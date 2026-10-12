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
from payments.models import Payment
from organizations.models import TaxpayerOrganization
from .models import ImportBatch, ImportRow
from .parser import (
    CsvImportError,
    PARSER_VERSION,
    XLSX_PARSER_VERSION,
    normalize_tax_id,
    parse_cashbook_csv,
    parse_cashbook_xlsx,
)
from .elemental_v1 import CONTRACT_VERSION, classify_elemental, parse_elemental_json
from .operations_v1 import CONTRACT_VERSION as OPERATIONS_CONTRACT_VERSION
from .operations_v1 import parse_operations_document

EXTERNAL_CONTRACTS = {CONTRACT_VERSION, OPERATIONS_CONTRACT_VERSION}


def _is_period_closed(organization, period):
    return MonthlyClose.objects.filter(
        organization=organization, period=period, status=MonthlyClose.Status.CLOSED
    ).exists()


def classify_import(parsed, *, organization, expected_period):
    if normalize_tax_id(parsed.taxpayer_tax_id) != normalize_tax_id(organization.tax_id):
        parsed.errors.append("El RUT de la cabecera no corresponde a la organización activa.")
    if parsed.period != expected_period:
        parsed.errors.append("El período de la cabecera no corresponde al período activo.")
    seen_documents = {}
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
        document_key = (document_type, normalized["folio"])
        previous = seen_documents.get(document_key)
        if previous:
            row.status = ImportRow.Status.CONFLICT
            row.errors.append(
                f"El folio se repite en las líneas {previous.line_number} y {row.line_number}."
            )
            previous.status = ImportRow.Status.CONFLICT
            previous.errors.append(
                f"El folio se repite en las líneas {previous.line_number} y {row.line_number}."
            )
            continue
        seen_documents[document_key] = row
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


def analyze_content(content, *, organization, expected_period, extension=".csv"):
    if extension == ".json":
        parsed = parse_elemental_json(content)
        return classify_elemental(parsed, organization=organization, expected_period=expected_period)
    if extension == ".xlsx":
        parsed = parse_cashbook_xlsx(content, expected_period=expected_period)
    else:
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
    extension = Path(original_name).suffix.lower()
    if extension not in {".csv", ".xlsx", ".json"}:
        raise ValidationError("Solo se admiten archivos .json, .csv o .xlsx.")
    content = uploaded_file.read()
    try:
        parsed = analyze_content(
            content,
            organization=organization,
            expected_period=expected_period,
            extension=extension,
        )
    except CsvImportError as exc:
        raise ValidationError(str(exc)) from exc
    parser_version = (
        CONTRACT_VERSION if extension == ".json"
        else XLSX_PARSER_VERSION if extension == ".xlsx"
        else PARSER_VERSION
    )
    return _save_preview_batch(
        organization=organization,
        expected_period=expected_period,
        actor=actor,
        parsed=parsed,
        content=content,
        original_name=original_name,
        extension=extension,
        parser_version=parser_version,
    )


class BatchIdConflict(ValidationError):
    """El cliente reutilizó un batch_id con contenido distinto."""


class PeriodClosed(ValidationError):
    """El período destino tiene un cierre vigente."""


class PeriodAlreadySubmitted(ValidationError):
    """El origen ya tiene un lote activo (en revisión o confirmado) para el período."""


def create_api_preview_batch(*, organization, expected_period, client, content, signature=None):
    """Recibe un documento `cuadratura-operations-v1` desde la API y lo deja en preview.

    Nunca confirma: una persona con rol de importación revisa y confirma en la web.
    `batch_id` es la llave de idempotencia del cliente: reenviar el mismo contenido
    devuelve el lote existente; reutilizarlo con otro contenido es un conflicto. Un
    lote bloqueado puede reenviarse para volver a validarse. Mientras no exista un flujo
    de corrección, un origen tiene a lo sumo un lote activo por período: otro `batch_id`
    para el mismo período es un conflicto. `signature` es la evidencia de la firma del
    request y queda en `source_metadata`.
    Devuelve (lote, creado).
    """
    if _is_period_closed(organization, expected_period):
        raise PeriodClosed("El período está cerrado; debe reabrirlo antes de importar.")
    try:
        parsed = parse_operations_document(content, origin_system=client.origin_system)
    except CsvImportError as exc:
        raise ValidationError(str(exc)) from exc
    metadata = parsed.source_metadata
    if signature:
        metadata["signature"] = signature
    with transaction.atomic():
        TaxpayerOrganization.objects.select_for_update().get(pk=organization.pk)
        active = ImportBatch.objects.filter(
            organization=organization,
            parser_version=OPERATIONS_CONTRACT_VERSION,
            source_metadata__origin_system=client.origin_system,
        ).exclude(status=ImportBatch.Status.BLOCKED)
        previous = active.filter(source_metadata__batch_id=metadata["batch_id"]).first()
        if previous:
            if (
                previous.period != expected_period
                or previous.source_metadata.get("content_fingerprint") != metadata["content_fingerprint"]
            ):
                raise BatchIdConflict("batch_id ya fue usado con un contenido diferente.")
            return previous, False
        if active.filter(period=expected_period).exists():
            raise PeriodAlreadySubmitted(
                "Ya existe un lote activo de este origen para el período; no se admiten correcciones por API."
            )
        parsed = classify_elemental(
            parsed,
            organization=organization,
            expected_period=expected_period,
            origin_system=client.origin_system,
        )
        batch, created = _save_preview_batch(
            organization=organization,
            expected_period=expected_period,
            actor=client.service_user,
            parsed=parsed,
            content=content,
            original_name=f"api-{client.origin_system.lower()}-{expected_period:%Y-%m}.json",
            extension=".json",
            parser_version=OPERATIONS_CONTRACT_VERSION,
            audit_metadata={"api_client": str(client.pk)},
        )
    return batch, created


def _save_preview_batch(
    *,
    organization,
    expected_period,
    actor,
    parsed,
    content,
    original_name,
    extension,
    parser_version,
    audit_metadata=None,
):
    audit_metadata = audit_metadata or {}
    blocked = bool(parsed.errors)
    values = _batch_counts(parsed)
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                organization=organization,
                period=expected_period,
                parser_version=parser_version,
                original_filename=original_name,
                source_file=f"private/imports/{timezone.now():%Y/%m}/pending{extension}",
                file_hash=parsed.file_hash,
                file_size=parsed.file_size,
                uploaded_by=actor,
                status=ImportBatch.Status.BLOCKED if blocked else ImportBatch.Status.VALIDATED,
                declared_net=parsed.declared_net,
                declared_vat=parsed.declared_vat,
                declared_total=parsed.declared_total,
                validation_errors=parsed.errors,
                source_metadata=getattr(parsed, "source_metadata", {}),
                validated_at=timezone.now(),
                **values,
            )
            batch.source_file.save(f"{batch.id}{extension}", ContentFile(content), save=True)
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
        existing = ImportBatch.objects.get(
            organization=organization,
            period=expected_period,
            file_hash=parsed.file_hash,
        )
        record_event(
            organization=organization,
            actor=actor,
            action="import.repeated_file",
            target=existing,
            metadata={"period": expected_period.isoformat(), **audit_metadata},
        )
        return existing, False
    record_event(
        organization=organization,
        actor=actor,
        action="import.uploaded",
        target=batch,
        metadata={"period": expected_period.isoformat(), "size": batch.file_size, **audit_metadata},
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
            **audit_metadata,
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


def _service_period_observation(batch, origin_system, data):
    if batch.parser_version == CONTRACT_VERSION:
        return f"Período de servicio Elemental: {data['service_period']}"
    if data.get("service_period"):
        return f"Período de servicio informado por {origin_system}: {data['service_period']}"
    return ""


@transaction.atomic
def commit_batch(*, batch_id, organization, actor):
    batch = ImportBatch.objects.select_for_update().get(pk=batch_id, organization=organization)
    if batch.status == ImportBatch.Status.COMMITTED:
        return batch, False
    if batch.status != ImportBatch.Status.VALIDATED:
        raise ValidationError("El lote no está validado o contiene bloqueos.")
    if _is_period_closed(organization, batch.period):
        raise ValidationError("El período está cerrado; debe reabrirlo antes de importar.")
    TaxpayerOrganization.objects.select_for_update().get(pk=organization.pk)
    rows = list(batch.rows.select_for_update().order_by("line_number"))
    if any(row.status in {ImportRow.Status.CONFLICT, ImportRow.Status.ERROR} for row in rows):
        raise ValidationError("El lote contiene conflictos o errores y no puede confirmarse.")
    for row in rows:
        if row.status != ImportRow.Status.NEW:
            continue
        data = row.normalized_data
        if batch.parser_version in EXTERNAL_CONTRACTS:
            origin_system = batch.source_metadata.get("origin_system", "ELEMENTAL")
            existing = Sale.objects.filter(
                organization=organization, origin_system=origin_system, external_id=data["external_id"]
            ).first()
            if existing:
                existing_payments = list(
                    Payment.objects.filter(
                        organization=organization,
                        origin_system=origin_system,
                        external_id__in=[item["external_id"] for item in data["payments"]],
                    )
                )
                identical = (
                    existing.operation_date.isoformat() == data["operation_date"]
                    and existing.detail == data["detail"]
                    and existing.tax_classification == data["classification"]
                    and existing.net_amount == data["net_amount"]
                    and existing.vat_amount == data["vat_amount"]
                    and existing.total_amount == data["total_amount"]
                    and len(existing_payments) == len(data["payments"])
                    and all(
                        any(
                            payment.external_id == item["external_id"]
                            and payment.sale_id == existing.id
                            and payment.payment_date.isoformat() == item["payment_date"]
                            and payment.amount == item["amount"]
                            for payment in existing_payments
                        )
                        for item in data["payments"]
                    )
                )
                if not identical:
                    raise ValidationError(
                        "La información cambió desde la previsualización; vuelva a cargar el archivo."
                    )
                row.sale = existing
                row.payment = existing_payments[0]
                row.status = ImportRow.Status.ALREADY_IMPORTED
                row.save(update_fields=["sale", "payment", "status"])
                continue
            if Payment.objects.filter(
                organization=organization,
                origin_system=origin_system,
                external_id__in=[item["external_id"] for item in data["payments"]],
            ).exists():
                raise ValidationError("Un pago fue importado desde la previsualización; vuelva a cargar el archivo.")
            sale = Sale.objects.create(
                organization=organization,
                operation_date=date.fromisoformat(data["operation_date"]),
                detail=data["detail"],
                customer_name=data.get("customer_name", ""),
                observations=_service_period_observation(batch, origin_system, data),
                tax_classification=data["classification"],
                net_amount=data["net_amount"], vat_amount=data["vat_amount"], total_amount=data["total_amount"],
                status=Sale.Status.READY,
                reconciliation_status=Sale.ReconciliationStatus.RECONCILED,
                origin_system=origin_system, external_id=data["external_id"], created_by=actor,
            )
            SaleLine.objects.create(sale=sale, description=data["detail"], quantity=1, unit_amount=data["total_amount"], total_amount=data["total_amount"])
            created_payments = []
            for payment_data in data["payments"]:
                created_payments.append(Payment.objects.create(
                    organization=organization, sale=sale,
                    payment_date=date.fromisoformat(payment_data["payment_date"]),
                    amount=payment_data["amount"], transfer_reference=payment_data.get("reference", ""),
                    origin_system=origin_system, external_id=payment_data["external_id"], created_by=actor,
                ))
            row.sale = sale
            row.payment = created_payments[0]
            row.status = ImportRow.Status.IMPORTED
            row.save(update_fields=["sale", "payment", "status"])
            continue
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
