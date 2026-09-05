from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import AuditEvent, Membership, Organization, OrganizationRequest


def audit(*, actor, action, obj, organization=None, metadata=None):
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label,
        object_id=str(obj.pk),
        organization=organization or getattr(obj, "organization", None),
        metadata=metadata or {},
    )


@transaction.atomic
def approve_organization_request(request_obj, actor):
    request_obj = OrganizationRequest.objects.select_for_update().get(pk=request_obj.pk)
    if request_obj.status != OrganizationRequest.Status.PENDING:
        raise ValueError("Only pending requests can be approved.")
    base = slugify(request_obj.name)[:150] or "organization"
    slug = base
    counter = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    organization = Organization.objects.create(name=request_obj.name, slug=slug)
    Membership.objects.create(
        organization=organization,
        user=request_obj.requester,
        role=Membership.Role.OWNER,
    )
    request_obj.status = OrganizationRequest.Status.APPROVED
    request_obj.decided_by = actor
    request_obj.decided_at = timezone.now()
    request_obj.save(update_fields=("status", "decided_by", "decided_at", "updated_at"))
    audit(actor=actor, action="organization_request.approved", obj=request_obj, organization=organization)
    return organization
