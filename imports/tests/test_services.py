import shutil
import tempfile
import threading
from datetime import date
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook
from accounts.models import User
from audit.models import AuditEvent
from documents.models import ElectronicReceipt
from organizations.models import OrganizationMembership, TaxpayerOrganization
from payments.models import Payment
from reports.models import MonthlyClose
from reports.services import generate_workbook
from sales.models import Sale
from imports.models import ImportBatch, ImportRow
from imports.parser import parse_cashbook_csv
from imports.services import analyze_content, commit_batch, create_preview_batch

FIXTURE = Path(__file__).parent / "fixtures" / "cashbook_july_synthetic.csv"


class ImportServiceTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="cuadratura-import-test-")
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)
        self.user = User.objects.create_user("accountant", password="test-password")
        self.org = TaxpayerOrganization.objects.create(
            tax_id="76.555.555-5",
            legal_name="Organización Sintética SpA",
            dte_39_enabled=True,
            dte_41_enabled=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org, user=self.user, role="ACCOUNTANT"
        )
        self.period = date(2026, 7, 1)

    def content(self):
        return FIXTURE.read_bytes()

    def upload(self, content=None, name="libro-sintetico.csv"):
        return SimpleUploadedFile(name, content or self.content(), content_type="text/csv")

    def preview(self, content=None):
        return create_preview_batch(
            organization=self.org,
            expected_period=self.period,
            actor=self.user,
            uploaded_file=self.upload(content),
        )[0]

    def test_preview_writes_no_financial_records_and_commit_invents_no_payment(self):
        batch = self.preview()
        self.assertEqual(batch.status, "VALIDATED")
        self.assertEqual((batch.new_rows, batch.taxable_rows, batch.exempt_rows), (19, 13, 6))
        self.assertEqual((batch.total_net, batch.total_vat, batch.total_amount), (546034, 72966, 619000))
        self.assertEqual((Sale.objects.count(), ElectronicReceipt.objects.count(), Payment.objects.count()), (0, 0, 0))
        committed, created = commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        self.assertTrue(created)
        self.assertEqual(committed.status, "COMMITTED")
        self.assertEqual((Sale.objects.count(), ElectronicReceipt.objects.count(), Payment.objects.count()), (19, 19, 0))
        self.assertEqual(Sale.objects.filter(reconciliation_status="MISSING_PAYMENT_DATA").count(), 19)
        self.assertEqual(ImportRow.objects.filter(status="IMPORTED").count(), 19)
        self.assertTrue(AuditEvent.objects.filter(action="import.uploaded").exists())
        self.assertTrue(AuditEvent.objects.filter(action="import.previewed").exists())
        self.assertTrue(AuditEvent.objects.filter(action="import.committed").exists())

    def test_header_tax_id_period_and_date_mismatch_block(self):
        wrong_org = TaxpayerOrganization.objects.create(
            tax_id="77.777.777-7", legal_name="Otra", dte_39_enabled=True, dte_41_enabled=True
        )
        parsed = analyze_content(self.content(), organization=wrong_org, expected_period=self.period)
        self.assertIn("RUT", " ".join(parsed.errors))
        parsed = analyze_content(self.content(), organization=self.org, expected_period=date(2026, 8, 1))
        self.assertIn("período", " ".join(parsed.errors).lower())
        outside = self.content().replace(b"01/07/2026", b"01/08/2026", 1)
        parsed = analyze_content(outside, organization=self.org, expected_period=self.period)
        self.assertTrue(any(row.status == "ERROR" for row in parsed.rows))

    def test_repeated_file_returns_existing_batch(self):
        first = self.preview()
        second, created = create_preview_batch(
            organization=self.org,
            expected_period=self.period,
            actor=self.user,
            uploaded_file=self.upload(),
        )
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(ImportBatch.objects.count(), 1)

    def test_identical_existing_receipts_are_noop_and_conflicting_folio_blocks(self):
        batch = self.preview()
        commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        identical_content = self.content().replace(
            b"Organizaci\xc3\xb3n Sint\xc3\xa9tica SpA", b"Organizaci\xc3\xb3n Sint\xc3\xa9tica SpA ", 1
        )
        identical = self.preview(identical_content)
        self.assertEqual((identical.new_rows, identical.existing_rows, identical.conflict_rows), (0, 19, 0))
        conflict_content = self.content().replace(b"Servicio sint\xc3\xa9tico 01", b"Detalle diferente", 1)
        conflict = self.preview(conflict_content)
        self.assertEqual(conflict.status, "BLOCKED")
        self.assertEqual(conflict.conflict_rows, 1)
        self.assertTrue(
            AuditEvent.objects.filter(action="import.conflicts_detected", target_id=conflict.id).exists()
        )

    def test_atomic_rollback_if_receipt_creation_fails(self):
        batch = self.preview()
        original_create = ElectronicReceipt.objects.create
        calls = {"count": 0}
        def failing_create(**kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("synthetic failure")
            return original_create(**kwargs)
        with patch("imports.services.ElectronicReceipt.objects.create", side_effect=failing_create):
            with self.assertRaises(RuntimeError):
                commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        self.assertEqual((Sale.objects.count(), ElectronicReceipt.objects.count()), (0, 0))
        batch.refresh_from_db()
        self.assertEqual(batch.status, "VALIDATED")

    def test_closed_period_blocks_preview(self):
        MonthlyClose.objects.create(
            organization=self.org, period=self.period, version=1, status="CLOSED", closed_by=self.user
        )
        with self.assertRaises(ValidationError):
            self.preview()

    def test_period_closed_after_preview_blocks_commit(self):
        batch = self.preview()
        MonthlyClose.objects.create(
            organization=self.org, period=self.period, version=1, status="CLOSED", closed_by=self.user
        )
        with self.assertRaises(ValidationError):
            commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        self.assertEqual(Sale.objects.count(), 0)

    def test_formula_detail_is_neutralized_in_xlsx_export(self):
        content = self.content().replace(b"Servicio sint\xc3\xa9tico 01", b"=2+2", 1)
        batch = self.preview(content)
        commit_batch(batch_id=batch.id, organization=self.org, actor=self.user)
        workbook_content, _, _ = generate_workbook(self.org, self.period)
        workbook = load_workbook(__import__("io").BytesIO(workbook_content), data_only=False)
        details = [cell.value for cell in workbook["Libro provisional"][2]]
        self.assertIn("'=2+2", details)

    def test_web_permissions_isolation_private_file_and_blocked_preview_survives(self):
        operator = User.objects.create_user("operator", password="test-password")
        OrganizationMembership.objects.create(organization=self.org, user=operator, role="OPERATOR")
        self.client.force_login(operator)
        url = reverse("import-create", args=[self.org.id, "2026-07"])
        self.assertEqual(self.client.get(url).status_code, 403)
        viewer = User.objects.create_user("viewer-import", password="test-password")
        OrganizationMembership.objects.create(organization=self.org, user=viewer, role="VIEWER")
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(url).status_code, 403)
        admin = User.objects.create_user("org-admin", password="test-password")
        OrganizationMembership.objects.create(
            organization=self.org, user=admin, role="ORGANIZATION_ADMIN"
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        platform = User.objects.create_user(
            "platform-import", password="test-password", platform_role="PLATFORM_ADMIN"
        )
        self.client.force_login(platform)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.user)
        bad = self.content().replace(b'"$619,000"', b'"$620,000"')
        response = self.client.post(url, {"file": self.upload(bad)}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "confirmación está bloqueada")
        batch = ImportBatch.objects.get()
        self.assertEqual(self.client.get(batch.source_file.url).status_code, 404)
        other_user = User.objects.create_user("other", password="test-password")
        other_org = TaxpayerOrganization.objects.create(tax_id="78.888.888-8", legal_name="Otra")
        OrganizationMembership.objects.create(organization=other_org, user=other_user, role="ACCOUNTANT")
        self.client.force_login(other_user)
        cross = reverse("import-preview", args=[other_org.id, "2026-07", batch.id])
        self.assertEqual(self.client.get(cross).status_code, 404)


class ConcurrentImportCommitTests(TransactionTestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="cuadratura-import-concurrent-")
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)

    def test_double_commit_creates_each_row_once(self):
        user = User.objects.create_user("concurrent-import")
        org = TaxpayerOrganization.objects.create(
            tax_id="76.555.555-5", legal_name="Sintética", dte_39_enabled=True, dte_41_enabled=True
        )
        period = date(2026, 7, 1)
        batch, _ = create_preview_batch(
            organization=org,
            expected_period=period,
            actor=user,
            uploaded_file=SimpleUploadedFile("synthetic.csv", FIXTURE.read_bytes()),
        )
        barrier = threading.Barrier(2)
        results = []
        errors = []
        def run():
            close_old_connections()
            try:
                barrier.wait()
                results.append(commit_batch(batch_id=batch.id, organization=org, actor=user)[1])
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual((Sale.objects.count(), ElectronicReceipt.objects.count(), Payment.objects.count()), (19, 19, 0))
