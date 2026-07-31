from django.urls import path
from . import views
urlpatterns=[
 path("organizaciones/<uuid:organization_id>/periodos/<str:period>/exportar/",views.provisional_export,name="provisional-export"),
 path("organizaciones/<uuid:organization_id>/periodos/<str:period>/cerrar/",views.close_period,name="close-period"),
 path("organizaciones/<uuid:organization_id>/periodos/<str:period>/cierres/<uuid:close_id>/reabrir/",views.reopen_period,name="reopen-period"),
 path("organizaciones/<uuid:organization_id>/auditoria/",views.audit_list,name="audit-list"),
]

