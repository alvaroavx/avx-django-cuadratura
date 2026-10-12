from django.urls import path, re_path

from . import api

urlpatterns = [
    path("api/v1/", api.api_root, name="api-v1-root"),
    path("api/v1/contracts/<str:contract_version>.schema.json", api.contract_schema, name="api-v1-contract-schema"),
    path(
        "api/v1/organizations/<uuid:organization_id>/periods/<str:period>/batches/",
        api.batch_create,
        name="api-v1-batch-create",
    ),
    path(
        "api/v1/organizations/<uuid:organization_id>/periods/<str:period>/batches/<uuid:batch_id>/",
        api.batch_detail,
        name="api-v1-batch-detail",
    ),
    re_path(r"^api/(?P<unmatched>.*)$", api.not_found),
]
