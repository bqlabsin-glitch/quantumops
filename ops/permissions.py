from rest_framework.exceptions import PermissionDenied

from .models import Membership, ProjectMembership


def organization_membership(user, organization_id):
    if not user.is_authenticated:
        return None
    return Membership.objects.filter(
        user=user, organization_id=organization_id, is_active=True
    ).first()


def require_organization_role(user, organization_id, roles):
    membership = organization_membership(user, organization_id)
    if not membership or membership.role not in roles:
        raise PermissionDenied("You do not have permission for this organization.")
    return membership


def accessible_project_ids(user):
    if user.is_staff:
        return None
    elevated_orgs = Membership.objects.filter(
        user=user,
        is_active=True,
        role__in=(Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGEMENT),
    ).values_list("organization_id", flat=True)
    direct_projects = ProjectMembership.objects.filter(
        user=user, is_active=True
    ).values_list("project_id", flat=True)
    return elevated_orgs, direct_projects
