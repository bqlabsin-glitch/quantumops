import json
import secrets
import hashlib
from datetime import timedelta
from urllib import parse, request as urlrequest

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import AuditEvent, EmailVerificationChallenge, Invitation, Membership, Organization, OrganizationRequest


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


def verify_human_challenge(token, remote_ip=None):
    if settings.DEBUG and token == "development":
        return True
    if not settings.HUMAN_CHALLENGE_SECRET:
        return True
    if not token:
        return False
    payload = {"secret": settings.HUMAN_CHALLENGE_SECRET, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    req = urlrequest.Request(
        settings.HUMAN_CHALLENGE_VERIFY_URL,
        data=parse.urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=4) as response:
            return bool(json.loads(response.read().decode()).get("success"))
    except Exception:
        return False


def issue_email_otp(email):
    normalized = email.strip().lower()
    EmailVerificationChallenge.objects.filter(
        email=normalized, purpose="REGISTRATION", consumed_at__isnull=True
    ).update(consumed_at=timezone.now())
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = EmailVerificationChallenge.objects.create(
        email=normalized,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    send_mail(
        "Your Quantum OPS verification code",
        f"Your Quantum OPS verification code is {code}. It expires in 10 minutes. If you did not request it, ignore this message.",
        settings.DEFAULT_FROM_EMAIL,
        [normalized],
        fail_silently=False,
    )
    return challenge


@transaction.atomic
def consume_email_otp(email, code):
    challenge = EmailVerificationChallenge.objects.select_for_update().filter(
        email=email.strip().lower(), purpose="REGISTRATION", consumed_at__isnull=True
    ).order_by("-created_at").first()
    if not challenge or challenge.expires_at <= timezone.now() or challenge.attempts >= 5:
        return False
    challenge.attempts += 1
    valid = check_password(str(code), challenge.code_hash)
    if valid:
        challenge.consumed_at = timezone.now()
    challenge.save(update_fields=("attempts", "consumed_at", "updated_at"))
    return valid


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_invitation(*, organization, invited_by, email, scope, role, client=None, project=None):
    raw_token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        organization=organization,
        client=client,
        project=project,
        invited_by=invited_by,
        email=email.strip().lower(),
        scope=scope,
        role=role,
        token_hash=token_digest(raw_token),
        expires_at=timezone.now() + timedelta(days=7),
    )
    link = f"{settings.FRONTEND_ORIGIN}/quantum-ops/invitations/accept?token={raw_token}"
    send_mail(
        f"You are invited to {organization.name} on Quantum OPS",
        f"{invited_by.get_full_name() or invited_by.email} invited you to Quantum OPS. Accept within 7 days: {link}",
        settings.DEFAULT_FROM_EMAIL,
        [invitation.email],
        fail_silently=False,
    )
    return invitation
