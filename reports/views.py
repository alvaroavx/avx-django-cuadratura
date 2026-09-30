from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from audit.models import AuditEvent
from organizations.access import CLOSE_ROLES, READ_ROLES, authorized_organization
from .forms import CloseForm, ReopenForm
from .models import MonthlyClose
from .services import (
    close_month,
    generate_receipt_export_workbook,
    generate_workbook,
    prepare_receipt_export,
    receipt_export_filename,
    reopen_month,
)

def _month(value): return date.fromisoformat(value+"-01")

@login_required
def provisional_export(request,organization_id,period):
    org=authorized_organization(request.user,organization_id,roles=READ_ROLES); month=_month(period)
    content,_,_=generate_workbook(org,month)
    response=HttpResponse(content,content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"]=f'attachment; filename="libro-provisional-{period}.xlsx"'
    return response


@login_required
def receipt_export_preview(request, organization_id, period):
    org = authorized_organization(request.user, organization_id, roles=READ_ROLES)
    month = _month(period)
    export = prepare_receipt_export(org, month, request.GET.get("exception", ""))
    rows = [
        [value.strftime("%d/%m/%Y") if isinstance(value, date) else value for value in row]
        for row in export["rows"]
    ]
    return JsonResponse(
        {
            "organization": org.legal_name,
            "period": month.strftime("%m/%Y"),
            "headers": export["headers"],
            "rows": rows,
            "count": len(rows),
            "filter": export["filter"],
            "filter_label": export["filter_label"],
            "excluded_count": export["excluded_count"],
            "scope_note": (
                "Incluye solo boletas aceptadas. Las rechazadas, inciertas, anuladas "
                "o todavía en trámite no se exportan como ingresos válidos."
            ),
        }
    )


@login_required
def receipt_export_download(request, organization_id, period):
    org = authorized_organization(request.user, organization_id, roles=READ_ROLES)
    month = _month(period)
    content, _export = generate_receipt_export_workbook(
        org, month, request.GET.get("exception", "")
    )
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{receipt_export_filename(org, month)}"'
    )
    return response

@login_required
@require_http_methods(["GET","POST"])
def close_period(request,organization_id,period):
    org=authorized_organization(request.user,organization_id,roles=CLOSE_ROLES); month=_month(period); form=CloseForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: close=close_month(organization=org,period=month,actor=request.user,withholding=form.cleaned_data["second_category_withholding"],ppm=form.cleaned_data["ppm"])
        except ValidationError as exc: form.add_error(None,exc)
        else: messages.success(request,f"Período cerrado. SHA-256: {close.file_hash}"); return redirect("organization-period",organization_id=org.id,period=period)
    return render(request,"reports/close_form.html",{"form":form,"organization":org,"period":month})

@login_required
@require_http_methods(["GET","POST"])
def reopen_period(request,organization_id,period,close_id):
    org=authorized_organization(request.user,organization_id,roles=CLOSE_ROLES); close=get_object_or_404(MonthlyClose,pk=close_id,organization=org,period=_month(period)); form=ReopenForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: reopen_month(close=close,actor=request.user,reason=form.cleaned_data["reason"])
        except ValidationError as exc: form.add_error(None,exc)
        else: messages.success(request,"Período reabierto y auditado."); return redirect("organization-period",organization_id=org.id,period=period)
    return render(request,"reports/close_form.html",{"form":form,"organization":org,"period":close.period,"reopen":True})

@login_required
def audit_list(request,organization_id):
    org=authorized_organization(request.user,organization_id,roles=CLOSE_ROLES)
    return render(request,"reports/audit.html",{"organization":org,"period":date.today().replace(day=1),"events":AuditEvent.objects.filter(organization=org).select_related("actor")[:200]})
