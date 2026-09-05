from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from django.core import mail
from urllib.parse import parse_qs, urlparse
from rest_framework.test import APIClient

from .models import ClientAccount, EmailVerificationChallenge, Membership, Organization, Project, ProjectMembership, Task, TaskTester, Team, UATObservation

User = get_user_model()


@override_settings(REST_FRAMEWORK={
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework.authentication.SessionAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
})
class AuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="Strong-pass-937!")
        self.member = User.objects.create_user("member", password="Strong-pass-937!")
        self.client_user = User.objects.create_user("client", password="Strong-pass-937!")
        self.outsider = User.objects.create_user("outsider", password="Strong-pass-937!")
        self.org = Organization.objects.create(name="BQ Labs", slug="bq-labs")
        Membership.objects.create(organization=self.org, user=self.owner, role=Membership.Role.OWNER)
        self.team = Team.objects.create(organization=self.org, name="Product", owner=self.owner, lead=self.owner)
        self.project = Project.objects.create(organization=self.org, team=self.team, name="Quantum OPS", code="QOP", visibility=Project.Visibility.SUMMARY)
        ProjectMembership.objects.create(project=self.project, user=self.member, role=ProjectMembership.Role.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.client_user, role=ProjectMembership.Role.CLIENT)
        self.task = Task.objects.create(project=self.project, sequence=1, title="Private detail", description="Internal implementation", owner=self.owner, assignee=self.member, assignment_status=Task.AssignmentStatus.PENDING)

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_outsider_cannot_see_project_or_tasks(self):
        self.assertEqual(self.api(self.outsider).get("/api/projects/").json()["count"], 0)
        self.assertEqual(self.api(self.outsider).get("/api/tasks/").json()["count"], 0)

    def test_summary_client_cannot_see_internal_fields_or_edit(self):
        api = self.api(self.client_user)
        item = api.get(f"/api/tasks/{self.task.id}/").json()
        self.assertNotIn("description", item)
        self.assertEqual(api.patch(f"/api/tasks/{self.task.id}/", {"title": "Changed"}, format="json").status_code, 403)

    def test_client_cannot_create_task(self):
        response = self.api(self.client_user).post("/api/tasks/", {"project": str(self.project.id), "title": "No", "description": "No"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_assignee_must_accept_before_starting(self):
        api = self.api(self.member)
        self.assertEqual(api.post(f"/api/tasks/{self.task.id}/start-work/").status_code, 403)
        self.assertEqual(api.post(f"/api/tasks/{self.task.id}/accept/").status_code, 200)
        self.assertEqual(api.post(f"/api/tasks/{self.task.id}/start-work/").status_code, 200)

    def test_open_uat_blocks_completion(self):
        tester = TaskTester.objects.create(task=self.task, user=self.member, is_main=True)
        tester.accepted_at = self.task.created_at
        tester.save(update_fields=("accepted_at",))
        UATObservation.objects.create(task=self.task, reporter=self.member, title="Issue", description="Open", severity=UATObservation.Severity.HIGH)
        response = self.api(self.member).post(f"/api/tasks/{self.task.id}/complete/")
        self.assertEqual(response.status_code, 400)

    def test_status_requires_staff(self):
        self.assertEqual(self.api(self.member).get("/api/status/").status_code, 403)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEBUG=True)
class OnboardingTests(TestCase):
    def setUp(self):
        self.api_client = APIClient(enforce_csrf_checks=True)

    def test_registration_requires_valid_email_otp(self):
        email = "raj@example.com"
        EmailVerificationChallenge.objects.create(email=email, code_hash=make_password("123456"), expires_at=timezone.now() + timedelta(minutes=10))
        csrf = self.api_client.get("/api/auth/csrf/").json()["csrfToken"]
        response = self.api_client.post("/api/auth/register/", {"email": email, "first_name": "Raj", "last_name": "K", "password": "Strong-pass-937!", "otp": "123456"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(email=email).username, email)

    def test_starter_workspace_and_client_creation(self):
        user = User.objects.create_user("raj@example.com", email="raj@example.com", password="Strong-pass-937!")
        api = APIClient()
        api.force_authenticate(user)
        workspace = api.post("/api/organizations/", {"name": "Raj Consulting", "timezone": "Asia/Kolkata"}, format="json")
        self.assertEqual(workspace.status_code, 201)
        organization_id = workspace.json()["id"]
        self.assertEqual(Membership.objects.get(user=user).role, Membership.Role.OWNER)
        client = api.post("/api/clients/", {"organization": organization_id, "name": "TALIC", "code": "talic"}, format="json")
        self.assertEqual(client.status_code, 201)
        self.assertTrue(ClientAccount.objects.filter(name="TALIC", created_by=user).exists())

    def test_member_task_list_is_personal(self):
        lead = User.objects.create_user("lead@example.com")
        member = User.objects.create_user("member@example.com")
        other = User.objects.create_user("other@example.com")
        org = Organization.objects.create(name="Workspace", slug="workspace")
        Membership.objects.bulk_create([Membership(organization=org, user=lead, role=Membership.Role.OWNER), Membership(organization=org, user=member, role=Membership.Role.MEMBER), Membership(organization=org, user=other, role=Membership.Role.MEMBER)])
        team = Team.objects.create(organization=org, name="Ops", owner=lead, lead=lead)
        project = Project.objects.create(organization=org, team=team, name="CAMS", code="CAMS")
        ProjectMembership.objects.bulk_create([ProjectMembership(project=project, user=member), ProjectMembership(project=project, user=other)])
        Task.objects.create(project=project, sequence=1, title="Mine", description="Mine", owner=lead, assignee=member)
        Task.objects.create(project=project, sequence=2, title="Other", description="Other", owner=lead, assignee=other)
        api = APIClient(); api.force_authenticate(member)
        titles = [item["title"] for item in api.get("/api/tasks/").json()["results"]]
        self.assertEqual(titles, ["Mine"])

    def test_project_invitation_is_email_bound_and_single_use(self):
        owner = User.objects.create_user("owner@example.com", email="owner@example.com")
        invitee = User.objects.create_user("invitee@example.com", email="invitee@example.com")
        wrong_user = User.objects.create_user("wrong@example.com", email="wrong@example.com")
        org = Organization.objects.create(name="Workspace", slug="invitation-workspace", max_users=5)
        Membership.objects.create(organization=org, user=owner, role=Membership.Role.OWNER)
        client = ClientAccount.objects.create(organization=org, name="TALIC", code="talic", created_by=owner)
        team = Team.objects.create(organization=org, name="Ops", owner=owner, lead=owner)
        project = Project.objects.create(organization=org, client=client, team=team, name="CAMS", code="CAMS")
        api = APIClient(); api.force_authenticate(owner)
        response = api.post("/api/invitations/", {"organization": str(org.id), "client": str(client.id), "project": str(project.id), "scope": "PROJECT", "email": invitee.email, "role": "MEMBER"}, format="json")
        self.assertEqual(response.status_code, 201)
        token = parse_qs(urlparse(mail.outbox[0].body.split()[-1]).query)["token"][0]
        wrong = APIClient(); wrong.force_authenticate(wrong_user)
        self.assertEqual(wrong.post("/api/invitations/accept/", {"token": token}, format="json").status_code, 400)
        accepted = APIClient(); accepted.force_authenticate(invitee)
        self.assertEqual(accepted.post("/api/invitations/accept/", {"token": token}, format="json").status_code, 200)
        self.assertTrue(ProjectMembership.objects.filter(project=project, user=invitee).exists())
        self.assertEqual(accepted.post("/api/invitations/accept/", {"token": token}, format="json").status_code, 400)


class PlatformAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin@example.com", email="admin@example.com", is_staff=True)
        self.member = User.objects.create_user("member@example.com", email="member@example.com")

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_platform_admin_summary_is_staff_only(self):
        self.assertEqual(self.api(self.member).get("/api/platform-admin/summary/").status_code, 403)
        response = self.api(self.admin).get("/api/platform-admin/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["users"]), 2)

    def test_platform_admin_can_block_and_restore_but_not_self_block(self):
        api = self.api(self.admin)
        self.assertEqual(api.post(f"/api/platform-admin/users/{self.member.id}/status/", {"is_active": False}, format="json").status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertEqual(api.post(f"/api/platform-admin/users/{self.member.id}/status/", {"is_active": True}, format="json").status_code, 200)
        self.assertEqual(api.post(f"/api/platform-admin/users/{self.admin.id}/status/", {"is_active": False}, format="json").status_code, 400)
