from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from integrations.services import create_api_client
from organizations.models import TaxpayerOrganization


class Command(BaseCommand):
    help = "Crea un cliente de la API v1 y muestra su token una sola vez."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Nombre visible, p. ej. 'Plataforma Elemental'.")
        parser.add_argument("--origin-system", required=True, help="Código de origen, p. ej. ELEMENTAL.")
        parser.add_argument(
            "--organization",
            action="append",
            default=[],
            metavar="UUID",
            help="Organización habilitada para el cliente; puede repetirse.",
        )
        parser.add_argument(
            "--public-key",
            default="",
            help="Llave pública Ed25519 del cliente (32 bytes en base64). Obligatoria si se exigen firmas.",
        )
        parser.add_argument(
            "--expires-days", type=int, default=None, help="Vigencia del token en días (0 = sin vencimiento)."
        )

    def handle(self, *args, **options):
        organizations = []
        for organization_id in options["organization"]:
            try:
                organizations.append(TaxpayerOrganization.objects.get(pk=organization_id))
            except (TaxpayerOrganization.DoesNotExist, ValidationError) as exc:
                raise CommandError(f"Organización inexistente: {organization_id}") from exc
        try:
            client, token = create_api_client(
                name=options["name"],
                origin_system=options["origin_system"],
                organizations=organizations,
                public_key=options["public_key"],
                expires_in_days=options["expires_days"],
            )
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(f"Cliente creado: {client} con {len(organizations)} organización(es).")
        if client.token_expires_at:
            self.stdout.write(f"El token vence el {client.token_expires_at:%Y-%m-%d}.")
        if not client.public_key:
            self.stdout.write("Sin llave pública: el cliente no podrá llamar a la API si se exigen firmas.")
        self.stdout.write("Token (se muestra una sola vez; guárdelo en el gestor de secretos del cliente):")
        self.stdout.write(token)
