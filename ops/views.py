from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.mail import BadHeaderError
from django.db import transaction
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import ClientAccount, ClientMembership, Invitation, LeaveRequest, Membership, Organization, OrganizationRequest, Project, ProjectMembership, Task, TaskTester, Team, TeamMembership, UATObservation
from .permissions import accessible_project_ids, require_organization_role
from .serializers import ClientAccountSerializer, LeaveRequestSerializer, OrganizationRequestSerializer, OrganizationSerializer, ProjectMembershipSerializer, ProjectSerializer, RegisterSerializer, TaskSerializer, TaskTesterSerializer, TeamSerializer, UATObservationSerializer, UserSerializer
from .services import audit, consume_email_otp, issue_email_otp, issue_invitation, token_digest, verify_human_challenge

User = get_user_model()
from .models import PlatformEmailSettings
from .email_config import EmailSettingsSerializer, send_platform_email


@api_view(["GET", "PUT"])
def platform_email_settings(request):
    require_platform_admin(request.user)
    instance = PlatformEmailSettings.objects.filter(pk=1).first() or PlatformEmailSettings(pk=1)
    if request.method == "PUT":
        serializer = EmailSettingsSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            audit(actor=request.user, action="platform.email_settings_updated", obj=instance)
    response = Response(EmailSettingsSerializer(instance).data)
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
def platform_email_test(request):
    require_platform_admin(request.user)
    if not request.user.email:
        raise ValidationError("Add an email address to your administrator account first.")
    try:
        send_platform_email("Quantum OPS email test", "Your Quantum OPS email configuration is working.", [request.user.email])
    except (OSError, BadHeaderError):
        return Response({"detail": "Test delivery failed. Check that delivery is enabled and the host, port, sender and credentials are correct."}, status=503)
    audit(actor=request.user, action="platform.email_test_sent", obj=request.user)
    return Response({"detail": "Test email sent to your administrator email address."})


def require_platform_admin(user):
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        raise PermissionDenied("BQ Labs administrator access is required.")


class AuthThrottle(AnonRateThrottle):
    scope = "auth"


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def csrf(request):
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def request_registration_otp(request):
    email = str(request.data.get("email", "")).strip().lower()[:254]
    challenge_token = str(request.data.get("challenge_token", ""))[:4096]
    if "@" not in email or not verify_human_challenge(challenge_token, request.META.get("REMOTE_ADDR")):
        return Response({"detail": "Unable to verify this registration request."}, status=status.HTTP_400_BAD_REQUEST)
    if not User.objects.filter(email__iexact=email).exists():
        try:
            issue_email_otp(email)
        except (OSError, BadHeaderError):
            return Response({"detail": "Verification email is temporarily unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"detail": "If the address can be registered, a verification code has been sent."})


@api_view(["GET"])
def platform_admin_summary(request):
    require_platform_admin(request.user)
    users = User.objects.annotate(
        owned_task_count=Count("owned_tasks", distinct=True),
        assigned_task_count=Count("assigned_tasks", distinct=True),
    ).order_by("-last_login", "email")[:500]
    organizations = Organization.objects.annotate(
        user_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True),
        project_count=Count("projects", filter=Q(projects__is_active=True), distinct=True),
        task_count=Count("projects__tasks", filter=Q(projects__tasks__archived_at__isnull=True), distinct=True),
    ).order_by("name")[:500]
    return Response({
        "users": [{
            "id": user.id,
            "email": user.email,
            "name": user.get_full_name(),
            "is_active": user.is_active,
            "is_staff": user.is_staff,
            "last_login": user.last_login,
            "date_joined": user.date_joined,
            "owned_tasks": user.owned_task_count,
            "assigned_tasks": user.assigned_task_count,
        } for user in users],
        "organizations": [{
            "id": org.id,
            "name": org.name,
            "status": org.status,
            "plan": "Starter" if org.max_projects <= 2 else "Custom",
            "users": org.user_count,
            "user_limit": org.max_users,
            "projects": org.project_count,
            "project_limit": org.max_projects,
            "tasks": org.task_count,
            "task_limit": org.max_tasks,
        } for org in organizations],
    })


@api_view(["POST"])
def platform_admin_user_status(request, user_id):
    require_platform_admin(request.user)
    target = User.objects.filter(pk=user_id).first()
    if not target:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    active = request.data.get("is_active")
    if not isinstance(active, bool):
        raise ValidationError({"is_active": "Use true or false."})
    if target.pk == request.user.pk and not active:
        raise ValidationError("You cannot block your own administrator account.")
    target.is_active = active
    target.save(update_fields=("is_active",))
    audit(actor=request.user, action="platform.user_restored" if active else "platform.user_blocked", obj=target)
    return Response(UserSerializer(target).data)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not consume_email_otp(serializer.validated_data["email"], serializer.validated_data["otp"]):
        raise ValidationError({"otp": "The verification code is invalid or expired."})
    user = serializer.save()
    login(request, user)
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def sign_in(request):
    identifier = str(request.data.get("email", request.data.get("username", ""))).strip().lower()[:254]
    password = str(request.data.get("password", ""))[:1024]
    account = User.objects.filter(email__iexact=identifier).only("username").first()
    user = authenticate(request, username=account.username if account else identifier, password=password)
    if user is None or not user.is_active:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
def sign_out(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def session(request):
    return Response(UserSerializer(request.user).data)


@api_view(["GET"])
def people(request):
    organization_id = request.query_params.get("organization")
    if not organization_id or not Membership.objects.filter(organization_id=organization_id, user=request.user, is_active=True).exists():
        raise PermissionDenied("Select a workspace you belong to.")
    users = User.objects.filter(organization_memberships__organization_id=organization_id, organization_memberships__is_active=True).distinct().order_by("first_name", "email")
    return Response(UserSerializer(users, many=True).data)


@api_view(["POST"])
def invite(request):
    organization = Organization.objects.filter(pk=request.data.get("organization")).first()
    client = ClientAccount.objects.filter(pk=request.data.get("client"), organization=organization).first() if request.data.get("client") else None
    project = Project.objects.filter(pk=request.data.get("project"), organization=organization).first() if request.data.get("project") else None
    scope = str(request.data.get("scope", "PROJECT"))
    email = str(request.data.get("email", "")).strip().lower()[:254]
    role = str(request.data.get("role", "MEMBER"))[:24]
    if not organization or "@" not in email or scope not in Invitation.Scope.values:
        raise ValidationError("Provide a valid invitation scope and email.")
    org_manager = Membership.objects.filter(organization=organization, user=request.user, is_active=True, role__in=(Membership.Role.OWNER, Membership.Role.ADMIN)).exists()
    client_manager = client and ClientMembership.objects.filter(client=client, user=request.user, is_active=True, role__in=(ClientMembership.Role.OWNER, ClientMembership.Role.MANAGER)).exists()
    project_manager = project and request.user in (project.team.owner, project.team.lead)
    if not request.user.is_staff and not org_manager and not client_manager and not project_manager:
        raise PermissionDenied("Only an authorized owner, manager, or team lead may invite users.")
    if scope == Invitation.Scope.CLIENT and not client:
        raise ValidationError({"client": "Select the client for this invitation."})
    if scope == Invitation.Scope.PROJECT and not project:
        raise ValidationError({"project": "Select the project for this invitation."})
    if organization.memberships.filter(is_active=True).count() >= organization.max_users:
        raise ValidationError("The workspace user limit has been reached.")
    try:
        invitation = issue_invitation(organization=organization, client=client or (project.client if project else None), project=project, invited_by=request.user, email=email, scope=scope, role=role)
    except (OSError, BadHeaderError):
        return Response({"detail": "Invitation email is temporarily unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    audit(actor=request.user, action="invitation.sent", obj=invitation, organization=organization, metadata={"scope": scope})
    return Response({"id": invitation.id, "email": invitation.email, "expires_at": invitation.expires_at}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def accept_invitation(request):
    digest = token_digest(str(request.data.get("token", ""))[:256])
    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().filter(token_hash=digest, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()).first()
        if not invitation or invitation.email.lower() != request.user.email.lower():
            raise ValidationError("This invitation is invalid, expired, or belongs to another account.")
        membership, _ = Membership.objects.get_or_create(organization=invitation.organization, user=request.user, defaults={"role": Membership.Role.MEMBER})
        if not membership.is_active:
            raise PermissionDenied("Your workspace membership is inactive.")
        if invitation.client:
            client_role = invitation.role if invitation.role in ClientMembership.Role.values else ClientMembership.Role.MEMBER
            ClientMembership.objects.update_or_create(client=invitation.client, user=request.user, defaults={"role": client_role, "is_active": True})
        if invitation.project:
            project_role = invitation.role if invitation.role in ProjectMembership.Role.values else ProjectMembership.Role.MEMBER
            ProjectMembership.objects.update_or_create(project=invitation.project, user=request.user, defaults={"role": project_role, "is_active": True})
            if project_role == ProjectMembership.Role.MEMBER:
                TeamMembership.objects.update_or_create(team=invitation.project.team, user=request.user, defaults={"is_active": True})
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=("accepted_at", "updated_at"))
        audit(actor=request.user, action="invitation.accepted", obj=invitation, organization=invitation.organization)
    return Response({"detail": "Invitation accepted."})


class OrganizationRequestViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationRequestSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        queryset = OrganizationRequest.objects.select_related("requester", "decided_by")
        return queryset if self.request.user.is_staff else queryset.filter(requester=self.request.user)

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        queryset = Organization.objects.prefetch_related("memberships")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(memberships__user=self.request.user, memberships__is_active=True).distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        if Membership.objects.filter(user=self.request.user, role=Membership.Role.OWNER, is_active=True).exists():
            raise ValidationError("The Starter plan allows one owned workspace.")
        base = slugify(serializer.validated_data["name"])[:150] or "workspace"
        slug, counter = base, 2
        while Organization.objects.filter(slug=slug).exists():
            slug, counter = f"{base}-{counter}", counter + 1
        organization = serializer.save(slug=slug, max_users=5, max_teams=2, max_projects=2, max_tasks=250, max_attachment_bytes=100 * 1024 * 1024)
        Membership.objects.create(organization=organization, user=self.request.user, role=Membership.Role.OWNER)
        audit(actor=self.request.user, action="organization.created", obj=organization)


class ClientAccountViewSet(viewsets.ModelViewSet):
    serializer_class = ClientAccountSerializer

    def get_queryset(self):
        return ClientAccount.objects.prefetch_related("memberships").annotate(project_count=Count("projects", distinct=True)).filter(
            Q(memberships__user=self.request.user, memberships__is_active=True) |
            Q(organization__memberships__user=self.request.user, organization__memberships__is_active=True, organization__memberships__role__in=(Membership.Role.OWNER, Membership.Role.ADMIN))
        ).distinct().order_by("name")

    @transaction.atomic
    def perform_create(self, serializer):
        organization = serializer.validated_data["organization"]
        if not Membership.objects.filter(organization=organization, user=self.request.user, is_active=True).exists():
            raise PermissionDenied("You must belong to this workspace.")
        if organization.clients.filter(is_active=True).count() >= 1 and organization.max_projects <= 2:
            raise ValidationError("The Starter plan allows one active client.")
        client = serializer.save(created_by=self.request.user)
        ClientMembership.objects.create(client=client, user=self.request.user, role=ClientMembership.Role.OWNER)
        audit(actor=self.request.user, action="client.created", obj=client, organization=organization)

    def perform_update(self, serializer):
        client = serializer.instance
        if not ClientMembership.objects.filter(client=client, user=self.request.user, is_active=True, role__in=(ClientMembership.Role.OWNER, ClientMembership.Role.MANAGER)).exists():
            raise PermissionDenied("Only a client owner or manager may update this client.")
        serializer.save()


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer

    def get_queryset(self):
        org_ids = Membership.objects.filter(user=self.request.user, is_active=True).values_list("organization_id", flat=True)
        return Team.objects.select_related("owner", "lead", "organization").filter(organization_id__in=org_ids).order_by("name")

    def perform_create(self, serializer):
        organization = serializer.validated_data["organization"]
        if not Membership.objects.filter(organization=organization, user=self.request.user, is_active=True).exists():
            raise PermissionDenied("You must belong to this workspace.")
        if organization.teams.count() >= organization.max_teams:
            raise ValidationError("The workspace team limit has been reached.")
        team = serializer.save(owner=self.request.user, lead=serializer.validated_data.get("lead") or self.request.user)
        TeamMembership.objects.get_or_create(team=team, user=self.request.user)
        audit(actor=self.request.user, action="team.created", obj=team, organization=organization)


class ProjectMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectMembershipSerializer

    def get_queryset(self):
        project_ids = ProjectViewSet(request=self.request).get_queryset().values_list("id", flat=True)
        queryset = ProjectMembership.objects.select_related("user", "project").filter(project_id__in=project_ids)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset.order_by("user__first_name", "user__email")

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        allowed = self.request.user in (project.team.owner, project.team.lead) or ClientMembership.objects.filter(client=project.client, user=self.request.user, is_active=True, role__in=(ClientMembership.Role.OWNER, ClientMembership.Role.MANAGER)).exists()
        if not allowed and not self.request.user.is_staff:
            raise PermissionDenied("Only the team lead, team owner, or client manager may assign project members.")
        target = serializer.validated_data["user"]
        if not Membership.objects.filter(organization=project.organization, user=target, is_active=True).exists():
            raise ValidationError({"user": "The user must first join the workspace."})
        serializer.save()


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        queryset = Project.objects.select_related("organization", "team").annotate(
            task_count=Count("tasks", filter=Q(tasks__archived_at__isnull=True), distinct=True),
            completed_count=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED, tasks__archived_at__isnull=True), distinct=True),
        )
        access = accessible_project_ids(self.request.user)
        if access is None:
            return queryset
        elevated_orgs, direct_projects = access
        return queryset.filter(Q(organization_id__in=elevated_orgs) | Q(id__in=direct_projects)).distinct().order_by("name")

    def perform_create(self, serializer):
        team = serializer.validated_data["team"]
        client = serializer.validated_data.get("client")
        allowed = self.request.user in (team.owner, team.lead) or (client and ClientMembership.objects.filter(client=client, user=self.request.user, is_active=True, role__in=(ClientMembership.Role.OWNER, ClientMembership.Role.MANAGER)).exists())
        if not allowed and not self.request.user.is_staff:
            raise PermissionDenied("Only the team lead, team owner, or client manager may create this project.")
        if client and client.organization_id != team.organization_id:
            raise ValidationError("Client and team must belong to the same workspace.")
        if team.organization.projects.filter(is_active=True).count() >= team.organization.max_projects:
            raise ValidationError("The active-project limit has been reached.")
        project = serializer.save(organization=team.organization)
        ProjectMembership.objects.update_or_create(
            project=project,
            user=self.request.user,
            defaults={"role": ProjectMembership.Role.MEMBER, "is_active": True},
        )
        TeamMembership.objects.update_or_create(team=team, user=self.request.user, defaults={"is_active": True})

    def perform_update(self, serializer):
        require_organization_role(self.request.user, serializer.instance.organization_id, (Membership.Role.OWNER, Membership.Role.ADMIN))
        serializer.save()

    def perform_destroy(self, instance):
        raise PermissionDenied("Projects are archived, not deleted.")


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer

    def get_queryset(self):
        queryset = Task.objects.select_related("project", "project__organization", "owner", "assignee").annotate(
            open_observations=Count("observations", filter=~Q(observations__status__in=(UATObservation.Status.RESOLVED, UATObservation.Status.REJECTED, UATObservation.Status.DUPLICATE)), distinct=True)
        ).filter(archived_at__isnull=True)
        access = accessible_project_ids(self.request.user)
        if access is None:
            return queryset
        elevated_orgs, direct_projects = access
        queryset = queryset.filter(Q(project__organization_id__in=elevated_orgs) | Q(project_id__in=direct_projects)).distinct()
        elevated = Membership.objects.filter(user=self.request.user, is_active=True, role__in=(Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGEMENT)).exists()
        leading = Team.objects.filter(Q(owner=self.request.user) | Q(lead=self.request.user)).exists()
        client_user = ProjectMembership.objects.filter(user=self.request.user, is_active=True, role__in=(ProjectMembership.Role.CLIENT, ProjectMembership.Role.CLIENT_APPROVER)).exists()
        if not self.request.user.is_staff and not elevated and not leading and not client_user:
            queryset = queryset.filter(Q(owner=self.request.user) | Q(assignee=self.request.user) | Q(testers__user=self.request.user))
        return queryset.distinct().order_by("project__code", "sequence")

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        internal = ProjectMembership.objects.filter(project=project, user=self.request.user, role=ProjectMembership.Role.MEMBER, is_active=True).exists()
        elevated = Membership.objects.filter(
            organization=project.organization,
            user=self.request.user,
            is_active=True,
            role__in=(Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGEMENT),
        ).exists()
        if not self.request.user.is_staff and not internal and not elevated:
            raise PermissionDenied("Only internal project members may create tasks.")
        serializer.save()

    def perform_update(self, serializer):
        task = serializer.instance
        membership = ProjectMembership.objects.filter(project=task.project, user=self.request.user, is_active=True).first()
        is_client = membership and membership.role in (ProjectMembership.Role.CLIENT, ProjectMembership.Role.CLIENT_APPROVER)
        if is_client:
            raise PermissionDenied("Clients have read-only task access.")
        if self.request.user not in (task.owner, task.assignee, task.project.team.lead) and not self.request.user.is_staff:
            raise PermissionDenied("Only the task owner, assignee, or team lead may update this task.")
        serializer.save()

    def perform_destroy(self, instance):
        if self.request.user not in (instance.owner, instance.project.team.lead) and not self.request.user.is_staff:
            raise PermissionDenied("Only the task owner or team lead may archive this task.")
        instance.archived_at = timezone.now()
        instance.save(update_fields=("archived_at", "updated_at"))
        audit(actor=self.request.user, action="task.archived", obj=instance, organization=instance.project.organization)

    @action(detail=True, methods=("post",))
    def accept(self, request, pk=None):
        task = self.get_object()
        if task.assignee_id != request.user.id:
            raise PermissionDenied("Only the assignee may accept this task.")
        task.assignment_status = Task.AssignmentStatus.ACCEPTED
        task.accepted_at = timezone.now()
        task.save(update_fields=("assignment_status", "accepted_at", "updated_at"))
        audit(actor=request.user, action="task.accepted", obj=task, organization=task.project.organization)
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=("post",), url_path="start-work")
    def start_work(self, request, pk=None):
        task = self.get_object()
        if task.assignee_id != request.user.id or task.assignment_status != Task.AssignmentStatus.ACCEPTED:
            raise PermissionDenied("The assignee must accept the task before starting work.")
        task.status = Task.Status.IN_PROGRESS
        task.started_at = task.started_at or timezone.now()
        task.save(update_fields=("status", "started_at", "updated_at"))
        audit(actor=request.user, action="task.started", obj=task, organization=task.project.organization)
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=("post",))
    def complete(self, request, pk=None):
        task = self.get_object()
        if task.assignee_id != request.user.id:
            raise PermissionDenied("Only the assignee may complete this task.")
        if task.observations.exclude(status__in=(UATObservation.Status.RESOLVED, UATObservation.Status.REJECTED, UATObservation.Status.DUPLICATE)).exists():
            raise ValidationError("Resolve all open UAT observations before completion.")
        if task.review_required and not task.reviews.exists():
            raise ValidationError("This task requires a review before completion.")
        task.status = Task.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=("status", "completed_at", "updated_at"))
        audit(actor=request.user, action="task.completed", obj=task, organization=task.project.organization)
        return Response(self.get_serializer(task).data)


class TaskTesterViewSet(viewsets.ModelViewSet):
    serializer_class = TaskTesterSerializer

    def get_queryset(self):
        task_ids = TaskViewSet(request=self.request).get_queryset().values_list("id", flat=True)
        return TaskTester.objects.select_related("task", "user").filter(task_id__in=task_ids).order_by("task", "-is_main")

    def perform_create(self, serializer):
        task = serializer.validated_data["task"]
        if self.request.user not in (task.assignee, task.owner, task.project.team.lead, task.project.team.owner) and not self.request.user.is_staff:
            raise PermissionDenied("Only the working member, task owner, or team lead may select testers.")
        user = serializer.validated_data["user"]
        if not ProjectMembership.objects.filter(project=task.project, user=user, is_active=True, role=ProjectMembership.Role.MEMBER).exists():
            raise ValidationError({"user": "Tester must be an active internal project member."})
        serializer.save()

    @action(detail=True, methods=("post",))
    def accept(self, request, pk=None):
        tester = self.get_object()
        if tester.user_id != request.user.id:
            raise PermissionDenied("Only the assigned tester may accept this testing assignment.")
        tester.accepted_at = tester.accepted_at or timezone.now()
        tester.save(update_fields=("accepted_at", "updated_at"))
        audit(actor=request.user, action="tester.accepted", obj=tester, organization=tester.task.project.organization)
        return Response(self.get_serializer(tester).data)


class UATObservationViewSet(viewsets.ModelViewSet):
    serializer_class = UATObservationSerializer

    def get_queryset(self):
        task_ids = TaskViewSet(request=self.request).get_queryset().values_list("id", flat=True)
        return UATObservation.objects.select_related("task", "reporter", "resolved_by").filter(task_id__in=task_ids)

    def perform_create(self, serializer):
        task = serializer.validated_data["task"]
        if not TaskTester.objects.filter(task=task, user=self.request.user, accepted_at__isnull=False).exists():
            raise PermissionDenied("Accept the testing assignment before raising observations.")
        observation = serializer.save(reporter=self.request.user)
        audit(actor=self.request.user, action="uat.created", obj=observation, organization=task.project.organization)

    def perform_update(self, serializer):
        observation = serializer.instance
        accepted_tester = TaskTester.objects.filter(task=observation.task, user=self.request.user, accepted_at__isnull=False).exists()
        if not accepted_tester and self.request.user not in (observation.task.assignee, observation.task.owner, observation.task.project.team.lead):
            raise PermissionDenied("Only the assignee, task owner, team lead, or accepted tester may update this observation.")
        resolved_by = self.request.user if serializer.validated_data.get("status") == UATObservation.Status.RESOLVED else observation.resolved_by
        updated = serializer.save(resolved_by=resolved_by)
        audit(actor=self.request.user, action="uat.updated", obj=updated, organization=observation.task.project.organization)


class LeaveRequestViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        org_ids = Membership.objects.filter(user=self.request.user, is_active=True).values_list("organization_id", flat=True)
        queryset = LeaveRequest.objects.select_related("requester", "organization").prefetch_related("affected_projects").filter(organization_id__in=org_ids)
        elevated_org_ids = Membership.objects.filter(
            user=self.request.user,
            is_active=True,
            role__in=(Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGEMENT),
        ).values_list("organization_id", flat=True)
        led_team_org_ids = Team.objects.filter(Q(owner=self.request.user) | Q(lead=self.request.user)).values_list("organization_id", flat=True)
        return queryset.filter(Q(requester=self.request.user) | Q(organization_id__in=elevated_org_ids) | Q(organization_id__in=led_team_org_ids)).distinct()

    def perform_destroy(self, instance):
        if instance.requester_id != self.request.user.id or instance.from_date <= timezone.localdate():
            raise PermissionDenied("Only the requester may cancel a future leave before it begins.")
        instance.status = LeaveRequest.Status.CANCELLED
        instance.save(update_fields=("status", "updated_at"))
        audit(actor=self.request.user, action="leave.cancelled", obj=instance)
