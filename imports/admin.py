from django.contrib import admin
from .models import ImportBatch, ImportRow

admin.site.register([ImportBatch, ImportRow])

