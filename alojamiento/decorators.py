from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def obtener_rol_usuario(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'Administrador'
    perfil = getattr(user, 'perfil', None)
    if perfil and perfil.rol:
        return perfil.rol.nombre
    return None


def rol_requerido(*roles_permitidos):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            rol = obtener_rol_usuario(request.user)
            if rol in roles_permitidos or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'No tienes permisos para acceder a este módulo.')
            if rol == 'Cliente':
                return redirect('portal_cliente')
            return redirect('dashboard')
        return _wrapped_view
    return decorator
