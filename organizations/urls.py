from django.urls import path
from . import views
urlpatterns=[
 path("",views.organization_list,name="organization-list"),
 path("organizaciones/nueva/",views.organization_create,name="organization-create"),
 path("organizaciones/<uuid:organization_id>/editar/",views.organization_edit,name="organization-edit"),
 path("organizaciones/<uuid:organization_id>/invitar/",views.invite_user,name="organization-invite"),
 path("organizaciones/<uuid:organization_id>/membresias/nueva/",views.membership_create,name="membership-create"),
 path("organizaciones/<uuid:organization_id>/usuarios/alta-controlada/",views.controlled_user_create,name="controlled-user-create"),
]
