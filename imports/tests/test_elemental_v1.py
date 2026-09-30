import json
import tempfile
from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import User
from documents.models import ElectronicReceipt
from imports.services import commit_batch, create_preview_batch
from organizations.models import TaxpayerOrganization
from payments.models import Payment
from reports.models import MonthlyClose
from sales.models import Sale


class ElementalV1ImportTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.user = User.objects.create_user("elemental-import")
        self.org = TaxpayerOrganization.objects.create(tax_id="77.111.222-3", legal_name="Taller Ficticio SpA", dte_41_enabled=True)
        self.period = date(2026, 9, 1)

    def payload(self, *, batch="a" * 64, detail="Taller ficticio", operation="transaction:101", payment="payment:201"):
        return {
            "contract_version": "elemental-cuadratura-v1", "origin_system": "ELEMENTAL", "batch_id": batch,
            "generated_at": "2026-09-30T12:00:00-03:00",
            "source_organization": {"external_id": "organization:99", "name": "Taller Ficticio"},
            "expected_taxpayer": {"tax_id": self.org.tax_id, "legal_name": self.org.legal_name},
            "selection": {"period": "2026-09", "timezone": "America/Santiago", "criterion": "confirmed_payment_date_in_period"},
            "operations": [{
                "external_id": operation, "operation_date": "2026-08-25", "service_period": "2026-08",
                "concept": "workshop_classes", "detail": detail, "plan": "4 clases", "discipline": "Cerámica",
                "beneficiary": {"external_id": "person:1", "display_name": "Alumna Ficticia"}, "buyer": None,
                "tax": {"classification": "EXEMPT", "net": 45000, "vat": 0, "total": 45000},
                "payments": [{"external_id": payment, "payment_date": "2026-09-03", "amount": 45000, "status": "CONFIRMED", "method": "transferencia", "reference": "REF-FICTICIA"}],
            }],
            "pending_records": [{"entity_type": "payment", "external_id": "payment:999", "reasons": ["missing_linked_transaction"]}],
            "summary": {"operations": 1, "payments": 1, "pending": 1, "total_payments": 45000},
        }

    def upload(self, payload, name="elemental.json"):
        return SimpleUploadedFile(name, json.dumps(payload).encode(), content_type="application/json")

    def preview(self, payload):
        return create_preview_batch(organization=self.org, expected_period=self.period, actor=self.user, uploaded_file=self.upload(payload))[0]

    def test_import_and_reimport_different_batch_are_idempotent(self):
        first = self.preview(self.payload())
        self.assertEqual((first.new_rows, first.ignored_rows, first.total_amount), (1, 1, 45000))
        commit_batch(batch_id=first.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), Payment.objects.count(), ElectronicReceipt.objects.count()), (1, 1, 0))
        sale = Sale.objects.get()
        self.assertEqual((sale.status, sale.operation_date, sale.payments.count()), ("READY", date(2026, 8, 25), 1))
        second = self.preview(self.payload(batch="b" * 64))
        self.assertEqual((second.new_rows, second.existing_rows, second.conflict_rows), (0, 1, 0))
        commit_batch(batch_id=second.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), Payment.objects.count()), (1, 1))

    def test_correction_wrong_taxpayer_unknown_version_and_closed_period_block(self):
        first = self.preview(self.payload())
        commit_batch(batch_id=first.id, organization=self.org, actor=self.user)
        corrected = self.preview(self.payload(batch="c" * 64, detail="Detalle corregido"))
        self.assertEqual((corrected.status, corrected.conflict_rows), ("BLOCKED", 1))
        wrong = self.payload(batch="d" * 64, operation="transaction:102", payment="payment:202")
        wrong["expected_taxpayer"]["tax_id"] = "76.000.000-0"
        self.assertEqual(self.preview(wrong).status, "BLOCKED")
        unknown = self.payload()
        unknown["contract_version"] = "elemental-cuadratura-v2"
        with self.assertRaises(ValidationError):
            self.preview(unknown)
        MonthlyClose.objects.create(organization=self.org, period=self.period, version=1, status="CLOSED", closed_by=self.user)
        with self.assertRaises(ValidationError):
            self.preview(self.payload(batch="e" * 64, operation="transaction:103", payment="payment:203"))

    def test_existing_documented_sale_is_preserved(self):
        first = self.preview(self.payload())
        commit_batch(batch_id=first.id, organization=self.org, actor=self.user)
        sale = Sale.objects.get()
        sale.status = Sale.Status.DOCUMENTED
        sale.save(update_fields=["status"])
        second = self.preview(self.payload(batch="f" * 64))
        self.assertEqual(second.existing_rows, 1)
        commit_batch(batch_id=second.id, organization=self.org, actor=self.user)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.DOCUMENTED)

    def test_operation_with_multiple_payments_creates_one_sale(self):
        payload = self.payload(operation="transaction:multi", payment="payment:multi-1")
        payload["operations"][0]["payments"] = [
            {"external_id": "payment:multi-1", "payment_date": "2026-09-03", "amount": 20000, "status": "CONFIRMED", "method": "transferencia", "reference": "A"},
            {"external_id": "payment:multi-2", "payment_date": "2026-09-10", "amount": 25000, "status": "CONFIRMED", "method": "transferencia", "reference": "B"},
        ]
        payload["summary"]["payments"] = 2
        batch = self.preview(payload)
        commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), Payment.objects.count()), (1, 2))

    def test_new_operation_with_same_date_and_amount_as_elemental_sale_is_new(self):
        first = self.preview(self.payload())
        commit_batch(batch_id=first.id, organization=self.org, actor=self.user)
        other = self.preview(self.payload(batch="g" * 64, operation="transaction:104", payment="payment:204"))
        self.assertEqual((other.new_rows, other.conflict_rows), (1, 0))
        commit_batch(batch_id=other.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), Payment.objects.count()), (2, 2))

    def test_historical_sale_without_identifier_requires_explicit_reconciliation(self):
        Sale.objects.create(
            organization=self.org, operation_date=date(2026, 8, 25), detail="Histórico", tax_classification="EXEMPT",
            net_amount=45000, vat_amount=0, total_amount=45000, origin_system="CASHBOOK_CSV_V1", external_id="hist-1",
            created_by=self.user,
        )
        batch = self.preview(self.payload())
        self.assertEqual((batch.status, batch.conflict_rows), ("BLOCKED", 1))
        self.assertEqual(Sale.objects.count(), 1)

    def test_operation_with_several_payments_creates_one_sale(self):
        payload = self.payload()
        payload["operations"][0]["payments"] = [
            {"external_id": "payment:301", "payment_date": "2026-09-03", "amount": 20000, "status": "CONFIRMED", "reference": ""},
            {"external_id": "payment:302", "payment_date": "2026-09-10", "amount": 25000, "status": "CONFIRMED", "reference": ""},
        ]
        batch = self.preview(payload)
        commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), Payment.objects.count(), Sale.objects.get().payments.count()), (1, 2, 2))

    def test_invalid_json_and_unconfirmed_payment_are_rejected(self):
        with self.assertRaises(ValidationError):
            create_preview_batch(organization=self.org, expected_period=self.period, actor=self.user,
                                 uploaded_file=SimpleUploadedFile("elemental.json", b"{no-json", content_type="application/json"))
        payload = self.payload()
        payload["operations"][0]["payments"][0]["status"] = "INFORMED"
        self.assertEqual(self.preview(payload).status, "BLOCKED")
        self.assertEqual(Sale.objects.count(), 0)

    def test_competing_previews_confirm_only_once(self):
        first = self.preview(self.payload())
        second = self.preview(self.payload(batch="h" * 64))
        commit_batch(batch_id=first.id, organization=self.org, actor=self.user)
        with self.assertRaises(ValidationError):
            commit_batch(batch_id=second.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), Payment.objects.count()), (1, 1))
