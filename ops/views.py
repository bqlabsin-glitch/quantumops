from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import LeaveRequest, Membership, Organization, OrganizationRequest, Project, ProjectMembership, Task, TaskTester, UATObservation
from .permissions import accessible_project_ids, require_organization_role
from .serializers import LeaveRequestSerializer, OrganizationRequestSerializer, OrganizationSerializer, ProjectSerializer, RegisterSerializer, TaskSerializer, UATObservationSerializer, UserSerializer
from .services import audit


class AuthThrottle(AnonRateThrottle):
    scope = "auth"


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def csrf(request):
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    login(request, user)
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def sign_in(request):
    username = str(request.data.get("username", ""))[:150]
    password = str(request.data.get("password", ""))[:1024]
    user = authenticate(request, username=username, password=password)
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


class OrganizationRequestViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationRequestSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        queryset = OrganizationRequest.objects.select_related("requester", "decided_by")
        return queryset if self.request.user.is_staff else queryset.filter(requester=self.request.user)

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        queryset = Organization.objects.prefetch_related("memberships")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(memberships__user=self.request.user, memberships__is_active=True).distinct()


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
        require_organization_role(self.request.user, team.organization_id, (Membership.Role.OWNER, Membership.Role.ADMIN))
        serializer.save(organization=team.organization)

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
        return queryset.filter(Q(project__organization_id__in=elevated_orgs) | Q(project_id__in=direct_projects)).distinct().order_by("project__code", "sequence")

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


class LeaveRequestViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        org_ids = Membership.objects.filter(user=self.request.user, is_active=True).values_list("organization_id", flat=True)
        return LeaveRequest.objects.select_related("requester", "organization").prefetch_related("affected_projects").filter(organization_id__in=org_ids)

    def perform_destroy(self, instance):
        if instance.requester_id != self.request.user.id or instance.from_date <= timezone.localdate():
            raise PermissionDenied("Only the requester may cancel a future leave before it begins.")
        instance.status = LeaveRequest.Status.CANCELLED
        instance.save(update_fields=("status", "updated_at"))
        audit(actor=self.request.user, action="leave.cancelled", obj=instance)
