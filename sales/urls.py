from django.urls import path
from . import views
urlpatterns=[
 path("organizaciones/<uuid:organization_id>/periodos/actual/",views.current_period,name="organization-period-current"),
 path("organizaciones/<uuid:organization_id>/periodos/<str:period>/",views.period_dashboard,name="organization-period"),
 path("organizaciones/<uuid:organization_id>/periodos/<str:period>/operaciones/nueva/",views.manual_operation,name="manual-operation"),
 path("organizaciones/<uuid:organization_id>/periodos/<str:period>/ventas/<uuid:sale_id>/boleta/",views.manual_receipt,name="manual-receipt"),
]

