from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.models import ApiAccessFailure, ApiRateCounter, ApiRequestNonce


class Command(BaseCommand):
    help = "Elimina intentos fallidos, contadores y nonces vencidos según la política de retención."

    def add_arguments(self, parser):
        parser.add_argument(
            "--failure-days", type=int, default=180, help="Días que se conservan los intentos fallidos."
        )

    def handle(self, *args, **options):
        now = timezone.now()
        failures, _ = ApiAccessFailure.objects.filter(
            occurred_at__lt=now - timedelta(days=options["failure_days"])
        ).delete()
        counters, _ = ApiRateCounter.objects.filter(window_start__lt=now - timedelta(days=1)).delete()
        nonces, _ = ApiRequestNonce.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
        self.stdout.write(f"Eliminados: {failures} intentos fallidos, {counters} contadores, {nonces} nonces.")
