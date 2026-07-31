from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import OrganizationMembership, TaxpayerOrganization

READ_ROLES = set(OrganizationMembership.Role.values)
WRITE_ROLES = {OrganizationMembership.Role.ORGANIZATION_ADMIN, OrganizationMembership.Role.ACCOUNTANT, OrganizationMembership.Role.OPERATOR}
CLOSE_ROLES = {OrganizationMembership.Role.ORGANIZATION_ADMIN, OrganizationMembership.Role.ACCOUNTANT}
ADMIN_ROLES = {OrganizationMembership.Role.ORGANIZATION_ADMIN}

def authorized_organization(user, organization_id, *, roles=None, active_only=True):
    organization = get_object_or_404(TaxpayerOrganization, pk=organization_id)
    if active_only and not organization.is_active: raise PermissionDenied("Organización inactiva")
    if user.is_platform_admin: return organization
    allowed = roles or READ_ROLES
    if not OrganizationMembership.objects.filter(organization=organization, user=user, is_active=True, role__in=allowed).exists():
        raise PermissionDenied("No tiene acceso a esta organización")
    return organization

def scoped_organizations(user):
    if user.is_platform_admin: return TaxpayerOrganization.objects.all()
    return TaxpayerOrganization.objects.filter(memberships__user=user, memberships__is_active=True).distinct()

