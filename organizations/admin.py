from django.contrib import admin
from .models import OrganizationMembership, TaxpayerOrganization, UserInvitation
admin.site.register([TaxpayerOrganization, OrganizationMembership, UserInvitation])

