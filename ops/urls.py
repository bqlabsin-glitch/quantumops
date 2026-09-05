from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("organization-requests", views.OrganizationRequestViewSet, basename="organization-request")
router.register("organizations", views.OrganizationViewSet, basename="organization")
router.register("clients", views.ClientAccountViewSet, basename="client")
router.register("teams", views.TeamViewSet, basename="team")
router.register("projects", views.ProjectViewSet, basename="project")
router.register("project-members", views.ProjectMembershipViewSet, basename="project-member")
router.register("tasks", views.TaskViewSet, basename="task")
router.register("task-testers", views.TaskTesterViewSet, basename="task-tester")
router.register("uat-observations", views.UATObservationViewSet, basename="uat-observation")
router.register("leave", views.LeaveRequestViewSet, basename="leave")

urlpatterns = [
    path("auth/csrf/", views.csrf),
    path("auth/registration-otp/", views.request_registration_otp),
    path("auth/register/", views.register),
    path("auth/login/", views.sign_in),
    path("auth/logout/", views.sign_out),
    path("auth/session/", views.session),
    path("people/", views.people),
    path("invitations/", views.invite),
    path("invitations/accept/", views.accept_invitation),
    path("platform-admin/summary/", views.platform_admin_summary),
    path("platform-admin/email/", views.platform_email_settings),
    path("platform-admin/email/test/", views.platform_email_test),
    path("platform-admin/users/<int:user_id>/status/", views.platform_admin_user_status),
    path("", include(router.urls)),
]
