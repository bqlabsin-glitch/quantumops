from rest_framework.decorators import api_view
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import permission_classes
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_status(request):
    return Response({"status": "ok"})
