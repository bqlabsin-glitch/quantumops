from rest_framework.exceptions import PermissionDenied

from django.db.models import Q

from .models import ClientMembership, Membership, Project


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
    direct_projects = Project.objects.filter(
        Q(memberships__user=user, memberships__is_active=True) |
        Q(client__memberships__user=user, client__memberships__is_active=True, client__memberships__role__in=(ClientMembership.Role.OWNER, ClientMembership.Role.MANAGER))
    ).values_list("id", flat=True)
    return elevated_orgs, direct_projects
