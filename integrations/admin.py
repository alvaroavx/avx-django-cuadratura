from django.contrib import admin

from .models import ApiAccessFailure, ApiClient, ApiClientOrganization


class ApiClientOrganizationInline(admin.TabularInline):
    """Solo lectura: los vínculos se cambian con `link_api_client_organization`, que audita."""

    model = ApiClientOrganization
    extra = 0
    fields = ("organization", "is_active", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApiClient)
class ApiClientAdmin(admin.ModelAdmin):
    """Alta, llaves, vínculos y tokens solo por comando, para que queden auditados y el
    token nunca pase por la web. Desde aquí solo se puede desactivar un cliente."""

    list_display = ("name", "origin_system", "is_active", "token_expires_at", "last_used_at")
    fields = (
        "name",
        "origin_system",
        "is_active",
        "service_user",
        "token_prefix",
        "token_expires_at",
        "token_rotated_at",
        "previous_token_prefix",
        "previous_token_valid_until",
        "public_key",
        "created_at",
        "last_used_at",
    )
    readonly_fields = tuple(field for field in fields if field != "is_active")
    inlines = [ApiClientOrganizationInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApiAccessFailure)
class ApiAccessFailureAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "reason", "ip_address", "client", "token_prefix", "method", "path")
    list_filter = ("reason", "client")
    search_fields = ("ip_address", "token_prefix")
    readonly_fields = tuple(field.name for field in ApiAccessFailure._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
