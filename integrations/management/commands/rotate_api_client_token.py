from django.core.management.base import BaseCommand, CommandError

from integrations.models import ApiClient
from integrations.services import rotate_api_client_token


class Command(BaseCommand):
    help = "Emite un token nuevo para un cliente de la API v1 y lo muestra una sola vez."

    def add_arguments(self, parser):
        parser.add_argument("--origin-system", required=True, help="Código de origen del cliente.")
        parser.add_argument(
            "--grace-hours",
            type=int,
            default=None,
            help="Horas que el token anterior sigue válido (0 = se corta ya; úselo si fue comprometido).",
        )
        parser.add_argument("--expires-days", type=int, default=None, help="Vigencia del token nuevo en días.")

    def handle(self, *args, **options):
        origin_system = options["origin_system"].strip().upper()
        client = ApiClient.objects.filter(origin_system=origin_system).first()
        if client is None:
            raise CommandError(f"No existe un cliente con origen {origin_system}.")
        token = rotate_api_client_token(
            client, expires_in_days=options["expires_days"], grace_hours=options["grace_hours"]
        )
        if client.previous_token_valid_until:
            self.stdout.write(
                f"Token rotado para {client}. El anterior sigue válido hasta {client.previous_token_valid_until:%Y-%m-%d %H:%M}."
            )
        else:
            self.stdout.write(f"Token rotado para {client}. El anterior dejó de funcionar.")
        self.stdout.write(token)
