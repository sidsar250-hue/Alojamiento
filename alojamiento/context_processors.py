from django.conf import settings
from .decorators import obtener_rol_usuario


def global_context(request):
    return {
        'rol_actual': obtener_rol_usuario(request.user),
        'GOOGLE_MAPS_API_KEY': getattr(settings, 'GOOGLE_MAPS_API_KEY', ''),
    }
