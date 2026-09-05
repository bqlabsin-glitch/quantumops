from django.contrib import admin

from .models import AuditEvent, Membership, Organization, OrganizationRequest, Project, Task
from .services import approve_organization_request


@admin.action(description="Approve selected organization requests")
def approve_requests(modeladmin, request, queryset):
    if not request.user.is_superuser:
        modeladmin.message_user(request, "Only a BQ Labs platform administrator may approve organizations.", level="ERROR")
        return
    approved = 0
    for item in queryset:
        if item.status == OrganizationRequest.Status.PENDING:
            approve_organization_request(item, request.user)
            approved += 1
    modeladmin.message_user(request, f"Approved {approved} organization request(s).")


@admin.register(OrganizationRequest)
class OrganizationRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "requester", "expected_users", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "requester__username", "requester__email")
    actions = (approve_requests,)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "max_users", "max_projects", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active")
    list_filter = ("role", "is_active")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "organization", "visibility", "is_active")
    list_filter = ("visibility", "is_active")
    search_fields = ("code", "name")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "status", "assignment_status", "assignee")
    list_filter = ("status", "assignment_status")
    search_fields = ("title", "project__code")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "organization", "actor", "action", "object_type", "object_id")
    list_filter = ("action", "object_type")
    search_fields = ("actor__username", "object_id")
    readonly_fields = ("id", "organization", "actor", "action", "object_type", "object_id", "metadata", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
