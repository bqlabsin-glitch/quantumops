from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import (
    LeaveRequest,
    Membership,
    Organization,
    OrganizationRequest,
    Project,
    ProjectMembership,
    Task,
    TaskTester,
    UATObservation,
)
from .services import audit

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account already uses this email.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class OrganizationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationRequest
        fields = ("id", "name", "purpose", "expected_users", "status", "decision_reason", "created_at")
        read_only_fields = ("status", "decision_reason", "created_at")


class OrganizationSerializer(serializers.ModelSerializer):
    current_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "status", "timezone", "current_role")

    def get_current_role(self, obj):
        membership = next((m for m in obj.memberships.all() if m.user_id == self.context["request"].user.id), None)
        return membership.role if membership else None


class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    completed_count = serializers.IntegerField(read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = Project
        fields = ("id", "organization", "organization_name", "team", "team_name", "name", "code", "description", "visibility", "client_leave_approval", "timezone", "working_days", "is_active", "task_count", "completed_count")
        read_only_fields = ("organization",)

    def validate_working_days(self, value):
        if not isinstance(value, list) or not value or any(not isinstance(day, int) or day < 0 or day > 6 for day in value):
            raise serializers.ValidationError("Use a non-empty list of weekday numbers from 0 to 6.")
        return sorted(set(value))


class TaskSerializer(serializers.ModelSerializer):
    key = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.get_full_name", read_only=True)
    open_observations = serializers.IntegerField(read_only=True)

    class Meta:
        model = Task
        fields = ("id", "key", "project", "sequence", "title", "description", "acceptance_criteria", "owner", "owner_name", "assignee", "assignee_name", "status", "assignment_status", "review_required", "complexity", "planned_start", "forecast_finish", "accepted_at", "started_at", "completed_at", "archived_at", "open_observations")
        read_only_fields = ("sequence", "owner", "assignment_status", "accepted_at", "started_at", "completed_at", "archived_at")

    def validate(self, attrs):
        project = attrs.get("project") or getattr(self.instance, "project", None)
        assignee = attrs.get("assignee")
        if assignee and project and not ProjectMembership.objects.filter(project=project, user=assignee, is_active=True).exists():
            raise serializers.ValidationError({"assignee": "Assignee must be an active project member."})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = self.context["request"].user
        is_client = ProjectMembership.objects.filter(
            project=instance.project,
            user=user,
            is_active=True,
            role__in=(ProjectMembership.Role.CLIENT, ProjectMembership.Role.CLIENT_APPROVER),
        ).exists()
        if is_client and instance.project.visibility == Project.Visibility.SUMMARY:
            for field in ("description", "acceptance_criteria", "owner", "owner_name", "assignee", "assignee_name", "complexity", "planned_start"):
                data.pop(field, None)
        return data

    @transaction.atomic
    def create(self, validated_data):
        project = validated_data["project"]
        last = Task.objects.select_for_update().filter(project=project).order_by("-sequence").first()
        validated_data["sequence"] = (last.sequence if last else 0) + 1
        validated_data["owner"] = self.context["request"].user
        validated_data["assignment_status"] = Task.AssignmentStatus.PENDING if validated_data.get("assignee") else Task.AssignmentStatus.UNASSIGNED
        task = super().create(validated_data)
        audit(actor=task.owner, action="task.created", obj=task, organization=project.organization)
        return task


class TaskTesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTester
        fields = ("id", "task", "user", "is_main", "accepted_at")
        read_only_fields = ("accepted_at",)


class UATObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UATObservation
        fields = ("id", "task", "reporter", "title", "description", "severity", "status", "resolved_by", "created_at", "updated_at")
        read_only_fields = ("reporter", "resolved_by", "created_at", "updated_at")


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = ("id", "organization", "requester", "from_date", "to_date", "leave_type", "reason", "status", "affected_projects", "created_at")
        read_only_fields = ("organization", "requester", "status", "created_at")

    def validate(self, attrs):
        if attrs["to_date"] < attrs["from_date"]:
            raise serializers.ValidationError({"to_date": "To date must be on or after from date."})
        projects = attrs.get("affected_projects", [])
        if not projects:
            raise serializers.ValidationError({"affected_projects": "Select at least one affected project."})
        org_ids = {project.organization_id for project in projects}
        if len(org_ids) != 1:
            raise serializers.ValidationError("Affected projects must belong to one organization.")
        return attrs

    def create(self, validated_data):
        projects = validated_data.pop("affected_projects")
        validated_data["organization"] = projects[0].organization
        validated_data["requester"] = self.context["request"].user
        leave = LeaveRequest.objects.create(**validated_data)
        leave.affected_projects.set(projects)
        audit(actor=leave.requester, action="leave.requested", obj=leave)
        return leave
