import hashlib
from io import BytesIO
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from openpyxl import Workbook
from audit.services import record_event
from documents.models import ElectronicReceipt
from sales.models import Sale
from .models import MonthlyClose

HEADERS = ["Correlativo", "RUT contribuyente", "Razón social", "Período", "Tipo operación", "Folio", "Tipo documento", "Emisor tributario", "Vendedor o firmante", "Clasificación", "Fecha operación", "Detalle", "Neto", "IVA", "Total"]

def spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value

def period_receipts(organization, period):
    return ElectronicReceipt.objects.filter(organization=organization, status=ElectronicReceipt.Status.ACCEPTED, tax_issue_date__year=period.year, tax_issue_date__month=period.month).select_related("sale").order_by("tax_issue_date", "folio")

def generate_workbook(organization, period, withholding=0, ppm=0):
    wb=Workbook(); ws=wb.active; ws.title="Libro provisional"; ws.append(HEADERS)
    receipts=list(period_receipts(organization, period))
    for index, receipt in enumerate(receipts, 1):
        sale=receipt.sale
        ws.append([index, spreadsheet_safe(organization.tax_id), spreadsheet_safe(organization.legal_name), period.strftime("%Y-%m"), "VENTA", receipt.folio, f"DTE {receipt.document_type}", spreadsheet_safe(receipt.issuer_name), spreadsheet_safe(receipt.signer_name), sale.get_tax_classification_display(), sale.operation_date, spreadsheet_safe(sale.detail), receipt.net_amount, receipt.vat_amount, receipt.total_amount])
    totals=[sum(getattr(r, field) for r in receipts) for field in ("net_amount","vat_amount","total_amount")]
    ws.append([]); ws.append(["TOTALES MENSUALES"]+[""]*11+totals)
    ws.append(["IVA débito fiscal", totals[1]]); ws.append(["Retención segunda categoría (manual)", withholding]); ws.append(["PPM (manual)", ppm]); ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
    ex=wb.create_sheet("Excepciones")
    ex.append(["Estado", "Fecha operación", "Detalle", "Total", "Motivo"])
    exceptions=Sale.objects.filter(organization=organization, operation_date__year=period.year, operation_date__month=period.month).exclude(reconciliation_status=Sale.ReconciliationStatus.RECONCILED)
    for sale in exceptions: ex.append([sale.get_reconciliation_status_display(), sale.operation_date, spreadsheet_safe(sale.detail), sale.total_amount, "No se incluye en libro definitivo mientras esté pendiente"])
    out=BytesIO(); wb.save(out); return out.getvalue(), totals, exceptions.exists()

@transaction.atomic
def close_month(*, organization, period, actor, withholding=0, ppm=0):
    if MonthlyClose.objects.filter(organization=organization, period=period, status=MonthlyClose.Status.CLOSED).exists(): raise ValidationError("El período ya está cerrado.")
    content, totals, has_exceptions=generate_workbook(organization, period, withholding, ppm)
    if has_exceptions: raise ValidationError("El período contiene excepciones y no puede cerrarse.")
    version=(MonthlyClose.objects.filter(organization=organization, period=period).aggregate(v=Max("version"))["v"] or 0)+1
    digest=hashlib.sha256(content).hexdigest()
    close=MonthlyClose.objects.create(organization=organization, period=period, version=version, closed_at=timezone.now(), closed_by=actor, file_hash=digest, total_net=totals[0], total_vat=totals[1], total_amount=totals[2], second_category_withholding=withholding, ppm=ppm, status=MonthlyClose.Status.CLOSED)
    close.file.save(f"libro-{organization.id}-{period:%Y-%m}-v{version}.xlsx", ContentFile(content), save=True)
    record_event(organization=organization, actor=actor, action="month.closed", target=close, metadata={"period":period.isoformat(),"version":version,"sha256":digest})
    return close

@transaction.atomic
def reopen_month(*, close, actor, reason):
    if close.status != MonthlyClose.Status.CLOSED: raise ValidationError("Solo se puede reabrir un cierre vigente.")
    if not reason.strip(): raise ValidationError("Debe indicar un motivo.")
    close.status=MonthlyClose.Status.REOPENED; close.reopen_reason=reason.strip(); close.save(update_fields=["status","reopen_reason"])
    record_event(organization=close.organization, actor=actor, action="month.reopened", target=close, metadata={"reason":reason.strip()})
    return close
