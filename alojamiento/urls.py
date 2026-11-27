from django.urls import path
from . import views

urlpatterns = [
    # Portal público
    path('', views.inicio_publico, name='inicio_publico'),
    path('alojamiento/<int:alojamiento_id>/', views.detalle_alojamiento_publico, name='detalle_alojamiento_publico'),
    path('alojamiento/<int:alojamiento_id>/resena/', views.crear_resena_alojamiento, name='crear_resena_alojamiento'),

    # Autenticación
    path('login/', views.vista_login, name='login'),
    path('registro/', views.registro_cliente, name='registro_cliente'),
    path('logout/', views.vista_logout, name='logout'),

    # Portal del cliente
    path('mi-portal/', views.portal_cliente, name='portal_cliente'),
    path('mi-portal/perfil/', views.editar_perfil_cliente, name='editar_perfil_cliente'),
    path('mi-portal/reservar/<int:habitacion_id>/', views.reservar_cliente, name='reservar_cliente'),
    path('mi-portal/reserva/<int:reserva_id>/cancelar/', views.cancelar_reserva_cliente, name='cancelar_reserva_cliente'),

    # Panel interno (staff)
    path('panel/', views.dashboard, name='dashboard'),
    path('panel/usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('panel/usuarios/crear/', views.crear_usuario_panel, name='crear_usuario'),
    path('panel/usuarios/<int:perfil_id>/editar/', views.editar_usuario_panel, name='editar_usuario'),
    path('panel/usuarios/<int:perfil_id>/toggle/', views.toggle_usuario_panel, name='toggle_usuario'),

    path('panel/alojamientos/', views.gestion_alojamientos, name='gestion_alojamientos'),
    path('panel/alojamiento/', views.gestion_alojamientos, name='gestion_alojamiento'),
    path('panel/alojamiento/guardar/', views.guardar_alojamiento_panel, name='guardar_alojamiento'),
    path('panel/alojamiento/<int:alojamiento_id>/subir-imagenes/', views.subir_imagenes_alojamiento, name='subir_imagenes_alojamiento'),
    path('panel/alojamiento/imagen/<int:imagen_id>/principal/', views.marcar_imagen_principal, name='marcar_imagen_principal'),
    path('panel/alojamiento/imagen/<int:imagen_id>/eliminar/', views.eliminar_imagen_alojamiento, name='eliminar_imagen_alojamiento'),
    path('panel/alojamiento/<int:alojamiento_id>/eliminar/', views.eliminar_alojamiento, name='eliminar_alojamiento'),

    path('panel/habitaciones/', views.gestion_habitaciones, name='gestion_habitaciones'),
    path('panel/habitaciones/crear/', views.crear_habitacion_panel, name='crear_habitacion'),
    path('panel/habitaciones/<int:habitacion_id>/editar/', views.editar_habitacion, name='editar_habitacion'),
    path('panel/habitaciones/tipo/crear/', views.crear_tipo_habitacion, name='crear_tipo_habitacion'),

    path('panel/huespedes/', views.gestion_huespedes, name='gestion_huespedes'),
    path('panel/huespedes/crear/', views.crear_huesped_panel, name='crear_huesped'),
    path('panel/huespedes/<int:huesped_id>/editar/', views.editar_huesped, name='editar_huesped'),

    path('panel/reservas/', views.gestion_reservas, name='gestion_reservas'),
    path('panel/reservas/crear/', views.crear_reserva_panel, name='crear_reserva'),
    path('panel/reservas/<int:reserva_id>/estado/', views.cambiar_estado_reserva, name='cambiar_estado_reserva'),

    path('panel/estadias-pagos/', views.gestion_estadias_pagos, name='gestion_estadias_pagos'),
    path('panel/checkin-checkout/', views.gestion_checkin_checkout, name='gestion_checkin_checkout'),
    path('panel/checkin-checkout/<int:reserva_id>/checkin/', views.procesar_checkin, name='procesar_checkin'),
    path('panel/checkin-checkout/<int:reserva_id>/checkout/', views.procesar_checkout, name='procesar_checkout'),
    path('panel/checkin-checkout/estadias/', views.gestion_checkin_checkout, name='gestion_estadias'),
    path('panel/checkin-checkout/alias/', views.gestion_checkin_checkout, name='checkin_checkout'),

    path('panel/pagos/', views.gestion_pagos, name='gestion_pagos'),
    path('panel/pagos/registrar/', views.registrar_pago, name='registrar_pago'),

    path('panel/servicios/', views.gestion_servicios, name='gestion_servicios'),
    path('panel/servicios/crear/', views.crear_servicio_panel, name='crear_servicio'),
    path('panel/servicios/asociar/', views.asociar_servicio_reserva, name='asociar_servicio_reserva'),

    path('panel/reportes/', views.reportes_guajira, name='reportes_guajira'),
    path('panel/reportes/alias/', views.reportes_guajira, name='gestion_reportes'),
]
