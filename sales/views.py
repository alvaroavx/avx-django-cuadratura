from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from documents.models import ElectronicReceipt
from organizations.access import CLOSE_ROLES, READ_ROLES, WRITE_ROLES, authorized_organization
from organizations.models import OrganizationMembership
from reports.models import MonthlyClose
from .forms import ManualOperationForm, ReceiptForm
from .models import Sale
from .services import calculate_tax_preview, register_manual_operation, register_manual_receipt

def _period(value):
    try: parsed=date.fromisoformat(value+"-01")
    except ValueError: raise ValidationError("Período inválido.")
    return parsed

@login_required
def current_period(request,organization_id):
    today=date.today(); return redirect("organization-period",organization_id=organization_id,period=f"{today:%Y-%m}")

@login_required
def period_dashboard(request,organization_id,period):
    org=authorized_organization(request.user,organization_id,roles=READ_ROLES); month=_period(period)
    sales=Sale.objects.filter(organization=org,operation_date__year=month.year,operation_date__month=month.month).prefetch_related("payments","receipts")
    receipts=ElectronicReceipt.objects.filter(organization=org,tax_issue_date__year=month.year,tax_issue_date__month=month.month)
    total_received=sales.aggregate(v=Sum("payments__amount"))["v"] or 0
    accepted=receipts.filter(status=ElectronicReceipt.Status.ACCEPTED)
    total_documented=accepted.aggregate(v=Sum("total_amount"))["v"] or 0
    summary={"received":total_received,"documented":total_documented,"difference":total_received-total_documented,"taxable":accepted.filter(document_type=39).aggregate(v=Sum("total_amount"))["v"] or 0,"exempt":accepted.filter(document_type=41).aggregate(v=Sum("total_amount"))["v"] or 0,"vat":accepted.aggregate(v=Sum("vat_amount"))["v"] or 0,"pending":sales.exclude(status=Sale.Status.DOCUMENTED).count(),"accepted":accepted.count(),"rejected":receipts.filter(status=ElectronicReceipt.Status.REJECTED).count(),"uncertain":receipts.filter(status=ElectronicReceipt.Status.UNCERTAIN).count()}
    close=MonthlyClose.objects.filter(organization=org,period=month).order_by("-version").first()
    role=None if request.user.is_platform_admin else OrganizationMembership.objects.filter(organization=org,user=request.user,is_active=True).values_list("role",flat=True).first()
    return render(request,"sales/dashboard.html",{"organization":org,"period":month,"sales":sales,"summary":summary,"close":close,"can_write":request.user.is_platform_admin or role in WRITE_ROLES,"can_close":request.user.is_platform_admin or role in CLOSE_ROLES,"can_admin":request.user.is_platform_admin or role==OrganizationMembership.Role.ORGANIZATION_ADMIN,"is_platform_admin":request.user.is_platform_admin})

@login_required
@require_http_methods(["GET","POST"])
def manual_operation(request,organization_id,period):
    org=authorized_organization(request.user,organization_id,roles=WRITE_ROLES); month=_period(period)
    if MonthlyClose.objects.filter(organization=org,period=month,status=MonthlyClose.Status.CLOSED).exists(): raise PermissionDenied("El período está cerrado.")
    form=ManualOperationForm(request.POST or None,initial={"operation_date":date.today(),"payment_date":date.today()})
    preview=None
    if request.method=="POST" and form.is_valid():
        d=form.cleaned_data
        if d["operation_date"].year!=month.year or d["operation_date"].month!=month.month: form.add_error("operation_date","La fecha debe pertenecer al período activo.")
        else:
            sale,created=register_manual_operation(organization=org,actor=request.user,**d)
            messages.success(request,"Operación guardada." if created else "El envío duplicado ya había sido guardado.")
            if request.POST.get("save_and_add"): return redirect("manual-operation",organization_id=org.id,period=period)
            return redirect("organization-period",organization_id=org.id,period=period)
    if form.is_bound and form.data.get("total") and form.data.get("classification"):
        try: preview=calculate_tax_preview(int(form.data["total"]),form.data["classification"])
        except (ValueError,ValidationError): pass
    return render(request,"sales/manual_form.html",{"form":form,"organization":org,"period":month,"preview":preview})

@login_required
@require_http_methods(["GET","POST"])
def manual_receipt(request,organization_id,period,sale_id):
    org=authorized_organization(request.user,organization_id,roles=WRITE_ROLES); month=_period(period)
    if MonthlyClose.objects.filter(organization=org,period=month,status=MonthlyClose.Status.CLOSED).exists(): raise PermissionDenied("El período está cerrado.")
    sale=get_object_or_404(Sale,pk=sale_id,organization=org)
    form=ReceiptForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: register_manual_receipt(organization=org,actor=request.user,sale=sale,**form.cleaned_data)
        except ValidationError as exc: form.add_error(None,exc)
        else: messages.success(request,"Boleta aceptada registrada y conciliación actualizada."); return redirect("organization-period",organization_id=org.id,period=period)
    return render(request,"sales/receipt_form.html",{"form":form,"organization":org,"period":month,"sale":sale})
