from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Cuadratura", {"fields": ("platform_role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Cuadratura", {"fields": ("platform_role",)}),)

