import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def default_working_days():
    return [0, 1, 2, 3, 4]


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PlatformEmailSettings(TimeStampedModel):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    host = models.CharField(max_length=253, blank=True)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=254, blank=True)
    password_encrypted = models.TextField(blank=True)
    security = models.CharField(max_length=8, default="STARTTLS", choices=(("STARTTLS", "STARTTLS"), ("SSL", "SSL")))
    from_email = models.EmailField(blank=True)


class OrganizationRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        MORE_INFO = "MORE_INFO", "More information required"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    purpose = models.TextField(max_length=2000)
    expected_users = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    decision_reason = models.TextField(blank=True, max_length=2000)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="organization_decisions")
    decided_at = models.DateTimeField(null=True, blank=True)


class Organization(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        READ_ONLY = "READ_ONLY", "Read only"
        SECURITY_LOCKED = "SECURITY_LOCKED", "Security locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    max_users = models.PositiveIntegerField(default=25)
    max_teams = models.PositiveIntegerField(default=5)
    max_projects = models.PositiveIntegerField(default=10)
    max_tasks = models.PositiveIntegerField(default=10000)
    max_attachment_bytes = models.PositiveBigIntegerField(default=2 * 1024 * 1024 * 1024)


class ClientAccount(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=60)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_clients")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_client_code_in_org")]
        indexes = [models.Index(fields=("organization", "is_active"))]


class ClientMembership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Client owner"
        MANAGER = "MANAGER", "Client manager"
        MEMBER = "MEMBER", "Member"

    client = models.ForeignKey(ClientAccount, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="client_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("client", "user"), name="unique_client_membership")]


class Membership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Organization owner"
        ADMIN = "ADMIN", "Organization administrator"
        MANAGEMENT = "MANAGEMENT", "Senior management"
        MEMBER = "MEMBER", "Team member"
        CLIENT = "CLIENT", "Client"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "user"), name="unique_org_membership")]
        indexes = [models.Index(fields=("user", "is_active")), models.Index(fields=("organization", "role"))]


class Team(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_teams")
    lead = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="led_teams")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "name"), name="unique_team_name_in_org")]


class TeamMembership(TimeStampedModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_memberships")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("team", "user"), name="unique_team_member")]


class Project(TimeStampedModel):
    class Visibility(models.TextChoices):
        SUMMARY = "SUMMARY", "Summarized"
        FULL = "FULL", "Full detail"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="projects")
    client = models.ForeignKey(ClientAccount, on_delete=models.PROTECT, related_name="projects", null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="projects")
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True, max_length=5000)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.SUMMARY)
    client_leave_approval = models.BooleanField(default=False)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    working_days = models.JSONField(default=default_working_days)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="unique_project_code_in_org")]
        indexes = [models.Index(fields=("organization", "is_active")), models.Index(fields=("team", "is_active"))]


class ProjectMembership(TimeStampedModel):
    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        CLIENT = "CLIENT", "Client"
        CLIENT_APPROVER = "CLIENT_APPROVER", "Client approver"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "user"), name="unique_project_membership")]
        indexes = [models.Index(fields=("user", "is_active")), models.Index(fields=("project", "role"))]


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        BLOCKED = "BLOCKED", "Blocked"
        REVIEW = "REVIEW", "Review"
        UAT = "UAT", "UAT"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class AssignmentStatus(models.TextChoices):
        UNASSIGNED = "UNASSIGNED", "Unassigned"
        PENDING = "PENDING", "Pending member action"
        OVERDUE = "OVERDUE", "Pending member action - overdue"
        ACCEPTED = "ACCEPTED", "Accepted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    sequence = models.PositiveIntegerField()
    title = models.CharField(max_length=240)
    description = models.TextField(max_length=10000)
    acceptance_criteria = models.TextField(blank=True, max_length=10000)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_tasks")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_tasks")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    assignment_status = models.CharField(max_length=16, choices=AssignmentStatus.choices, default=AssignmentStatus.UNASSIGNED)
    review_required = models.BooleanField(default=False)
    complexity = models.PositiveSmallIntegerField(default=1)
    planned_start = models.DateTimeField(null=True, blank=True)
    forecast_finish = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "sequence"), name="unique_task_sequence"),
            models.CheckConstraint(check=Q(complexity__gte=1) & Q(complexity__lte=5), name="task_complexity_1_to_5"),
        ]
        indexes = [models.Index(fields=("project", "status")), models.Index(fields=("assignee", "status"))]

    @property
    def key(self):
        return f"{self.project.code}-{self.sequence}"


class TaskTester(TimeStampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="testers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="testing_assignments")
    is_main = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("task", "user"), name="unique_task_tester"),
            models.UniqueConstraint(fields=("task",), condition=Q(is_main=True), name="one_main_tester_per_task"),
        ]


class TaskReview(TimeStampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    task_revision = models.PositiveIntegerField(default=1)
    outcome = models.CharField(max_length=40)
    notes = models.TextField(blank=True, max_length=5000)


class UATObservation(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FIXING = "FIXING", "Fix in progress"
        READY = "READY", "Ready for retest"
        RETESTING = "RETESTING", "Retesting"
        RESOLVED = "RESOLVED", "Resolved"
        REJECTED = "REJECTED", "Rejected"
        DUPLICATE = "DUPLICATE", "Duplicate"

    class Severity(models.TextChoices):
        CRITICAL = "CRITICAL", "Critical"
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="observations")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_observations")
    title = models.CharField(max_length=240)
    description = models.TextField(max_length=10000)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="resolved_observations")


class Blocker(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="blockers")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="raised_blockers")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_blockers")
    description = models.TextField(max_length=5000)
    severity = models.CharField(max_length=10, choices=UATObservation.Severity.choices)
    resolution = models.TextField(blank=True, max_length=5000)
    resolved_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="confirmed_blockers")


class LeaveRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_LEAD = "PENDING_LEAD", "Pending team lead"
        PENDING_CLIENT = "PENDING_CLIENT", "Pending client"
        CHANGES_REQUIRED = "CHANGES_REQUIRED", "Changes required"
        APPROVED = "APPROVED", "Approved"
        UNAPPROVED = "UNAPPROVED", "Unapproved leave"
        AUTO_APPROVED = "AUTO_APPROVED", "Backdated - system approved"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="leave_requests")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leave_requests")
    from_date = models.DateField()
    to_date = models.DateField()
    leave_type = models.CharField(max_length=40)
    reason = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_LEAD)
    affected_projects = models.ManyToManyField(Project, related_name="leave_requests")

    def clean(self):
        if self.to_date < self.from_date:
            raise ValidationError({"to_date": "To date must be on or after from date."})


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("organization", "created_at")), models.Index(fields=("actor", "created_at"))]

    def save(self, *args, **kwargs):
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are immutable.")


class EmailVerificationChallenge(TimeStampedModel):
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=32, default="REGISTRATION")
    code_hash = models.CharField(max_length=160)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("email", "purpose", "expires_at"))]


class Invitation(TimeStampedModel):
    class Scope(models.TextChoices):
        ORGANIZATION = "ORGANIZATION", "Organization"
        CLIENT = "CLIENT", "Client"
        PROJECT = "PROJECT", "Project"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    client = models.ForeignKey(ClientAccount, null=True, blank=True, on_delete=models.CASCADE, related_name="invitations")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.CASCADE, related_name="invitations")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_invitations")
    email = models.EmailField()
    scope = models.CharField(max_length=16, choices=Scope.choices)
    role = models.CharField(max_length=24)
    token_hash = models.CharField(max_length=160)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("email", "expires_at")), models.Index(fields=("organization", "created_at"))]
