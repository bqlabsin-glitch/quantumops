from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Membership, Organization, Project, ProjectMembership, Task, TaskTester, Team, UATObservation

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
