from django.contrib import admin
from .models import Sale, SaleLine
admin.site.register([Sale, SaleLine])

