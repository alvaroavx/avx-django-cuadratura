from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from audit.services import record_event
from organizations.access import IMPORT_ROLES, authorized_organization
from reports.models import MonthlyClose
from .forms import CsvUploadForm
from .models import ImportBatch, ImportRow
from .services import commit_batch, create_preview_batch


def _period(value):
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise ValidationError("Período inválido.") from exc


@login_required
def batch_list(request, organization_id, period):
    organization = authorized_organization(request.user, organization_id, roles=IMPORT_ROLES)
    month = _period(period)
    batches = ImportBatch.objects.filter(organization=organization, period=month).select_related(
        "uploaded_by"
    )
    return render(
        request,
        "imports/list.html",
        {"organization": organization, "period": month, "batches": batches},
    )


@login_required
@require_http_methods(["GET", "POST"])
def batch_create(request, organization_id, period):
    organization = authorized_organization(request.user, organization_id, roles=IMPORT_ROLES)
    month = _period(period)
    closed = MonthlyClose.objects.filter(
        organization=organization, period=month, status=MonthlyClose.Status.CLOSED
    ).exists()
    form = CsvUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            batch, created = create_preview_batch(
                organization=organization,
                expected_period=month,
                actor=request.user,
                uploaded_file=form.cleaned_data["file"],
            )
        except ValidationError as exc:
            form.add_error("file", exc)
        else:
            if not created:
                messages.info(request, "Este archivo ya había sido cargado; se muestra el lote existente.")
            return redirect(
                "import-preview",
                organization_id=organization.id,
                period=period,
                batch_id=batch.id,
            )
    return render(
        request,
        "imports/upload.html",
        {"organization": organization, "period": month, "form": form, "closed": closed},
    )


@login_required
def batch_preview(request, organization_id, period, batch_id):
    organization = authorized_organization(request.user, organization_id, roles=IMPORT_ROLES)
    month = _period(period)
    batch = get_object_or_404(
        ImportBatch.objects.prefetch_related("rows"),
        pk=batch_id,
        organization=organization,
        period=month,
    )
    rows = list(batch.rows.all())
    groups = [
        (label, [row for row in rows if row.status == status])
        for status, label in (
            (ImportRow.Status.NEW, "Filas nuevas"),
            (ImportRow.Status.ALREADY_IMPORTED, "Ya existentes e idénticas"),
            (ImportRow.Status.CONFLICT, "Conflictos"),
            (ImportRow.Status.ERROR, "Errores"),
            (ImportRow.Status.IMPORTED, "Filas importadas"),
        )
    ]
    return render(
        request,
        "imports/preview.html",
        {"organization": organization, "period": month, "batch": batch, "groups": groups},
    )


@login_required
@require_POST
def batch_commit(request, organization_id, period, batch_id):
    organization = authorized_organization(request.user, organization_id, roles=IMPORT_ROLES)
    month = _period(period)
    batch = get_object_or_404(ImportBatch, pk=batch_id, organization=organization, period=month)
    record_event(
        organization=organization,
        actor=request.user,
        action="import.confirmation_requested",
        target=batch,
        metadata={"period": month.isoformat()},
    )
    try:
        committed_batch, created = commit_batch(
            batch_id=batch.id, organization=organization, actor=request.user
        )
    except ValidationError as exc:
        record_event(
            organization=organization,
            actor=request.user,
            action="import.commit_blocked",
            target=batch,
            metadata={"status": batch.status},
        )
        messages.error(request, str(exc))
    else:
        if created:
            messages.success(
                request,
                f"Importación confirmada: {committed_batch.new_rows} operaciones creadas sin inventar pagos.",
            )
        else:
            messages.info(request, "La importación ya había sido confirmada.")
    return redirect(
        "import-preview", organization_id=organization.id, period=period, batch_id=batch.id
    )
