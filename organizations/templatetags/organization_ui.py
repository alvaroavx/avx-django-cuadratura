from django import template
from organizations.models import OrganizationMembership

register = template.Library()


@register.simple_tag
def organization_access(user, organization):
    if not user.is_authenticated or not organization:
        return {"role": "", "can_import": False, "can_close": False, "can_admin": False}
    if user.is_platform_admin:
        return {
            "role": "Administrador de plataforma",
            "can_import": True,
            "can_close": True,
            "can_admin": True,
        }
    membership = OrganizationMembership.objects.filter(
        organization=organization, user=user, is_active=True
    ).first()
    if not membership:
        return {"role": "", "can_import": False, "can_close": False, "can_admin": False}
    return {
        "role": membership.get_role_display(),
        "can_import": membership.role
        in {OrganizationMembership.Role.ORGANIZATION_ADMIN, OrganizationMembership.Role.ACCOUNTANT},
        "can_close": membership.role
        in {OrganizationMembership.Role.ORGANIZATION_ADMIN, OrganizationMembership.Role.ACCOUNTANT},
        "can_admin": membership.role == OrganizationMembership.Role.ORGANIZATION_ADMIN,
    }

