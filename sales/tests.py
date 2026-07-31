import threading
import uuid
from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from accounts.models import User
from audit.models import AuditEvent
from documents.models import ElectronicReceipt
from organizations.models import OrganizationMembership, TaxpayerOrganization
from payments.models import Payment
from .models import Sale
from .services import RECEIPT_TRANSITIONS, SALE_TRANSITIONS, calculate_tax_preview, register_manual_operation, register_manual_receipt, validate_transition

class DomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=User.objects.create_user("operator",password="test-password")
        cls.org=TaxpayerOrganization.objects.create(tax_id="76.000.001-1",legal_name="Organización A",dte_39_enabled=True,dte_41_enabled=True)

    def operation(self,classification=Sale.TaxClassification.TAXABLE,key=None,total=1190,reference="ABC"):
        return register_manual_operation(organization=self.org,actor=self.user,operation_date=date(2026,7,10),payment_date=date(2026,7,11),total=total,transfer_reference=reference,detail="Servicio",classification=classification,idempotency_key=key or uuid.uuid4())

    def test_taxable_and_exempt_preview_use_integer_clp(self):
        taxable=calculate_tax_preview(1190,"TAXABLE"); exempt=calculate_tax_preview(1190,"EXEMPT")
        self.assertEqual((taxable.net,taxable.vat,taxable.total),(1000,190,1190))
        self.assertEqual((exempt.net,exempt.vat,exempt.total),(1190,0,1190))

    def test_money_constraints_reject_inconsistent_and_exempt_vat(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sale.objects.create(organization=self.org,operation_date=date.today(),detail="x",tax_classification="EXEMPT",net_amount=100,vat_amount=19,total_amount=119,origin_system="X",external_id="bad",created_by=self.user)

    def test_double_submit_is_idempotent(self):
        key=uuid.uuid4(); first,created=self.operation(key=key); second,created_again=self.operation(key=key)
        self.assertTrue(created); self.assertFalse(created_again); self.assertEqual(first,second); self.assertEqual(Payment.objects.count(),1)

    def test_duplicate_payment_is_flagged(self):
        self.operation(reference="SAME"); duplicate,_=self.operation(reference="SAME")
        self.assertEqual(duplicate.reconciliation_status,Sale.ReconciliationStatus.POSSIBLE_DUPLICATE)

    def test_valid_and_invalid_state_transitions(self):
        validate_transition("DRAFT","READY",SALE_TRANSITIONS)
        validate_transition("SUBMITTING","UNCERTAIN",RECEIPT_TRANSITIONS)
        with self.assertRaises(ValidationError): validate_transition("ACCEPTED","PREPARED",RECEIPT_TRANSITIONS)

    def test_receipt_capability_classification_and_reconciliation(self):
        sale,_=self.operation()
        receipt=register_manual_receipt(organization=self.org,actor=self.user,sale=sale,document_type=39,folio=1,tax_issue_date=date(2026,7,11))
        sale.refresh_from_db(); self.assertEqual(receipt.status,"ACCEPTED"); self.assertEqual(sale.reconciliation_status,"RECONCILED")
        exempt,_=self.operation(classification="EXEMPT",reference="EX")
        with self.assertRaises(ValidationError): register_manual_receipt(organization=self.org,actor=self.user,sale=exempt,document_type=39,folio=2,tax_issue_date=date(2026,7,11))

    def test_accepted_receipt_is_database_immutable(self):
        sale,_=self.operation(); receipt=register_manual_receipt(organization=self.org,actor=self.user,sale=sale,document_type=39,folio=8,tax_issue_date=date(2026,7,11))
        receipt.folio=9
        with self.assertRaises(Exception):
            with transaction.atomic(): receipt.save(update_fields=["folio"])

    def test_audit_created_without_payment_reference(self):
        sale,_=self.operation(reference="PRIVATE-REFERENCE")
        event=AuditEvent.objects.get(action="manual_operation.created",target_id=sale.id)
        self.assertNotIn("PRIVATE-REFERENCE",str(event.metadata))

class AuthorizationWebTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user("accountant",password="test-password")
        self.viewer=User.objects.create_user("viewer",password="test-password")
        self.org_a=TaxpayerOrganization.objects.create(tax_id="76.100.001-1",legal_name="A")
        self.org_b=TaxpayerOrganization.objects.create(tax_id="76.100.002-K",legal_name="B")
        OrganizationMembership.objects.create(organization=self.org_a,user=self.user,role="ACCOUNTANT")
        OrganizationMembership.objects.create(organization=self.org_a,user=self.viewer,role="VIEWER")

    def test_url_tampering_cannot_access_other_organization(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("organization-period",args=[self.org_b.id,"2026-07"])).status_code,403)

    def test_viewer_cannot_post_operation(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(reverse("manual-operation",args=[self.org_a.id,"2026-07"]),{}).status_code,403)

    def test_posted_organization_id_is_ignored(self):
        self.client.force_login(self.user); key=uuid.uuid4()
        response=self.client.post(reverse("manual-operation",args=[self.org_a.id,"2026-07"]),{"organization":str(self.org_b.id),"total":1190,"payment_date":"2026-07-02","operation_date":"2026-07-01","transfer_reference":"T","detail":"Clase","classification":"TAXABLE","customer_name":"","customer_tax_id":"","observations":"","idempotency_key":str(key)})
        self.assertEqual(response.status_code,302); self.assertTrue(Sale.objects.filter(organization=self.org_a).exists()); self.assertFalse(Sale.objects.filter(organization=self.org_b).exists())

    def test_cross_tenant_sale_id_returns_not_found(self):
        other_user=User.objects.create_user("other")
        sale=Sale.objects.create(organization=self.org_b,operation_date=date(2026,7,1),detail="X",tax_classification="EXEMPT",net_amount=10,vat_amount=0,total_amount=10,origin_system="X",external_id="1",created_by=other_user)
        self.client.force_login(self.user)
        response=self.client.get(reverse("manual-receipt",args=[self.org_a.id,"2026-07",sale.id])); self.assertEqual(response.status_code,404)

    def test_form_error_preserves_values_and_has_summary(self):
        self.client.force_login(self.user)
        response=self.client.post(reverse("manual-operation",args=[self.org_a.id,"2026-07"]),{"total":"abc","operation_date":"2026-07-01","payment_date":"2026-07-01","detail":"Conservar este detalle","classification":"TAXABLE","idempotency_key":str(uuid.uuid4())})
        self.assertEqual(response.status_code,200); self.assertContains(response,"Conservar este detalle"); self.assertContains(response,"Revise los siguientes errores")

    def test_platform_admin_controlled_user_creation_hashes_password_and_assigns_tenant(self):
        admin=User.objects.create_user("platform",password="Admin-safe-987!",platform_role="PLATFORM_ADMIN")
        self.client.force_login(admin); raw="Initial-safe-987!"
        response=self.client.post(reverse("controlled-user-create",args=[self.org_a.id]),{"username":"new-user","email":"new@example.test","first_name":"Nueva","last_name":"Persona","password":raw,"role":"OPERATOR"})
        self.assertEqual(response.status_code,302)
        created=User.objects.get(username="new-user"); self.assertTrue(created.check_password(raw)); self.assertNotEqual(created.password,raw)
        self.assertTrue(OrganizationMembership.objects.filter(organization=self.org_a,user=created,role="OPERATOR").exists())
        event=AuditEvent.objects.get(action="user.controlled_created"); self.assertNotIn(raw,str(event.metadata))

class ConcurrentIdempotencyTests(TransactionTestCase):
    reset_sequences=True
    def test_concurrent_same_key_creates_one_operation(self):
        user=User.objects.create_user("concurrent"); org=TaxpayerOrganization.objects.create(tax_id="77.000.001-1",legal_name="Concurrente")
        key=uuid.uuid4(); barrier=threading.Barrier(2); results=[]
        def run():
            close_old_connections(); barrier.wait()
            try: results.append(register_manual_operation(organization=org,actor=user,operation_date=date(2026,7,1),payment_date=date(2026,7,1),total=1190,transfer_reference="R",detail="X",classification="TAXABLE",idempotency_key=key)[1])
            finally: close_old_connections()
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(Sale.objects.count(),1); self.assertEqual(Payment.objects.count(),1); self.assertEqual(sorted(results),[False,True])
