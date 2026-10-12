import base64
import io
import json
import secrets
import tempfile
import time
from datetime import date, timedelta
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from imports.models import ImportBatch
from imports.services import commit_batch
from audit.models import AuditEvent
from integrations.models import ApiAccessFailure, ApiClient
from integrations.security import signing_message
from integrations.services import create_api_client, rotate_api_client_token
from organizations.models import TaxpayerOrganization
from payments.models import Payment
from reports.models import MonthlyClose
from sales.models import Sale


def new_keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, base64.b64encode(public).decode()


def signed_headers(private_key, method, path, body=b"", *, timestamp=None, nonce=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or secrets.token_urlsafe(18)
    signature = private_key.sign(signing_message(method, path, timestamp, nonce, body))
    return {
        "HTTP_X_CUADRATURA_TIMESTAMP": timestamp,
        "HTTP_X_CUADRATURA_NONCE": nonce,
        "HTTP_X_CUADRATURA_SIGNATURE": base64.b64encode(signature).decode(),
    }


SECURE_API = {
    "API_REQUIRE_HTTPS": False,
    "API_REQUIRE_SIGNATURES": True,
    "API_RATE_LIMIT_PER_MINUTE": 60,
    "API_AUTH_FAILURE_LIMIT": 10,
    "API_AUTH_FAILURE_WINDOW_MINUTES": 15,
}


@override_settings(**SECURE_API)
class ApiTestBase(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.org = TaxpayerOrganization.objects.create(
            tax_id="77.111.222-3", legal_name="Taller Ficticio SpA", dte_39_enabled=True, dte_41_enabled=True
        )
        self.other_org = TaxpayerOrganization.objects.create(tax_id="76.000.000-0", legal_name="Otra SpA")
        self.private_key, public_key = new_keypair()
        self.client_api, self.token = create_api_client(
            name="Sistema Ficticio", origin_system="FICTICIO", organizations=[self.org], public_key=public_key
        )
        self.reviewer = User.objects.create_user("revisora")

    def url(self, org=None, period="2026-09"):
        return f"/api/v1/organizations/{(org or self.org).id}/periods/{period}/batches/"

    def document(self, *, batch_id="lote-1", detail="Taller ficticio", total=50000, vat=7983, period="2026-09"):
        net = total - vat
        return {
            "contract_version": "cuadratura-operations-v1",
            "batch_id": batch_id,
            "generated_at": "2026-10-01T09:00:00-03:00",
            "period": period,
            "taxpayer": {"tax_id": self.org.tax_id, "legal_name": self.org.legal_name},
            "source": {"organization_id": "org:1", "name": "Taller Ficticio"},
            "operations": [{
                "external_id": "op:1", "operation_date": "2026-09-03", "service_period": "2026-09",
                "detail": detail, "customer_name": "Persona Ficticia",
                "tax": {"classification": "TAXABLE" if vat else "EXEMPT", "net": net, "vat": vat, "total": total},
                "payments": [{"external_id": "pay:1", "payment_date": "2026-09-03", "amount": total, "reference": "REF-1"}],
            }],
            "excluded_records": [{"external_id": "pay:9", "reasons": ["payment_reversed"]}],
            "summary": {"operations": 1, "payments": 1, "total_amount": total},
        }

    def post(self, document, *, token=None, org=None, period="2026-09", key=None, **extra):
        url = self.url(org, period)
        body = document if isinstance(document, bytes) else json.dumps(document).encode()
        headers = signed_headers(key or self.private_key, "POST", url, body)
        headers.update(extra)
        return self.client.post(
            url, data=body, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}", **headers,
        )

    def get(self, url, *, token=None, key=None):
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        return self.client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {token or self.token}",
            **signed_headers(key or self.private_key, "GET", path),
        )


class ApiV1Tests(ApiTestBase):
    def test_discovery_is_public_and_lists_linked_organizations_with_token(self):
        public = self.client.get("/api/v1/").json()
        self.assertEqual((public["service"], public["api_version"]), ("cuadratura", "v1"))
        self.assertNotIn("organizations", public)
        self.assertEqual(public["contracts"][0]["version"], "cuadratura-operations-v1")
        private = self.get("/api/v1/").json()
        self.assertEqual(private["client"]["origin_system"], "FICTICIO")
        self.assertEqual([org["tax_id"] for org in private["organizations"]], [self.org.tax_id])
        schema = self.client.get(public["contracts"][0]["schema"])
        self.assertEqual(schema.status_code, 200)
        self.assertEqual(json.loads(schema.content)["$id"], "cuadratura-operations-v1")

    def test_authentication_is_required_and_tokens_are_not_stored(self):
        self.assertEqual(self.client.post(self.url(), data="{}", content_type="application/json").status_code, 401)
        self.assertEqual(ApiAccessFailure.objects.get().reason, "missing_token")
        self.assertEqual(self.post(self.document(), token="cdr_bad_token").status_code, 401)
        self.assertNotIn(self.token, self.client_api.token_digest)
        old = self.token
        new = rotate_api_client_token(self.client_api, grace_hours=0)
        self.assertEqual(self.post(self.document(), token=old).status_code, 401)
        self.assertEqual(self.post(self.document(), token=new).status_code, 201)
        ApiClient.objects.filter(pk=self.client_api.pk).update(is_active=False)
        self.assertEqual(self.post(self.document(batch_id="lote-2"), token=new).status_code, 401)
        self.assertFalse(self.client_api.service_user.is_active)
        self.assertFalse(self.client_api.service_user.has_usable_password())

    def test_batch_stays_in_review_and_human_commit_uses_client_origin(self):
        response = self.post(self.document())
        self.assertEqual(response.status_code, 201)
        batch = response.json()["batch"]
        self.assertEqual((batch["status"], batch["counts"]["new"], batch["counts"]["excluded"]), ("VALIDATED", 1, 1))
        self.assertEqual(batch["totals"], {"net": 42017, "vat": 7983, "total": 50000})
        self.assertEqual(response["Location"], batch["links"]["self"])
        self.assertEqual(Sale.objects.count(), 0)
        stored = ImportBatch.objects.get(pk=batch["id"])
        self.assertEqual(stored.uploaded_by, self.client_api.service_user)
        commit_batch(batch_id=stored.id, organization=self.org, actor=self.reviewer)
        sale = Sale.objects.get()
        self.assertEqual((sale.origin_system, sale.external_id, sale.created_by), ("FICTICIO", "op:1", self.reviewer))
        self.assertEqual(Payment.objects.get().origin_system, "FICTICIO")
        detail = self.get(batch["links"]["self"]).json()
        self.assertEqual(detail["batch"]["status"], "COMMITTED")

    def test_batch_id_is_idempotency_key(self):
        first = self.post(self.document())
        resend = self.document()
        resend["generated_at"] = "2026-10-02T10:00:00-03:00"
        again = self.post(resend)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["batch"]["id"], first.json()["batch"]["id"])
        conflict = self.post(self.document(detail="Otro detalle"))
        self.assertEqual((conflict.status_code, conflict.json()["error"]["code"]), (409, "batch_id_conflict"))
        self.assertEqual(ImportBatch.objects.count(), 1)

    def test_blocked_batch_reports_errors_and_can_be_resent(self):
        document = self.document()
        document["taxpayer"]["tax_id"] = self.other_org.tax_id
        blocked = self.post(document)
        self.assertEqual(blocked.status_code, 201)
        self.assertEqual(blocked.json()["batch"]["status"], "BLOCKED")
        self.assertTrue(blocked.json()["batch"]["errors"])
        fixed = self.post(self.document())
        self.assertEqual((fixed.status_code, fixed.json()["batch"]["status"]), (201, "VALIDATED"))

    def test_invalid_documents_are_rejected_with_clear_errors(self):
        bad_amounts = self.document()
        bad_amounts["operations"][0]["tax"]["vat"] = 1
        response = self.post(bad_amounts)
        self.assertEqual(response.json()["batch"]["status"], "BLOCKED")
        self.assertIn("neto + IVA", response.json()["batch"]["rows"][0]["messages"][0])
        wrong_version = self.document()
        wrong_version["contract_version"] = "elemental-cuadratura-v1"
        self.assertEqual(self.post(wrong_version).json()["error"]["code"], "invalid_document")
        self.assertEqual(self.post(b"{").status_code, 400)
        form_body = b"a=b"
        form = self.client.post(
            self.url(), data=form_body, content_type="application/x-www-form-urlencoded",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            **signed_headers(self.private_key, "POST", self.url(), form_body),
        )
        self.assertEqual(form.status_code, 415)
        reasons = self.document()
        reasons["excluded_records"] = [{"external_id": "x", "reasons": "texto"}]
        self.assertEqual(self.post(reasons).json()["error"]["code"], "invalid_document")
        self.assertEqual(self.post(self.document(), period="2026-13").status_code, 400)

    def test_organization_scope_and_closed_period(self):
        self.assertEqual(self.post(self.document(), org=self.other_org).status_code, 403)
        MonthlyClose.objects.create(organization=self.org, period=date(2026, 9, 1), version=1, status="CLOSED")
        closed = self.post(self.document())
        self.assertEqual((closed.status_code, closed.json()["error"]["code"]), (409, "period_closed"))

    def test_other_clients_cannot_read_batches(self):
        batch_url = self.post(self.document()).json()["batch"]["links"]["self"]
        other_key, other_public = new_keypair()
        _, other_token = create_api_client(
            name="Otro", origin_system="OTRO", organizations=[self.org], public_key=other_public
        )
        self.assertEqual(self.get(batch_url, token=other_token, key=other_key).status_code, 404)

    def test_create_api_client_command_prints_token_once(self):
        out = io.StringIO()
        key, public = new_keypair()
        call_command(
            "create_api_client", "--name", "Comando", "--origin-system", "comando",
            "--organization", str(self.org.id), "--public-key", public, stdout=out,
        )
        token = out.getvalue().strip().splitlines()[-1]
        self.assertTrue(token.startswith("cdr_"))
        client = ApiClient.objects.get(origin_system="COMANDO")
        self.assertNotEqual(client.token_digest, token)
        self.assertEqual(self.get("/api/v1/", token=token, key=key).status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(action="api_client.created", organization=self.org).exists())

    def test_reserved_origins_are_refused(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            create_api_client(name="Manual", origin_system="MANUAL")


@override_settings(**SECURE_API)
class ApiV1SecurityTests(ApiTestBase):
    """Controles de ADR 0006."""

    def test_signature_is_second_factor(self):
        stolen = self.post(self.document(), key=new_keypair()[0])
        self.assertEqual((stolen.status_code, stolen.json()["error"]["code"]), (401, "invalid_signature"))
        unsigned = self.client.post(
            self.url(), data=json.dumps(self.document()), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(unsigned.json()["error"]["code"], "invalid_signature")
        tampered = self.post(self.document(), HTTP_X_CUADRATURA_TIMESTAMP=str(int(time.time()) - 10))
        self.assertEqual(tampered.json()["error"]["code"], "invalid_signature")
        stale_headers = signed_headers(self.private_key, "POST", self.url(), b"{}", timestamp=int(time.time()) - 3600)
        stale = self.client.post(
            self.url(), data=b"{}", content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}", **stale_headers,
        )
        self.assertEqual(stale.json()["error"]["code"], "stale_request")
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_replayed_request_is_rejected_and_signature_is_kept_as_evidence(self):
        body = json.dumps(self.document()).encode()
        headers = signed_headers(self.private_key, "POST", self.url(), body)
        send = lambda: self.client.post(  # noqa: E731
            self.url(), data=body, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}", **headers,
        )
        first = send()
        self.assertEqual(first.status_code, 201)
        evidence = ImportBatch.objects.get().source_metadata["signature"]
        self.assertEqual(evidence["signature"], headers["HTTP_X_CUADRATURA_SIGNATURE"])
        self.assertEqual(evidence["public_key"], self.client_api.public_key)
        replay = send()
        self.assertEqual(replay.json()["error"]["code"], "replayed_request")

    def test_client_without_public_key_cannot_call_when_signatures_required(self):
        _, token = create_api_client(name="Sin llave", origin_system="SINLLAVE", organizations=[self.org])
        response = self.client.get("/api/v1/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.json()["error"]["code"], "signature_required")
        with override_settings(API_REQUIRE_SIGNATURES=False):
            self.assertEqual(self.client.get("/api/v1/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 200)

    def test_failures_are_recorded_without_secrets_and_ip_gets_blocked(self):
        for _ in range(10):
            self.post(self.document(), token="cdr_abcd1234_secreto-falso")
        failure = ApiAccessFailure.objects.first()
        self.assertEqual((failure.reason, failure.token_prefix, failure.ip_address), ("invalid_token", "abcd1234", "127.0.0.1"))
        self.assertFalse(ApiAccessFailure.objects.filter(token_prefix__contains="secreto").exists())
        blocked = self.post(self.document())
        self.assertEqual((blocked.status_code, blocked.json()["error"]["code"]), (429, "too_many_failures"))
        self.assertEqual(blocked["Retry-After"], "900")
        self.assertEqual(ApiAccessFailure.objects.count(), 10)

    @override_settings(API_RATE_LIMIT_PER_MINUTE=2)
    def test_rate_limit_per_client(self):
        self.assertEqual(self.get("/api/v1/").status_code, 200)
        self.assertEqual(self.get("/api/v1/").status_code, 200)
        limited = self.get("/api/v1/")
        self.assertEqual((limited.status_code, limited.json()["error"]["code"]), (429, "rate_limited"))
        self.assertTrue(limited["Retry-After"])
        self.assertTrue(ApiAccessFailure.objects.filter(reason="rate_limited", client=self.client_api).exists())

    def test_expired_token_and_rotation_grace(self):
        ApiClient.objects.filter(pk=self.client_api.pk).update(token_expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.get("/api/v1/").json()["error"]["code"], "expired_token")
        self.client_api.refresh_from_db()
        old = self.token
        ApiClient.objects.filter(pk=self.client_api.pk).update(token_expires_at=None)
        self.client_api.refresh_from_db()
        new = rotate_api_client_token(self.client_api, grace_hours=24)
        self.assertEqual(self.get("/api/v1/", token=old).status_code, 200)
        self.assertEqual(self.get("/api/v1/", token=new).status_code, 200)
        ApiClient.objects.filter(pk=self.client_api.pk).update(previous_token_valid_until=timezone.now())
        self.assertEqual(self.get("/api/v1/", token=old).status_code, 401)
        self.assertTrue(AuditEvent.objects.filter(action="api_client.token_rotated").exists())

    @override_settings(API_REQUIRE_HTTPS=True)
    def test_https_is_required(self):
        response = self.get("/api/v1/")
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (403, "https_required"))
        self.assertEqual(self.client.get("/api/v1/", secure=True).status_code, 200)

    def test_only_one_active_batch_per_origin_and_period(self):
        self.assertEqual(self.post(self.document()).status_code, 201)
        second = self.post(self.document(batch_id="lote-distinto", detail="Otro contenido"))
        self.assertEqual((second.status_code, second.json()["error"]["code"]), (409, "period_already_submitted"))
        self.assertEqual(self.post(self.document(batch_id="lote-octubre", period="2026-10"), period="2026-10").status_code, 201)

    def test_org_not_allowed_is_recorded(self):
        self.post(self.document(), org=self.other_org)
        self.assertTrue(ApiAccessFailure.objects.filter(reason="organization_not_allowed", client=self.client_api).exists())
