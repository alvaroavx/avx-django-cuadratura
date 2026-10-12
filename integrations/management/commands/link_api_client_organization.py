from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from integrations.models import ApiClient
from integrations.services import link_api_client_organization
from organizations.models import TaxpayerOrganization


class Command(BaseCommand):
    help = "Habilita (o con --unlink deshabilita) un cliente de la API en una organización, con auditoría."

    def add_arguments(self, parser):
        parser.add_argument("--origin-system", required=True)
        parser.add_argument("--organization", required=True, metavar="UUID")
        parser.add_argument("--unlink", action="store_true")

    def handle(self, *args, **options):
        client = ApiClient.objects.filter(origin_system=options["origin_system"].strip().upper()).first()
        if client is None:
            raise CommandError("Cliente inexistente.")
        try:
            organization = TaxpayerOrganization.objects.get(pk=options["organization"])
        except (TaxpayerOrganization.DoesNotExist, ValidationError) as exc:
            raise CommandError("Organización inexistente.") from exc
        link_api_client_organization(client, organization, active=not options["unlink"])
        estado = "deshabilitado" if options["unlink"] else "habilitado"
        self.stdout.write(f"{client} {estado} en {organization}.")
