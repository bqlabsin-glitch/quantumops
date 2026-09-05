"""Platform email configuration. Credentials never appear in API responses or audit data."""
import base64
import hashlib
import smtplib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import get_connection, send_mail
from rest_framework import serializers

from .models import PlatformEmailSettings


def cipher():
    # Domain-separated key; the Django secret must be retained with encrypted backups.
    key = hashlib.sha256((settings.SECRET_KEY + ":quantumops:smtp:v1").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class EmailSettingsSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=1024, trim_whitespace=False)
    password_set = serializers.SerializerMethodField()

    class Meta:
        model = PlatformEmailSettings
        fields = ("enabled", "host", "port", "username", "password", "password_set", "security", "from_email")

    def get_password_set(self, obj):
        return bool(obj.password_encrypted)

    def validate(self, attrs):
        if not 1 <= attrs.get("port", self.instance.port) <= 65535:
            raise serializers.ValidationError({"port": "Enter a port between 1 and 65535."})
        host = attrs.get("host", self.instance.host)
        if host and (any(c.isspace() for c in host) or any(c in host for c in "/\\:@")):
            raise serializers.ValidationError({"host": "Enter an SMTP hostname without a URL or port."})
        if attrs.get("enabled", self.instance.enabled) and (not host or not attrs.get("from_email", self.instance.from_email)):
            raise serializers.ValidationError("Enter the SMTP host and sender email before enabling delivery.")
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        if password:
            instance.password_encrypted = cipher().encrypt(password.encode()).decode()
        return super().update(instance, validated_data)


def send_platform_email(subject, message, recipients):
    config = PlatformEmailSettings.objects.filter(pk=1).first()
    if config is None:
        if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST:
            raise OSError("Email delivery is not configured.")
        return send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    if not config.enabled:
        raise OSError("Email delivery is disabled.")
    try:
        password = cipher().decrypt(config.password_encrypted.encode()).decode() if config.password_encrypted else ""
        with get_connection(
            "django.core.mail.backends.smtp.EmailBackend", host=config.host, port=config.port,
            username=config.username, password=password, use_tls=config.security == "STARTTLS",
            use_ssl=config.security == "SSL", timeout=10,
        ) as connection:
            return send_mail(subject, message, config.from_email, recipients, connection=connection, fail_silently=False)
    except (smtplib.SMTPException, InvalidToken) as exc:
        raise OSError("Email delivery failed. Check the saved settings.") from exc
