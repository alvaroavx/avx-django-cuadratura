import hashlib
import json
from datetime import date, datetime

from imports.models import ImportRow
from imports.parser import CsvImportError, ParsedImport, ParsedRow, normalize_tax_id
from payments.models import Payment
from sales.models import Sale

CONTRACT_VERSION = "elemental-cuadratura-v1"
MAX_JSON_SIZE = 2 * 1024 * 1024
MAX_OPERATIONS = 5000


def _text(value, field, maximum, *, allow_blank=False):
    if not isinstance(value, str) or (not allow_blank and not value.strip()) or len(value) > maximum:
        raise CsvImportError(f"{field} es inválido.")
    return value.strip()


def _positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CsvImportError(f"{field} debe ser un entero CLP positivo.")
    return value


def _same_sale(sale, data):
    return (
        sale.operation_date.isoformat() == data["operation_date"]
        and sale.detail == data["detail"]
        and sale.tax_classification == data["classification"]
        and sale.net_amount == data["net_amount"]
        and sale.vat_amount == data["vat_amount"]
        and sale.total_amount == data["total_amount"]
    )


def parse_elemental_json(content):
    if not content:
        raise CsvImportError("El archivo está vacío.")
    if len(content) > MAX_JSON_SIZE:
        raise CsvImportError("El archivo JSON supera el límite de 2 MiB.")
    try:
        raw = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CsvImportError("El archivo debe estar codificado en UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise CsvImportError("El archivo no contiene JSON válido.") from exc
    if not isinstance(raw, dict):
        raise CsvImportError("La raíz JSON debe ser un objeto.")
    if raw.get("contract_version") != CONTRACT_VERSION:
        raise CsvImportError("Versión de contrato Elemental desconocida o incompatible.")
    if raw.get("origin_system") != "ELEMENTAL":
        raise CsvImportError("El sistema de origen no es ELEMENTAL.")
    batch_id = _text(raw.get("batch_id"), "batch_id", 64)
    try:
        datetime.fromisoformat(_text(raw.get("generated_at"), "generated_at", 64).replace("Z", "+00:00"))
        period = date.fromisoformat(_text(raw.get("selection", {}).get("period"), "selection.period", 7) + "-01")
    except (ValueError, TypeError) as exc:
        raise CsvImportError("Fecha de generación o período inválido.") from exc
    source = raw.get("source_organization") or {}
    taxpayer = raw.get("expected_taxpayer") or {}
    source_id = _text(source.get("external_id"), "source_organization.external_id", 160)
    source_name = _text(source.get("name"), "source_organization.name", 200)
    tax_id = _text(taxpayer.get("tax_id"), "expected_taxpayer.tax_id", 20)
    operations = raw.get("operations")
    if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
        raise CsvImportError(f"operations debe ser una lista de hasta {MAX_OPERATIONS} elementos.")
    parsed = ParsedImport(file_hash=hashlib.sha256(content).hexdigest(), file_size=len(content), taxpayer_tax_id=tax_id, taxpayer_name=_text(taxpayer.get("legal_name"), "expected_taxpayer.legal_name", 200), period=period)
    seen_operations, seen_payments = set(), set()
    for number, operation in enumerate(operations, 1):
        try:
            if not isinstance(operation, dict):
                raise CsvImportError("La operación debe ser un objeto.")
            external_id = _text(operation.get("external_id"), "operation.external_id", 160)
            if external_id in seen_operations:
                raise CsvImportError("Identificador de operación repetido en el archivo.")
            seen_operations.add(external_id)
            operation_date = date.fromisoformat(_text(operation.get("operation_date"), "operation.operation_date", 10))
            service_period = _text(operation.get("service_period"), "operation.service_period", 7)
            date.fromisoformat(service_period + "-01")
            detail = _text(operation.get("detail"), "operation.detail", 500)
            tax = operation.get("tax") or {}
            classification = tax.get("classification")
            if classification not in {"TAXABLE", "EXEMPT"}:
                raise CsvImportError("Clasificación tributaria inválida.")
            net, vat, total = (_positive_int(tax.get("net"), "tax.net"), tax.get("vat"), _positive_int(tax.get("total"), "tax.total"))
            if isinstance(vat, bool) or not isinstance(vat, int) or vat < 0 or net + vat != total or (classification == "EXEMPT" and vat):
                raise CsvImportError("Los montos no cumplen neto + IVA = total.")
            payments = operation.get("payments")
            if not isinstance(payments, list) or not payments:
                raise CsvImportError("La operación debe contener al menos un pago.")
            normalized_payments = []
            for payment in payments:
                payment_id = _text(payment.get("external_id"), "payment.external_id", 160)
                if payment_id in seen_payments:
                    raise CsvImportError("Identificador de pago repetido en el archivo.")
                seen_payments.add(payment_id)
                if payment.get("status") != "CONFIRMED":
                    raise CsvImportError("Solo se admiten pagos confirmados.")
                normalized_payments.append({
                    "external_id": payment_id,
                    "payment_date": date.fromisoformat(_text(payment.get("payment_date"), "payment.payment_date", 10)).isoformat(),
                    "amount": _positive_int(payment.get("amount"), "payment.amount"),
                    "reference": _text(payment.get("reference", ""), "payment.reference", 160, allow_blank=True),
                })
            if sum(item["amount"] for item in normalized_payments) != total:
                raise CsvImportError("La suma de pagos no coincide con el total de la operación.")
            beneficiary = operation.get("beneficiary") or {}
            normalized = {
                "external_id": external_id, "operation_date": operation_date.isoformat(),
                "service_period": service_period, "detail": detail,
                "customer_name": _text(beneficiary.get("display_name", ""), "beneficiary.display_name", 200, allow_blank=True),
                "classification": classification, "net_amount": net, "vat_amount": vat,
                "total_amount": total, "payments": normalized_payments,
            }
            fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            parsed.rows.append(ParsedRow(number, {"external_id": external_id}, normalized, fingerprint, classification))
        except (CsvImportError, ValueError, TypeError) as exc:
            parsed.rows.append(ParsedRow(number, {"external_id": operation.get("external_id") if isinstance(operation, dict) else ""}, errors=[str(exc)], status=ImportRow.Status.ERROR))
    for pending in raw.get("pending_records", []):
        if isinstance(pending, dict):
            parsed.rows.append(ParsedRow(len(parsed.rows) + 1, {"external_id": pending.get("external_id", "")}, warnings=["Pendiente en Elemental: " + ", ".join(pending.get("reasons", []))], status=ImportRow.Status.IGNORED))
    summary = raw.get("summary") or {}
    expected_total = sum(row.normalized.get("total_amount", 0) for row in parsed.rows)
    if summary.get("total_payments") != expected_total:
        parsed.errors.append("El total declarado no coincide con las operaciones del archivo.")
    parsed.source_metadata = {"batch_id": batch_id, "source_organization_id": source_id, "source_organization_name": source_name, "selection": raw.get("selection", {})}
    if any(row.status == ImportRow.Status.ERROR for row in parsed.rows):
        parsed.errors.append("Una o más operaciones contienen datos inválidos.")
    return parsed


def classify_elemental(parsed, *, organization, expected_period, origin_system="ELEMENTAL"):
    """Clasifica filas normalizadas de un contrato externo (Elemental v1 u operaciones v1)."""
    if normalize_tax_id(parsed.taxpayer_tax_id) != normalize_tax_id(organization.tax_id):
        parsed.errors.append("El contribuyente esperado no corresponde a la organización destino.")
    if parsed.period != expected_period:
        parsed.errors.append("El período seleccionado no corresponde al período activo.")
    for row in parsed.rows:
        if row.status != ImportRow.Status.NEW:
            continue
        data = row.normalized
        sale = Sale.objects.filter(organization=organization, origin_system=origin_system, external_id=data["external_id"]).first()
        payment_ids = [item["external_id"] for item in data["payments"]]
        payments = list(Payment.objects.filter(organization=organization, origin_system=origin_system, external_id__in=payment_ids))
        if sale:
            identical = _same_sale(sale, data) and len(payments) == len(payment_ids) and all(
                any(p.external_id == item["external_id"] and p.sale_id == sale.id and p.payment_date.isoformat() == item["payment_date"] and p.amount == item["amount"] for p in payments)
                for item in data["payments"]
            )
            row.status = ImportRow.Status.ALREADY_IMPORTED if identical else ImportRow.Status.CONFLICT
            (row.warnings if identical else row.errors).append("La operación ya fue importada con datos idénticos." if identical else "El identificador externo ya existe con contenido diferente.")
        elif payments:
            row.status = ImportRow.Status.CONFLICT
            row.errors.append("Un identificador de pago ya existe sin la operación esperada.")
        elif Sale.objects.filter(organization=organization, operation_date=data["operation_date"], total_amount=data["total_amount"]).exclude(origin_system=origin_system).exists():
            row.status = ImportRow.Status.CONFLICT
            row.errors.append("Existe una operación histórica posiblemente duplicada; debe conciliarse explícitamente.")
    if any(row.status == ImportRow.Status.CONFLICT for row in parsed.rows):
        parsed.errors.append("Una o más operaciones entran en conflicto con la base local.")
    return parsed
