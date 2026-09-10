from django.urls import path
from . import views

urlpatterns = [
    path(
        "organizaciones/<uuid:organization_id>/periodos/<str:period>/importaciones/",
        views.batch_list,
        name="import-list",
    ),
    path(
        "organizaciones/<uuid:organization_id>/periodos/<str:period>/importaciones/nueva/",
        views.batch_create,
        name="import-create",
    ),
    path(
        "organizaciones/<uuid:organization_id>/periodos/<str:period>/importaciones/<uuid:batch_id>/",
        views.batch_preview,
        name="import-preview",
    ),
    path(
        "organizaciones/<uuid:organization_id>/periodos/<str:period>/importaciones/<uuid:batch_id>/confirmar/",
        views.batch_commit,
        name="import-commit",
    ),
]

