import hashlib
from datetime import date
from io import BytesIO
from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import load_workbook
from accounts.models import User
from audit.models import AuditEvent
from organizations.models import TaxpayerOrganization
from sales.services import register_manual_operation, register_manual_receipt
from sii.gateway import DisabledSiiGateway, SiiDisabledError
from .services import close_month, generate_workbook, reopen_month

class ReportingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user("accountant")
        self.org=TaxpayerOrganization.objects.create(tax_id="76.200.001-1",legal_name="Reporte SpA",dte_39_enabled=True)
        sale,_=register_manual_operation(organization=self.org,actor=self.user,operation_date=date(2026,7,3),payment_date=date(2026,7,3),total=1190,transfer_reference="R",detail="Actividad",classification="TAXABLE",idempotency_key=__import__("uuid").uuid4())
        register_manual_receipt(organization=self.org,actor=self.user,sale=sale,document_type=39,folio=15,tax_issue_date=date(2026,7,3),issuer_name="Reporte SpA",signer_name="Persona")

    def test_provisional_export_has_required_sheets_totals_and_manual_fields(self):
        content,totals,exceptions=generate_workbook(self.org,date(2026,7,1),withholding=25,ppm=30)
        wb=load_workbook(BytesIO(content),data_only=True)
        self.assertEqual(wb.sheetnames,["Libro provisional","Excepciones"]); self.assertEqual(totals,[1000,190,1190]); self.assertFalse(exceptions)
        values=[cell.value for row in wb["Libro provisional"] for cell in row]
        self.assertIn("Retención segunda categoría (manual)",values); self.assertIn("PPM (manual)",values)

    def test_close_hash_audit_and_reopen_reason(self):
        close=close_month(organization=self.org,period=date(2026,7,1),actor=self.user,withholding=25,ppm=30)
        with close.file.open("rb") as stream: self.assertEqual(hashlib.sha256(stream.read()).hexdigest(),close.file_hash)
        self.assertTrue(AuditEvent.objects.filter(action="month.closed",target_id=close.id).exists())
        with self.assertRaises(ValidationError): reopen_month(close=close,actor=self.user,reason="")
        reopen_month(close=close,actor=self.user,reason="Corrección confirmada por contadora")
        self.assertTrue(AuditEvent.objects.filter(action="month.reopened",target_id=close.id).exists())

    def test_second_close_is_rejected(self):
        close_month(organization=self.org,period=date(2026,7,1),actor=self.user)
        with self.assertRaises(ValidationError): close_month(organization=self.org,period=date(2026,7,1),actor=self.user)

    def test_disabled_gateway_never_echoes_identifier_or_secret(self):
        secret="private-secret-value"
        with self.assertRaises(SiiDisabledError) as ctx: DisabledSiiGateway().submit(receipt_id=secret)
        self.assertNotIn(secret,str(ctx.exception)); self.assertIn("deshabilitada",str(ctx.exception))

