from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from accounts.models import User
from django.views.decorators.http import require_http_methods
from audit.services import record_event
from .access import ADMIN_ROLES, authorized_organization, scoped_organizations
from .forms import ControlledUserForm, InvitationForm, MembershipForm, OrganizationForm
from .models import OrganizationMembership

@login_required
def organization_list(request):
    return render(request,"organizations/list.html",{"organizations":scoped_organizations(request.user).order_by("legal_name"),"can_create":request.user.is_platform_admin})

@login_required
@require_http_methods(["GET","POST"])
def organization_create(request):
    if not request.user.is_platform_admin: raise PermissionDenied
    form=OrganizationForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        org=form.save(); record_event(organization=org,actor=request.user,action="organization.created",target=org); messages.success(request,"Contribuyente creado."); return redirect("organization-list")
    return render(request,"organizations/form.html",{"form":form,"title":"Nuevo contribuyente","organization_form":True})

@login_required
@require_http_methods(["GET","POST"])
def organization_edit(request, organization_id):
    if not request.user.is_platform_admin: raise PermissionDenied
    org=authorized_organization(request.user,organization_id,active_only=False)
    form=OrganizationForm(request.POST or None,instance=org)
    if request.method=="POST" and form.is_valid():
        form.save(); record_event(organization=org,actor=request.user,action="organization.updated",target=org,metadata={"active":org.is_active,"dte_39":org.dte_39_enabled,"dte_41":org.dte_41_enabled}); messages.success(request,"Contribuyente actualizado."); return redirect("organization-list")
    return render(request,"organizations/form.html",{"form":form,"organization":org,"title":"Configurar contribuyente","organization_form":True})

@login_required
@require_http_methods(["GET","POST"])
def invite_user(request, organization_id):
    org=authorized_organization(request.user,organization_id,roles=ADMIN_ROLES)
    form=InvitationForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        invitation,_raw=form.save_for(org,request.user); record_event(organization=org,actor=request.user,action="invitation.created",target=invitation,metadata={"role":invitation.role}); messages.success(request,"Invitación creada. El envío de correo aún no está configurado."); return redirect("organization-period-current",organization_id=org.id)
    return render(request,"organizations/form.html",{"form":form,"organization":org,"title":"Invitar usuario"})

@login_required
@require_http_methods(["GET","POST"])
def membership_create(request, organization_id):
    org=authorized_organization(request.user,organization_id,roles=ADMIN_ROLES)
    form=MembershipForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        membership=form.save(commit=False); membership.organization=org; membership.save(); record_event(organization=org,actor=request.user,action="membership.created",target=membership,metadata={"role":membership.role}); messages.success(request,"Membresía guardada."); return redirect("organization-period-current",organization_id=org.id)
    return render(request,"organizations/form.html",{"form":form,"organization":org,"title":"Equipo y permisos"})

@login_required
@require_http_methods(["GET","POST"])
def controlled_user_create(request, organization_id):
    if not request.user.is_platform_admin: raise PermissionDenied
    org=authorized_organization(request.user,organization_id,active_only=False)
    form=ControlledUserForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        data=form.cleaned_data
        with transaction.atomic():
            user=User.objects.create_user(username=data["username"],email=data["email"],first_name=data["first_name"],last_name=data["last_name"],password=data["password"])
            membership=OrganizationMembership.objects.create(organization=org,user=user,role=data["role"])
            record_event(organization=org,actor=request.user,action="user.controlled_created",target=membership,metadata={"role":membership.role})
        messages.success(request,"Usuario y membresía creados. Entregue la contraseña inicial por un canal seguro.")
        return redirect("organization-period-current",organization_id=org.id)
    return render(request,"organizations/form.html",{"form":form,"organization":org,"title":"Crear usuario"})

@login_required
def organization_administration(request, organization_id, period):
    org=authorized_organization(request.user,organization_id,roles=ADMIN_ROLES)
    month=date.fromisoformat(f"{period}-01")
    return render(request,"organizations/administration.html",{"organization":org,"period":month,"is_platform_admin":request.user.is_platform_admin})
