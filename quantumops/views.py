from django.db import connection
import django
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def system_status(request):
    db_status = "Active"
    try:
        # Verify the PostgreSQL connection is active by running a simple query
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
    except Exception as e:
        db_status = f"Disconnected: {str(e)}"

    return Response({
        "status": "online",
        "db_status": db_status,
        "django_version": django.get_version(),
        "server": "Django dev container"
    })
