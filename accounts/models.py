import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class PlatformRole(models.TextChoices):
        PLATFORM_ADMIN = "PLATFORM_ADMIN", "Administrador de plataforma"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform_role = models.CharField(max_length=32, choices=PlatformRole.choices, blank=True)

    @property
    def is_platform_admin(self):
        return self.is_superuser or self.platform_role == self.PlatformRole.PLATFORM_ADMIN

