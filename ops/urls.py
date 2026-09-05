from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("organization-requests", views.OrganizationRequestViewSet, basename="organization-request")
router.register("organizations", views.OrganizationViewSet, basename="organization")
router.register("projects", views.ProjectViewSet, basename="project")
router.register("tasks", views.TaskViewSet, basename="task")
router.register("uat-observations", views.UATObservationViewSet, basename="uat-observation")
router.register("leave", views.LeaveRequestViewSet, basename="leave")

urlpatterns = [
    path("auth/csrf/", views.csrf),
    path("auth/register/", views.register),
    path("auth/login/", views.sign_in),
    path("auth/logout/", views.sign_out),
    path("auth/session/", views.session),
    path("", include(router.urls)),
]
