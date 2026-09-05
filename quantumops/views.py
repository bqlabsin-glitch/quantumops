import django
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import permission_classes
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def get_system_status():
    database = "Active"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
    except Exception:
        logger.exception("Database health check failed")
        database = "Disconnected"
    return {"status": "online", "db_status": database, "django_version": django.get_version(), "server": "Django application"}

@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_status(request):
    return Response(get_system_status())


@staff_member_required
def system_status_page(request):
    return render(request, 'admin/system_status.html', {'system_status': get_system_status()})
