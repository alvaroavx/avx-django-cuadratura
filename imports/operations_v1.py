"""Contrato genérico `cuadratura-operations-v1` recibido por la API (ADR 0005).

Lo define Cuadratura y no depende de ningún emisor. Produce filas normalizadas con la
misma forma que `elemental_v1`, de modo que la clasificación y la confirmación son
compartidas. El sistema de origen no viaja en el documento: lo fija el cliente API.
"""

import hashlib
import json
from datetime import date, datetime

from imports.elemental_v1 import _positive_int, _text
from imports.models import ImportRow
from imports.parser import CsvImportError, ParsedImport, ParsedRow

CONTRACT_VERSION = "cuadratura-operations-v1"
MAX_JSON_SIZE = 2 * 1024 * 1024
MAX_OPERATIONS = 5000


def content_fingerprint(raw):
    """Huella del contenido sin `generated_at`, para reconocer reenvíos del mismo lote."""
    stable = {key: value for key, value in raw.items() if key != "generated_at"}
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def load_document(content):
    if not content:
        raise CsvImportError("El cuerpo está vacío.")
    if len(content) > MAX_JSON_SIZE:
        raise CsvImportError("El documento JSON supera el límite de 2 MiB.")
    try:
        raw = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CsvImportError("El documento debe estar codificado en UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise CsvImportError("El cuerpo no contiene JSON válido.") from exc
    if not isinstance(raw, dict):
        raise CsvImportError("La raíz JSON debe ser un objeto.")
    if raw.get("contract_version") != CONTRACT_VERSION:
        raise CsvImportError(f"contract_version debe ser {CONTRACT_VERSION}.")
    return raw


def _date(value, field):
    try:
        return date.fromisoformat(_text(value, field, 10))
    except ValueError as exc:
        raise CsvImportError(f"{field} debe ser una fecha AAAA-MM-DD.") from exc


def _operation(operation, seen_operations, seen_payments):
    if not isinstance(operation, dict):
        raise CsvImportError("La operación debe ser un objeto.")
    external_id = _text(operation.get("external_id"), "operation.external_id", 160)
    if external_id in seen_operations:
        raise CsvImportError("Identificador de operación repetido en el documento.")
    seen_operations.add(external_id)
    operation_date = _date(operation.get("operation_date"), "operation.operation_date")
    service_period = operation.get("service_period") or ""
    if service_period:
        try:
            date.fromisoformat(_text(service_period, "operation.service_period", 7) + "-01")
        except ValueError as exc:
            raise CsvImportError("operation.service_period debe tener formato AAAA-MM.") from exc
    tax = operation.get("tax")
    if not isinstance(tax, dict):
        raise CsvImportError("operation.tax es obligatorio.")
    classification = tax.get("classification")
    if classification not in {"TAXABLE", "EXEMPT"}:
        raise CsvImportError("tax.classification debe ser TAXABLE o EXEMPT.")
    net, vat, total = (
        _positive_int(tax.get("net"), "tax.net"),
        tax.get("vat"),
        _positive_int(tax.get("total"), "tax.total"),
    )
    if (
        isinstance(vat, bool)
        or not isinstance(vat, int)
        or vat < 0
        or net + vat != total
        or (classification == "EXEMPT" and vat)
    ):
        raise CsvImportError("Los montos no cumplen neto + IVA = total en CLP enteros.")
    payments = operation.get("payments")
    if not isinstance(payments, list) or not payments:
        raise CsvImportError("La operación debe contener al menos un pago.")
    normalized_payments = []
    for payment in payments:
        if not isinstance(payment, dict):
            raise CsvImportError("El pago debe ser un objeto.")
        payment_id = _text(payment.get("external_id"), "payment.external_id", 160)
        if payment_id in seen_payments:
            raise CsvImportError("Identificador de pago repetido en el documento.")
        seen_payments.add(payment_id)
        normalized_payments.append({
            "external_id": payment_id,
            "payment_date": _date(payment.get("payment_date"), "payment.payment_date").isoformat(),
            "amount": _positive_int(payment.get("amount"), "payment.amount"),
            "reference": _text(payment.get("reference", ""), "payment.reference", 160, allow_blank=True),
        })
    if sum(item["amount"] for item in normalized_payments) != total:
        raise CsvImportError("La suma de pagos no coincide con el total de la operación.")
    return {
        "external_id": external_id,
        "operation_date": operation_date.isoformat(),
        "service_period": service_period,
        "detail": _text(operation.get("detail"), "operation.detail", 500),
        "customer_name": _text(operation.get("customer_name", ""), "operation.customer_name", 200, allow_blank=True),
        "classification": classification,
        "net_amount": net,
        "vat_amount": vat,
        "total_amount": total,
        "payments": normalized_payments,
    }


def parse_operations_document(content, *, origin_system):
    raw = load_document(content)
    batch_id = _text(raw.get("batch_id"), "batch_id", 64)
    try:
        datetime.fromisoformat(_text(raw.get("generated_at"), "generated_at", 64).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CsvImportError("generated_at debe ser una fecha y hora ISO 8601.") from exc
    try:
        period = date.fromisoformat(_text(raw.get("period"), "period", 7) + "-01")
    except ValueError as exc:
        raise CsvImportError("period debe tener formato AAAA-MM.") from exc
    taxpayer = raw.get("taxpayer")
    if not isinstance(taxpayer, dict):
        raise CsvImportError("taxpayer es obligatorio.")
    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise CsvImportError("source debe ser un objeto.")
    operations = raw.get("operations")
    if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
        raise CsvImportError(f"operations debe ser una lista de hasta {MAX_OPERATIONS} elementos.")
    parsed = ParsedImport(
        file_hash=hashlib.sha256(content).hexdigest(),
        file_size=len(content),
        taxpayer_tax_id=_text(taxpayer.get("tax_id"), "taxpayer.tax_id", 20),
        taxpayer_name=_text(taxpayer.get("legal_name", ""), "taxpayer.legal_name", 200, allow_blank=True),
        period=period,
    )
    seen_operations, seen_payments = set(), set()
    for number, operation in enumerate(operations, 1):
        try:
            normalized = _operation(operation, seen_operations, seen_payments)
        except (CsvImportError, ValueError, TypeError) as exc:
            reference = operation.get("external_id") if isinstance(operation, dict) else ""
            parsed.rows.append(
                ParsedRow(number, {"external_id": reference}, errors=[str(exc)], status=ImportRow.Status.ERROR)
            )
            continue
        fingerprint = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        parsed.rows.append(
            ParsedRow(number, {"external_id": normalized["external_id"]}, normalized, fingerprint, normalized["classification"])
        )
    excluded = raw.get("excluded_records") or []
    if not isinstance(excluded, list) or len(excluded) > MAX_OPERATIONS:
        raise CsvImportError(f"excluded_records debe ser una lista de hasta {MAX_OPERATIONS} elementos.")
    for record in excluded:
        if isinstance(record, dict):
            reasons = record.get("reasons", [])
            if not isinstance(reasons, list):
                raise CsvImportError("excluded_records[].reasons debe ser una lista.")
            reasons = [str(reason)[:80] for reason in reasons if reason][:10]
            parsed.rows.append(
                ParsedRow(
                    len(parsed.rows) + 1,
                    {"external_id": str(record.get("external_id", ""))[:160]},
                    warnings=["Excluido por el origen: " + (", ".join(reasons) or "sin motivo")],
                    status=ImportRow.Status.IGNORED,
                )
            )
    summary = raw.get("summary")
    if not isinstance(summary, dict):
        raise CsvImportError("summary es obligatorio.")
    valid = [row for row in parsed.rows if row.normalized]
    expected = {
        "operations": len(operations),
        "payments": sum(len(row.normalized["payments"]) for row in valid),
        "total_amount": sum(row.normalized["total_amount"] for row in valid),
    }
    if any(summary.get(key) != value for key, value in expected.items()):
        parsed.errors.append("summary no coincide con las operaciones del documento.")
    if any(row.status == ImportRow.Status.ERROR for row in parsed.rows):
        parsed.errors.append("Una o más operaciones contienen datos inválidos.")
    parsed.source_metadata = {
        "origin_system": origin_system,
        "batch_id": batch_id,
        "content_fingerprint": content_fingerprint(raw),
        "source_organization_id": str(source.get("organization_id", ""))[:160],
        "source_organization_name": str(source.get("name", ""))[:200],
        "selection": {"period": raw["period"]},
    }
    return parsed
