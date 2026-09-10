from datetime import date
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from audit.services import record_event
from documents.models import ElectronicReceipt
from reports.models import MonthlyClose
from sales.models import Sale, SaleLine
from .models import ImportBatch, ImportRow
from .parser import PARSER_VERSION, normalize_tax_id, parse_cashbook_csv


def _is_period_closed(organization, period):
    return MonthlyClose.objects.filter(
        organization=organization, period=period, status=MonthlyClose.Status.CLOSED
    ).exists()


def classify_import(parsed, *, organization, expected_period):
    if normalize_tax_id(parsed.taxpayer_tax_id) != normalize_tax_id(organization.tax_id):
        parsed.errors.append("El RUT de la cabecera no corresponde a la organización activa.")
    if parsed.period != expected_period:
        parsed.errors.append("El período de la cabecera no corresponde al período activo.")
    for row in parsed.rows:
        if row.status != ImportRow.Status.NEW:
            continue
        normalized = row.normalized
        issue_date = date.fromisoformat(normalized["issue_date"])
        if issue_date.year != expected_period.year or issue_date.month != expected_period.month:
            row.status = ImportRow.Status.ERROR
            row.errors.append("La fecha tributaria está fuera del período activo.")
            continue
        document_type = normalized["document_type"]
        if document_type == 39 and not organization.dte_39_enabled:
            row.status = ImportRow.Status.ERROR
            row.errors.append("DTE 39 no está habilitado para esta organización.")
            continue
        if document_type == 41 and not organization.dte_41_enabled:
            row.status = ImportRow.Status.ERROR
            row.errors.append("DTE 41 no está habilitado para esta organización.")
            continue
        receipt = ElectronicReceipt.objects.filter(
            organization=organization, document_type=document_type, folio=normalized["folio"]
        ).select_related("sale").first()
        if not receipt:
            continue
        identical = (
            receipt.status == ElectronicReceipt.Status.ACCEPTED
            and receipt.tax_issue_date == issue_date
            and receipt.net_amount == normalized["net_amount"]
            and receipt.vat_amount == normalized["vat_amount"]
            and receipt.total_amount == normalized["total_amount"]
            and receipt.sale.detail == normalized["detail"]
            and receipt.sale.tax_classification == normalized["classification"]
        )
        row.status = ImportRow.Status.ALREADY_IMPORTED if identical else ImportRow.Status.CONFLICT
        if identical:
            row.warnings.append("La boleta ya existe con datos idénticos; no se volverá a crear.")
        else:
            row.errors.append("El folio ya existe con datos diferentes.")
    if any(row.status == ImportRow.Status.ERROR for row in parsed.rows):
        parsed.errors.append("Una o más filas contienen errores.")
    if any(row.status == ImportRow.Status.CONFLICT for row in parsed.rows):
        parsed.errors.append("Uno o más folios entran en conflicto con la base local.")
    return parsed


def analyze_content(content, *, organization, expected_period):
    parsed = parse_cashbook_csv(content)
    return classify_import(parsed, organization=organization, expected_period=expected_period)


def _batch_counts(parsed):
    counts = {status: 0 for status in ImportRow.Status.values}
    for row in parsed.rows:
        counts[row.status] += 1
    valid = [row for row in parsed.rows if row.normalized and row.status != ImportRow.Status.ERROR]
    totals = parsed.totals
    return {
        "detected_rows": len(valid),
        "new_rows": counts[ImportRow.Status.NEW],
        "existing_rows": counts[ImportRow.Status.ALREADY_IMPORTED],
        "conflict_rows": counts[ImportRow.Status.CONFLICT],
        "error_rows": counts[ImportRow.Status.ERROR],
        "ignored_rows": counts[ImportRow.Status.IGNORED],
        "taxable_rows": sum(row.classification == "TAXABLE" for row in valid),
        "exempt_rows": sum(row.classification == "EXEMPT" for row in valid),
        "total_net": totals["net"],
        "total_vat": totals["vat"],
        "total_amount": totals["total"],
    }


def create_preview_batch(*, organization, expected_period, actor, uploaded_file):
    if _is_period_closed(organization, expected_period):
        raise ValidationError("El período está cerrado; debe reabrirlo antes de importar.")
    original_name = Path(uploaded_file.name).name[:255]
    if Path(original_name).suffix.lower() != ".csv":
        raise ValidationError("Solo se admiten archivos con extensión .csv.")
    content = uploaded_file.read()
    parsed = analyze_content(content, organization=organization, expected_period=expected_period)
    blocked = bool(parsed.errors)
    values = _batch_counts(parsed)
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                organization=organization,
                period=expected_period,
                parser_version=PARSER_VERSION,
                original_filename=original_name,
                source_file=f"private/imports/{timezone.now():%Y/%m}/pending.csv",
                file_hash=parsed.file_hash,
                file_size=parsed.file_size,
                uploaded_by=actor,
                status=ImportBatch.Status.BLOCKED if blocked else ImportBatch.Status.VALIDATED,
                declared_net=parsed.declared_net,
                declared_vat=parsed.declared_vat,
                declared_total=parsed.declared_total,
                validation_errors=parsed.errors,
                validated_at=timezone.now(),
                **values,
            )
            batch.source_file.save(f"{batch.id}.csv", ContentFile(content), save=True)
            ImportRow.objects.bulk_create(
                [
                    ImportRow(
                        batch=batch,
                        line_number=row.line_number,
                        original_data=row.original,
                        normalized_data=row.normalized,
                        fingerprint=row.fingerprint,
                        classification=row.classification,
                        warnings=row.warnings,
                        errors=row.errors,
                        status=row.status,
                    )
                    for row in parsed.rows
                ]
            )
    except IntegrityError:
        existing = ImportBatch.objects.get(organization=organization, file_hash=parsed.file_hash)
        record_event(
            organization=organization,
            actor=actor,
            action="import.repeated_file",
            target=existing,
            metadata={"period": expected_period.isoformat()},
        )
        return existing, False
    record_event(
        organization=organization,
        actor=actor,
        action="import.uploaded",
        target=batch,
        metadata={"period": expected_period.isoformat(), "size": batch.file_size},
    )
    record_event(
        organization=organization,
        actor=actor,
        action="import.previewed",
        target=batch,
        metadata={
            "period": expected_period.isoformat(),
            "status": batch.status,
            "new_rows": batch.new_rows,
            "conflicts": batch.conflict_rows,
            "errors": batch.error_rows,
        },
    )
    if batch.conflict_rows:
        record_event(
            organization=organization,
            actor=actor,
            action="import.conflicts_detected",
            target=batch,
            metadata={"count": batch.conflict_rows},
        )
    return batch, True


@transaction.atomic
def commit_batch(*, batch_id, organization, actor):
    batch = ImportBatch.objects.select_for_update().get(pk=batch_id, organization=organization)
    if batch.status == ImportBatch.Status.COMMITTED:
        return batch, False
    if batch.status != ImportBatch.Status.VALIDATED:
        raise ValidationError("El lote no está validado o contiene bloqueos.")
    if _is_period_closed(organization, batch.period):
        raise ValidationError("El período está cerrado; debe reabrirlo antes de importar.")
    rows = list(batch.rows.select_for_update().order_by("line_number"))
    if any(row.status in {ImportRow.Status.CONFLICT, ImportRow.Status.ERROR} for row in rows):
        raise ValidationError("El lote contiene conflictos o errores y no puede confirmarse.")
    for row in rows:
        if row.status != ImportRow.Status.NEW:
            continue
        data = row.normalized_data
        if ElectronicReceipt.objects.filter(
            organization=organization,
            document_type=data["document_type"],
            folio=data["folio"],
        ).exists():
            raise ValidationError(
                f"El folio {data['folio']} cambió desde la previsualización; vuelva a cargar el archivo."
            )
        sale = Sale.objects.create(
            organization=organization,
            operation_date=date.fromisoformat(data["issue_date"]),
            detail=data["detail"],
            observations=data.get("historical_observation", ""),
            tax_classification=data["classification"],
            net_amount=data["net_amount"],
            vat_amount=data["vat_amount"],
            total_amount=data["total_amount"],
            status=Sale.Status.DOCUMENTED,
            reconciliation_status=Sale.ReconciliationStatus.MISSING_PAYMENT_DATA,
            origin_system="CASHBOOK_CSV_V1",
            external_id=row.fingerprint,
            created_by=actor,
        )
        SaleLine.objects.create(
            sale=sale,
            description=data["detail"],
            quantity=1,
            unit_amount=data["total_amount"],
            total_amount=data["total_amount"],
        )
        receipt = ElectronicReceipt.objects.create(
            organization=organization,
            sale=sale,
            document_type=data["document_type"],
            folio=data["folio"],
            tax_issue_date=date.fromisoformat(data["issue_date"]),
            net_amount=data["net_amount"],
            vat_amount=data["vat_amount"],
            total_amount=data["total_amount"],
            signer_name=data.get("historical_issuer", ""),
            status=ElectronicReceipt.Status.ACCEPTED,
            created_by=actor,
        )
        row.sale = sale
        row.receipt = receipt
        row.status = ImportRow.Status.IMPORTED
        row.save(update_fields=["sale", "receipt", "status"])
    batch.status = ImportBatch.Status.COMMITTED
    batch.committed_at = timezone.now()
    batch.save(update_fields=["status", "committed_at"])
    record_event(
        organization=organization,
        actor=actor,
        action="import.committed",
        target=batch,
        metadata={
            "period": batch.period.isoformat(),
            "created": batch.new_rows,
            "already_existing": batch.existing_rows,
        },
    )
    return batch, True
