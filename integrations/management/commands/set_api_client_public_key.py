from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from integrations.models import ApiClient
from integrations.services import set_api_client_public_key


class Command(BaseCommand):
    help = "Registra o reemplaza la llave pública Ed25519 con la que un cliente firma sus requests."

    def add_arguments(self, parser):
        parser.add_argument("--origin-system", required=True)
        parser.add_argument("--public-key", required=True, help="32 bytes en base64.")

    def handle(self, *args, **options):
        client = ApiClient.objects.filter(origin_system=options["origin_system"].strip().upper()).first()
        if client is None:
            raise CommandError("Cliente inexistente.")
        try:
            set_api_client_public_key(client, options["public_key"])
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(f"Llave pública registrada para {client}.")
