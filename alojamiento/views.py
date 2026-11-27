import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q
from django.utils import timezone
from django.conf import settings

from .models import (
    Rol, PerfilUsuario, Municipio, SitioTuristico, Alojamiento,
    ImagenAlojamiento, TipoHabitacion, Habitacion, Huesped,
    Reserva, ResenaAlojamiento, Pago, ServicioAdicional, NovedadEstadia
)


def obtener_rol_usuario(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'Administrador'
    perfil = PerfilUsuario.objects.filter(usuario=user).select_related('rol').first()
    if perfil and perfil.rol:
        return perfil.rol.nombre
    return None


def tiene_rol(user, roles_permitidos):
    rol = obtener_rol_usuario(user)
    return rol in roles_permitidos


def generar_codigo_reserva():
    prefijo = f"RSH-{timezone.now().strftime('%y%m%d')}"
    ultimo = Reserva.objects.filter(codigo__startswith=prefijo).order_by('-id').first()
    consecutivo = 1
    if ultimo:
        try:
            consecutivo = int(ultimo.codigo.split('-')[-1]) + 1
        except (ValueError, IndexError):
            consecutivo = Reserva.objects.count() + 1
    return f"{prefijo}-{consecutivo:03d}"


def verificar_disponibilidad_habitacion(habitacion, fecha_entrada, fecha_salida, excluir_reserva_id=None):
    if habitacion.estado == 'MANTENIMIENTO':
        return False
    solapadas = Reserva.objects.filter(
        habitacion=habitacion,
        estado__in=['PENDIENTE', 'CONFIRMADA', 'EN_CURSO'],
        fecha_entrada__lt=fecha_salida,
        fecha_salida__gt=fecha_entrada,
    )
    if excluir_reserva_id:
        solapadas = solapadas.exclude(id=excluir_reserva_id)
    return not solapadas.exists()


def _obtener_o_crear_huesped_cliente(user):
    huesped = Huesped.objects.filter(usuario=user).first()
    if huesped:
        return huesped
    if user.email:
        huesped = Huesped.objects.filter(correo__iexact=user.email).first()
        if huesped:
            if not huesped.usuario:
                huesped.usuario = user
                huesped.origen = 'PORTAL_CLIENTE'
                huesped.save(update_fields=['usuario', 'origen'])
            return huesped
    doc_fallback = f"USR-{user.id}"
    huesped, _ = Huesped.objects.get_or_create(
        numero_documento=doc_fallback,
        defaults={
            'usuario': user,
            'origen': 'PORTAL_CLIENTE',
            'tipo_documento': 'CC',
            'nombres': user.first_name or user.username,
            'apellidos': user.last_name or '',
            'telefono': '',
            'correo': user.email or f"{user.username}@syshsena.local",
            'nacionalidad': 'Colombiana',
        }
    )
    return huesped


def inicio_publico(request):
    municipios = Municipio.objects.all()
    municipio_id = request.GET.get('municipio', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    q = request.GET.get('q', '').strip()

    alojamientos = Alojamiento.objects.filter(estado='ACTIVO').select_related('municipio').prefetch_related('imagenes', 'habitaciones', 'resenas')

    if municipio_id and municipio_id.isdigit():
        alojamientos = alojamientos.filter(municipio_id=int(municipio_id))
    if tipo:
        alojamientos = alojamientos.filter(tipo=tipo)
    if q:
        alojamientos = alojamientos.filter(
            Q(nombre__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(direccion__icontains=q) |
            Q(municipio__nombre__icontains=q)
        )

    sitios = SitioTuristico.objects.select_related('municipio')
    if municipio_id and municipio_id.isdigit():
        sitios = sitios.filter(municipio_id=int(municipio_id))

    return render(request, 'public/inicio.html', {
        'alojamientos': alojamientos,
        'municipios': municipios,
        'sitios': sitios[:8],
        'tipos_alojamiento': [c[0] for c in Alojamiento.TIPO_CHOICES],
        'filtro_municipio': municipio_id,
        'filtro_tipo': tipo,
        'filtro_q': q,
    })


def detalle_alojamiento_publico(request, alojamiento_id):
    alojamiento = get_object_or_404(
        Alojamiento.objects.select_related('municipio').prefetch_related('imagenes', 'habitaciones__tipo', 'resenas__usuario__huesped'),
        id=alojamiento_id,
        estado='ACTIVO'
    )
    habitaciones = alojamiento.habitaciones.all()
    sitios_cercanos = SitioTuristico.objects.filter(municipio=alojamiento.municipio)
    resenas = alojamiento.resenas.select_related('usuario', 'usuario__huesped').all()

    resena_usuario = None
    if request.user.is_authenticated:
        resena_usuario = resenas.filter(usuario=request.user).first()

    fecha_entrada = request.GET.get('fecha_entrada', '').strip()
    fecha_salida = request.GET.get('fecha_salida', '').strip()
    huespedes_req = request.GET.get('huespedes', '2').strip()

    noches_seleccionadas = 0
    f_in = None
    f_out = None
    if fecha_entrada and fecha_salida:
        try:
            f_in = datetime.strptime(fecha_entrada, '%Y-%m-%d').date()
            f_out = datetime.strptime(fecha_salida, '%Y-%m-%d').date()
            if f_out > f_in:
                noches_seleccionadas = (f_out - f_in).days
        except ValueError:
            f_in = None
            f_out = None

    habitaciones_info = []
    fechas_ocupadas_por_hab = {}

    for hab in habitaciones:
        reservas_hab = Reserva.objects.filter(
            habitacion=hab,
            estado__in=['PENDIENTE', 'CONFIRMADA', 'EN_CURSO']
        ).values_list('fecha_entrada', 'fecha_salida')

        rangos = []
        for ini, fin in reservas_hab:
            actual = ini
            while actual < fin:
                rangos.append(actual.strftime('%Y-%m-%d'))
                actual += timedelta(days=1)
        fechas_ocupadas_por_hab[str(hab.id)] = sorted(list(set(rangos)))

        disponible = hab.estado == 'DISPONIBLE'
        if f_in and f_out and f_out > f_in:
            disponible = verificar_disponibilidad_habitacion(hab, f_in, f_out)

        if huespedes_req and huespedes_req.isdigit():
            if hab.capacidad < int(huespedes_req):
                continue

        total_estadia = (hab.precio_noche * noches_seleccionadas) if noches_seleccionadas > 0 else hab.precio_noche
        habitaciones_info.append({
            'obj': hab,
            'disponible_fechas': disponible,
            'total_estadia': total_estadia,
        })

    return render(request, 'public/detalle_alojamiento.html', {
        'alojamiento': alojamiento,
        'habitaciones_info': habitaciones_info,
        'sitios_cercanos': sitios_cercanos,
        'resenas': resenas,
        'resena_usuario': resena_usuario,
        'fecha_entrada': fecha_entrada,
        'fecha_salida': fecha_salida,
        'huespedes_req': huespedes_req,
        'noches_seleccionadas': noches_seleccionadas,
        'fechas_ocupadas_json': json.dumps(fechas_ocupadas_por_hab),
        'GOOGLE_MAPS_API_KEY': getattr(settings, 'GOOGLE_MAPS_API_KEY', ''),
    })


@login_required
def crear_resena_alojamiento(request, alojamiento_id):
    if request.method != 'POST':
        return redirect('detalle_alojamiento_publico', alojamiento_id=alojamiento_id)

    alojamiento = get_object_or_404(Alojamiento, id=alojamiento_id, estado='ACTIVO')
    estrellas_raw = request.POST.get('estrellas', '5').strip()
    comentario = request.POST.get('comentario', '').strip()

    try:
        estrellas = int(estrellas_raw)
    except ValueError:
        estrellas = 0

    if estrellas < 1 or estrellas > 5:
        messages.error(request, 'Selecciona una calificación válida de 1 a 5 estrellas.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=alojamiento.id)

    if not comentario:
        messages.error(request, 'Escribe un comentario para publicar tu reseña.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=alojamiento.id)

    ResenaAlojamiento.objects.update_or_create(
        alojamiento=alojamiento,
        usuario=request.user,
        defaults={
            'estrellas': estrellas,
            'comentario': comentario,
        }
    )
    messages.success(request, '¡Tu reseña y calificación han sido guardadas!')
    return redirect('detalle_alojamiento_publico', alojamiento_id=alojamiento.id)


def vista_login(request):
    if request.user.is_authenticated:
        if tiene_rol(request.user, ['Cliente']):
            return redirect('portal_cliente')
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)
        if user is None and '@' in username:
            usuario_por_correo = User.objects.filter(email__iexact=username).first()
            if usuario_por_correo:
                user = authenticate(request, username=usuario_por_correo.username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, 'Tu cuenta se encuentra desactivada.')
                return render(request, 'auth/login.html')

            perfil = PerfilUsuario.objects.filter(usuario=user).select_related('rol').first()
            if perfil and not perfil.activo and not user.is_superuser:
                messages.error(request, 'Tu perfil de usuario está inactivo.')
                return render(request, 'auth/login.html')

            login(request, user)
            rol = obtener_rol_usuario(user)
            messages.success(request, f'Bienvenido a SysHSENA, {user.get_full_name() or user.username}.')

            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)

            if rol == 'Cliente':
                return redirect('portal_cliente')
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'auth/login.html')


def registro_cliente(request):
    if request.user.is_authenticated:
        return redirect('portal_cliente')

    if request.method == 'POST':
        nombres = request.POST.get('nombres', '').strip()
        apellidos = request.POST.get('apellidos', '').strip()
        tipo_doc = request.POST.get('tipo_documento', 'CC').strip()
        documento = request.POST.get('numero_documento', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        email = request.POST.get('correo', '').strip()
        nacionalidad = request.POST.get('nacionalidad', 'Colombiana').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        password2 = request.POST.get('password2', '').strip()

        if not all([nombres, apellidos, documento, email, username, password]):
            messages.error(request, 'Completa todos los campos obligatorios.')
            return render(request, 'auth/registro_cliente.html')

        if password != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(request, 'auth/registro_cliente.html')

        if len(password) < 6:
            messages.error(request, 'La contraseña debe tener al menos 6 caracteres.')
            return render(request, 'auth/registro_cliente.html')

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'Ese nombre de usuario ya está en uso.')
            return render(request, 'auth/registro_cliente.html')

        if Huesped.objects.filter(numero_documento=documento).exclude(usuario__isnull=True).exists():
            messages.error(request, 'Ya existe una cuenta asociada a ese número de documento.')
            return render(request, 'auth/registro_cliente.html')

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=nombres,
                    last_name=apellidos,
                )
                rol_cliente, _ = Rol.objects.get_or_create(
                    nombre='Cliente',
                    defaults={'descripcion': 'Cliente que reserva alojamientos desde el portal web'}
                )
                PerfilUsuario.objects.create(
                    usuario=user,
                    rol=rol_cliente,
                    telefono=telefono,
                    activo=True,
                )
                Huesped.objects.update_or_create(
                    numero_documento=documento,
                    defaults={
                        'usuario': user,
                        'origen': 'PORTAL_CLIENTE',
                        'tipo_documento': tipo_doc,
                        'nombres': nombres,
                        'apellidos': apellidos,
                        'telefono': telefono,
                        'correo': email,
                        'nacionalidad': nacionalidad or 'Colombiana',
                    }
                )
            login(request, user)
            messages.success(request, '¡Registro exitoso! Ya puedes reservar y gestionar tu perfil.')
            return redirect('portal_cliente')
        except IntegrityError:
            messages.error(request, 'No se pudo completar el registro por un dato duplicado.')

    return render(request, 'auth/registro_cliente.html')


@login_required
def vista_logout(request):
    logout(request)
    messages.info(request, 'Has cerrado sesión correctamente.')
    return redirect('inicio_publico')


@login_required
def portal_cliente(request):
    huesped = _obtener_o_crear_huesped_cliente(request.user)
    estado_filtro = request.GET.get('estado', 'TODAS').strip().upper()

    reservas_qs = Reserva.objects.filter(huesped=huesped).select_related(
        'alojamiento', 'habitacion', 'habitacion__tipo'
    ).prefetch_related('pagos', 'servicios_adicionales')

    total_reservas = reservas_qs.count()
    confirmadas_count = reservas_qs.filter(estado='CONFIRMADA').count()
    canceladas_count = reservas_qs.filter(estado='CANCELADA').count()
    finalizadas_count = reservas_qs.filter(estado='FINALIZADA').count()
    pendientes_count = reservas_qs.filter(estado='PENDIENTE').count()

    if estado_filtro in ['PENDIENTE', 'CONFIRMADA', 'EN_CURSO', 'FINALIZADA', 'CANCELADA']:
        reservas_listado = reservas_qs.filter(estado=estado_filtro)
    else:
        estado_filtro = 'TODAS'
        reservas_listado = reservas_qs

    return render(request, 'public/portal_cliente.html', {
        'huesped': huesped,
        'reservas': reservas_listado,
        'estado_filtro': estado_filtro,
        'total_reservas': total_reservas,
        'confirmadas_count': confirmadas_count,
        'canceladas_count': canceladas_count,
        'finalizadas_count': finalizadas_count,
        'pendientes_count': pendientes_count,
    })


@login_required
def editar_perfil_cliente(request):
    huesped = _obtener_o_crear_huesped_cliente(request.user)

    if request.method == 'POST':
        nombres = request.POST.get('nombres', '').strip()
        apellidos = request.POST.get('apellidos', '').strip()
        tipo_doc = request.POST.get('tipo_documento', huesped.tipo_documento).strip()
        numero_doc = request.POST.get('numero_documento', huesped.numero_documento).strip()
        telefono = request.POST.get('telefono', '').strip()
        correo = request.POST.get('correo', '').strip()
        nacionalidad = request.POST.get('nacionalidad', 'Colombiana').strip()
        contacto_emergencia = request.POST.get('contacto_emergencia', '').strip()

        if not nombres or not apellidos or not correo or not numero_doc:
            messages.error(request, 'Nombres, apellidos, documento y correo son obligatorios.')
            return redirect('editar_perfil_cliente')

        if Huesped.objects.filter(numero_documento=numero_doc).exclude(id=huesped.id).exists():
            messages.error(request, 'Ese número de documento ya está registrado por otro huésped.')
            return redirect('editar_perfil_cliente')

        try:
            with transaction.atomic():
                huesped.nombres = nombres
                huesped.apellidos = apellidos
                huesped.tipo_documento = tipo_doc
                huesped.numero_documento = numero_doc
                huesped.telefono = telefono
                huesped.correo = correo
                huesped.nacionalidad = nacionalidad or 'Colombiana'
                huesped.contacto_emergencia = contacto_emergencia
                huesped.origen = 'PORTAL_CLIENTE'
                huesped.usuario = request.user

                if 'foto_perfil' in request.FILES and request.FILES['foto_perfil']:
                    huesped.foto_perfil = request.FILES['foto_perfil']

                huesped.save()

                request.user.first_name = nombres
                request.user.last_name = apellidos
                request.user.email = correo
                request.user.save(update_fields=['first_name', 'last_name', 'email'])

                perfil = PerfilUsuario.objects.filter(usuario=request.user).first()
                if perfil:
                    perfil.telefono = telefono
                    perfil.save(update_fields=['telefono'])

            messages.success(request, 'Tu perfil y foto de perfil se actualizaron correctamente.')
            return redirect('portal_cliente')
        except IntegrityError:
            messages.error(request, 'No se pudo guardar tu perfil por un conflicto de datos.')

    return render(request, 'public/editar_perfil_cliente.html', {
        'huesped': huesped,
    })


@login_required
def reservar_cliente(request, habitacion_id):
    if request.method != 'POST':
        return redirect('inicio_publico')

    habitacion = get_object_or_404(Habitacion.objects.select_related('alojamiento'), id=habitacion_id)
    fecha_entrada_str = request.POST.get('fecha_entrada', '').strip()
    fecha_salida_str = request.POST.get('fecha_salida', '').strip()
    num_huespedes_str = request.POST.get('numero_huespedes', '1').strip()
    observaciones = request.POST.get('observaciones', '').strip()

    try:
        f_in = datetime.strptime(fecha_entrada_str, '%Y-%m-%d').date()
        f_out = datetime.strptime(fecha_salida_str, '%Y-%m-%d').date()
        num_huespedes = int(num_huespedes_str)
    except ValueError:
        messages.error(request, 'Selecciona fechas válidas en el calendario.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=habitacion.alojamiento.id)

    if f_in < date.today():
        messages.error(request, 'La fecha de entrada no puede ser anterior a hoy.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=habitacion.alojamiento.id)

    if f_out <= f_in:
        messages.error(request, 'La fecha de salida debe ser posterior a la fecha de entrada.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=habitacion.alojamiento.id)

    if num_huespedes < 1 or num_huespedes > habitacion.capacidad:
        messages.error(request, f'El número de huéspedes debe estar entre 1 y {habitacion.capacidad}.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=habitacion.alojamiento.id)

    if not verificar_disponibilidad_habitacion(habitacion, f_in, f_out):
        messages.error(request, 'La habitación ya está reservada en ese rango de fechas.')
        return redirect('detalle_alojamiento_publico', alojamiento_id=habitacion.alojamiento.id)

    huesped = _obtener_o_crear_huesped_cliente(request.user)
    noches = (f_out - f_in).days
    total = habitacion.precio_noche * noches

    reserva = Reserva.objects.create(
        codigo=generar_codigo_reserva(),
        alojamiento=habitacion.alojamiento,
        habitacion=habitacion,
        huesped=huesped,
        creado_por=request.user,
        origen='WEB_CLIENTE',
        fecha_entrada=f_in,
        fecha_salida=f_out,
        numero_huespedes=num_huespedes,
        noches=noches,
        precio_noche=habitacion.precio_noche,
        total_estimado=total,
        estado='PENDIENTE',
        observaciones=observaciones,
    )
    messages.success(request, f'Reserva {reserva.codigo} creada por {noches} noche(s). Total: ${total:,.0f}.')
    return redirect('portal_cliente')


@login_required
def cancelar_reserva_cliente(request, reserva_id):
    if request.method != 'POST':
        return redirect('portal_cliente')

    huesped = _obtener_o_crear_huesped_cliente(request.user)
    reserva = get_object_or_404(Reserva, id=reserva_id, huesped=huesped)

    if reserva.estado in ['PENDIENTE', 'CONFIRMADA']:
        reserva.estado = 'CANCELADA'
        reserva.save(update_fields=['estado', 'actualizado_en'])
        messages.success(request, f'La reserva {reserva.codigo} ha sido cancelada.')
    else:
        messages.warning(request, 'Solo puedes cancelar reservas pendientes o confirmadas.')

    return redirect('portal_cliente')


@login_required
def dashboard(request):
    if tiene_rol(request.user, ['Cliente']):
        return redirect('portal_cliente')

    rol = obtener_rol_usuario(request.user)
    total_alojamientos = Alojamiento.objects.count()
    total_habitaciones = Habitacion.objects.count()
    habitaciones_disponibles = Habitacion.objects.filter(estado='DISPONIBLE').count()
    reservas_activas = Reserva.objects.filter(estado__in=['PENDIENTE', 'CONFIRMADA', 'EN_CURSO']).count()
    ingresos_registrados = Pago.objects.filter(estado='REGISTRADO').aggregate(total=Sum('monto'))['total'] or Decimal('0')
    ultimas_reservas = Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped')[:8]

    return render(request, 'modulos/dashboard.html', {
        'rol_actual': rol,
        'active_menu': 'dashboard',
        'rol': rol,
        'total_alojamientos': total_alojamientos,
        'total_habitaciones': total_habitaciones,
        'habitaciones_disponibles': habitaciones_disponibles,
        'reservas_activas': reservas_activas,
        'ingresos_registrados': ingresos_registrados,
        'ultimas_reservas': ultimas_reservas,
    })



@login_required
def gestion_estadias_pagos(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para acceder a estadías y pagos.')
        return redirect('dashboard')

    reservas = Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped').prefetch_related(
        'pagos', 'servicios_adicionales', 'novedades'
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')
        reserva = get_object_or_404(
            Reserva.objects.select_related('habitacion', 'huesped').prefetch_related('pagos', 'servicios_adicionales'),
            id=int(request.POST.get('reserva_id'))
        )

        # Bloqueo global para reservas cerradas o canceladas
        if reserva.estado in ['FINALIZADA', 'CANCELADA']:
            messages.error(
                request,
                f'La reserva {reserva.codigo} está {reserva.get_estado_display().lower()} y no admite nuevos movimientos.'
            )
            return redirect('gestion_estadias_pagos')

        if accion == 'pago':
            monto = Decimal(request.POST.get('monto', '0').replace(',', '.') or '0')
            metodo = request.POST.get('metodo', 'EFECTIVO').strip()
            referencia = request.POST.get('referencia', '').strip()
            notas = request.POST.get('notas', '').strip()

            if reserva.saldo_pendiente <= 0:
                messages.warning(request, f'La reserva {reserva.codigo} ya tiene saldo $0.')
                return redirect('gestion_estadias_pagos')

            if monto <= 0:
                messages.error(request, 'El monto del pago debe ser mayor a $0.')
                return redirect('gestion_estadias_pagos')

            if monto > reserva.saldo_pendiente:
                messages.error(
                    request,
                    f'El monto ingresado (${monto:,.0f}) supera el saldo pendiente de ${reserva.saldo_pendiente:,.0f}.'
                )
                return redirect('gestion_estadias_pagos')

            Pago.objects.create(
                reserva=reserva,
                monto=monto,
                metodo=metodo,
                referencia=referencia,
                registrado_por=request.user,
                notas=notas,
            )
            messages.success(request, f'Pago de ${monto:,.0f} registrado en {reserva.codigo}.')
            return redirect('gestion_estadias_pagos')

        elif accion == 'servicio':
            nombre_serv = request.POST.get('nombre_servicio', '').strip()
            cantidad = int(request.POST.get('cantidad', '1') or 1)
            precio_u = Decimal(request.POST.get('precio_unitario', '0').replace(',', '.') or '0')

            if nombre_serv and cantidad > 0 and precio_u >= 0:
                subtotal = cantidad * precio_u
                ServicioAdicional.objects.create(
                    reserva=reserva,
                    nombre=nombre_serv,
                    cantidad=cantidad,
                    precio_unitario=precio_u,
                    subtotal=subtotal,
                )
                reserva.total_estimado = (reserva.total_estimado or Decimal('0')) + subtotal
                reserva.save(update_fields=['total_estimado', 'actualizado_en'])
                messages.success(request, f'Servicio "{nombre_serv}" agregado a {reserva.codigo}.')
            return redirect('gestion_estadias_pagos')

        elif accion == 'novedad':
            tipo = request.POST.get('tipo', 'NOVEDAD').strip()
            descripcion = request.POST.get('descripcion', '').strip()

            if tipo == 'CHECK_OUT' and reserva.saldo_pendiente > 0:
                messages.error(
                    request,
                    f'No se puede hacer check-out en {reserva.codigo}: tiene un saldo pendiente de ${reserva.saldo_pendiente:,.0f}.'
                )
                return redirect('gestion_estadias_pagos')

            if descripcion:
                NovedadEstadia.objects.create(
                    reserva=reserva,
                    tipo=tipo,
                    descripcion=descripcion,
                    registrado_por=request.user,
                )
                if tipo == 'CHECK_IN':
                    reserva.estado = 'EN_CURSO'
                    reserva.save(update_fields=['estado', 'actualizado_en'])
                    reserva.habitacion.estado = 'OCUPADA'
                    reserva.habitacion.save(update_fields=['estado'])
                elif tipo == 'CHECK_OUT':
                    reserva.estado = 'FINALIZADA'
                    reserva.save(update_fields=['estado', 'actualizado_en'])
                    reserva.habitacion.estado = 'DISPONIBLE'
                    reserva.habitacion.save(update_fields=['estado'])
                messages.success(request, f'Registro de {tipo} guardado en {reserva.codigo}.')
            return redirect('gestion_estadias_pagos')

    return render(request, 'modulos/checkin_checkout.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'checkin_checkout',
        'reservas': reservas,
    })



@login_required
def crear_usuario_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_usuarios(request)


@login_required
def guardar_alojamiento_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'editar' if post_data.get('alojamiento_id') else 'crear'
        request.POST = post_data
    return gestion_alojamientos(request)


@login_required
def crear_habitacion_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_habitaciones(request)


@login_required
def crear_huesped_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_huespedes(request)


@login_required
def crear_reserva_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_reservas(request)


@login_required
def gestion_checkin_checkout(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para acceder a Check-in / Check-out.')
        return redirect('dashboard')
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'novedad'
        request.POST = post_data
        gestion_estadias_pagos(request)
        return redirect('gestion_checkin_checkout')
    reservas = Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped').prefetch_related('novedades', 'pagos', 'servicios_adicionales')
    return render(request, 'modulos/checkin_checkout.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'checkin',
        'reservas': reservas,
    })


class _PagoVista:
    def __init__(self, pago):
        self._pago = pago
        self.id = pago.id
        self.reserva = pago.reserva
        self.monto = pago.monto
        self.fecha_pago = getattr(pago, 'fecha_pago', getattr(pago, 'creado_en', None))

        if hasattr(pago, 'get_metodo_pago_display'):
            self.get_metodo_pago_display = pago.get_metodo_pago_display()
        elif hasattr(pago, 'get_metodo_display'):
            self.get_metodo_pago_display = pago.get_metodo_display()
        else:
            self.get_metodo_pago_display = getattr(pago, 'metodo_pago', getattr(pago, 'metodo', 'Efectivo'))

        if hasattr(pago, 'get_tipo_pago_display'):
            self.get_tipo_pago_display = pago.get_tipo_pago_display()
        elif hasattr(pago, 'get_tipo_display'):
            self.get_tipo_pago_display = pago.get_tipo_display()
        else:
            self.get_tipo_pago_display = getattr(pago, 'tipo_pago', getattr(pago, 'tipo', 'Abono / Pago'))

    def __getattr__(self, name):
        return getattr(self._pago, name)


@login_required
def gestion_pagos(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para acceder a Pagos.')
        return redirect('dashboard')

    if request.method == 'POST':
        reserva_id = request.POST.get('reserva_id') or request.POST.get('reserva')
        reserva = Reserva.objects.prefetch_related('pagos', 'servicios_adicionales').filter(id=reserva_id).first()

        if not reserva:
            messages.error(request, 'Debes seleccionar una reserva válida.')
            return redirect('gestion_pagos')

        if reserva.estado in ['FINALIZADA', 'CANCELADA']:
            messages.error(
                request,
                f'No se pueden registrar pagos en la reserva {reserva.codigo} porque está {reserva.get_estado_display().lower()}.'
            )
            return redirect('gestion_pagos')

        if reserva.saldo_pendiente <= 0:
            messages.warning(
                request,
                f'La reserva {reserva.codigo} ya no tiene saldo pendiente por pagar.'
            )
            return redirect('gestion_pagos')

        post_data = request.POST.copy()
        post_data['accion'] = 'pago'
        post_data['reserva_id'] = str(reserva.id)
        if 'metodo_pago' in post_data and 'metodo' not in post_data:
            post_data['metodo'] = post_data['metodo_pago']
        request.POST = post_data
        gestion_estadias_pagos(request)
        return redirect('gestion_pagos')

    reservas_qs = (
        Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped')
        .prefetch_related('pagos', 'servicios_adicionales')
        .exclude(estado__in=['FINALIZADA', 'CANCELADA'])
        .order_by('-id')
    )
    reservas = [r for r in reservas_qs if r.saldo_pendiente > 0]

    pagos_qs = Pago.objects.select_related('reserva', 'reserva__huesped', 'reserva__alojamiento').order_by('-id')
    pagos_envueltos = [_PagoVista(p) for p in pagos_qs]

    metodos_pago = [
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('TARJETA', 'Tarjeta'),
        ('NEQUI_DAVIPLATA', 'Nequi / Daviplata'),
    ]

    return render(request, 'modulos/pagos.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'pagos',
        'page_obj': _paginar(request, pagos_envueltos),
        'reservas': reservas,
        'pagos': pagos_envueltos,
        'metodos_pago': metodos_pago,
    })


@login_required
def gestion_alojamientos(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Gerente']):
        messages.error(request, 'No tienes permiso para administrar alojamientos.')
        return redirect('dashboard')

    municipios = Municipio.objects.all()
    alojamientos = Alojamiento.objects.select_related('municipio').prefetch_related('imagenes', 'habitaciones')
    aloj_id = request.GET.get('id', '').strip()
    if aloj_id and aloj_id.isdigit():
        alojamiento = alojamientos.filter(id=int(aloj_id)).first()
    else:
        alojamiento = alojamientos.first()

    return render(request, 'modulos/alojamiento.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'alojamiento',
        'alojamiento': alojamiento,
        'alojamientos': alojamientos,
        'municipios': municipios,
        'tipos_alojamiento': Alojamiento.TIPO_CHOICES,
        'GOOGLE_MAPS_API_KEY': getattr(settings, 'GOOGLE_MAPS_API_KEY', ''),
    })


@login_required
def gestion_habitaciones(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para ver habitaciones.')
        return redirect('dashboard')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        if accion == 'crear':
            aloj = get_object_or_404(Alojamiento, id=int(request.POST.get('alojamiento_id')))
            tipo = get_object_or_404(TipoHabitacion, id=int(request.POST.get('tipo_id')))
            numero = request.POST.get('numero', '').strip()
            piso = int(request.POST.get('piso', '1') or 1)
            capacidad = int(request.POST.get('capacidad', '2') or 2)
            precio = Decimal(request.POST.get('precio_noche', '0').replace(',', '.') or '0')
            descripcion = request.POST.get('descripcion', '').strip()
            estado = request.POST.get('estado', 'DISPONIBLE').strip()
            imagen = request.FILES.get('imagen')
            try:
                Habitacion.objects.create(
                    alojamiento=aloj, tipo=tipo, numero=numero, piso=piso,
                    capacidad=capacidad, precio_noche=precio, descripcion=descripcion,
                    estado=estado, imagen=imagen,
                )
                messages.success(request, f'Habitación {numero} creada.')
            except IntegrityError:
                messages.error(request, f'Ya existe la habitación {numero} en {aloj.nombre}.')
            return redirect('gestion_habitaciones')
        elif accion == 'editar':
            hab = get_object_or_404(Habitacion, id=int(request.POST.get('habitacion_id')))
            hab.alojamiento = get_object_or_404(Alojamiento, id=int(request.POST.get('alojamiento_id')))
            hab.tipo = get_object_or_404(TipoHabitacion, id=int(request.POST.get('tipo_id')))
            hab.numero = request.POST.get('numero', hab.numero).strip()
            hab.piso = int(request.POST.get('piso', hab.piso) or 1)
            hab.capacidad = int(request.POST.get('capacidad', hab.capacidad) or 2)
            hab.precio_noche = Decimal(request.POST.get('precio_noche', hab.precio_noche).replace(',', '.'))
            hab.estado = request.POST.get('estado', hab.estado).strip()
            if request.FILES.get('imagen'):
                hab.imagen = request.FILES['imagen']
            hab.save()
            messages.success(request, f'Habitación {hab.numero} actualizada.')
            return redirect('gestion_habitaciones')

    q = request.GET.get('q', '').strip()
    aloj_f = request.GET.get('alojamiento', '').strip()
    estado_f = request.GET.get('estado', '').strip()

    qs = Habitacion.objects.select_related('alojamiento', 'tipo').order_by('id')
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(tipo__nombre__icontains=q))
    if aloj_f and aloj_f.isdigit():
        qs = qs.filter(alojamiento_id=int(aloj_f))
    if estado_f:
        qs = qs.filter(estado=estado_f)

    estados = [('DISPONIBLE', 'Disponible'), ('OCUPADA', 'Ocupada'), ('MANTENIMIENTO', 'Mantenimiento')]
    return render(request, 'modulos/habitaciones.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'habitaciones',
        'page_obj': _paginar(request, qs),
        'alojamientos': Alojamiento.objects.all(),
        'tipos': TipoHabitacion.objects.all(),
        'estados': estados,
        'filtros': {'q': q, 'alojamiento': aloj_f, 'estado': estado_f},
    })


@login_required
def gestion_huespedes(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para ver huéspedes.')
        return redirect('dashboard')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        if accion == 'crear':
            tipo_doc = request.POST.get('tipo_documento', 'CC').strip()
            numero_doc = request.POST.get('numero_documento', '').strip()
            nombres = request.POST.get('nombres', '').strip()
            apellidos = request.POST.get('apellidos', '').strip()
            telefono = request.POST.get('telefono', '').strip()
            correo = request.POST.get('correo', '').strip()
            nacionalidad = request.POST.get('nacionalidad', 'Colombiana').strip()
            contacto_emergencia = request.POST.get('contacto_emergencia', '').strip()
            try:
                Huesped.objects.create(
                    origen='ALOJAMIENTO', tipo_documento=tipo_doc, numero_documento=numero_doc,
                    nombres=nombres, apellidos=apellidos, telefono=telefono, correo=correo,
                    nacionalidad=nacionalidad, contacto_emergencia=contacto_emergencia,
                )
                messages.success(request, f'Huésped {nombres} {apellidos} registrado.')
            except IntegrityError:
                messages.error(request, 'Ya existe un huésped con ese documento.')
            return redirect('gestion_huespedes')
        elif accion == 'editar':
            huesped = get_object_or_404(Huesped, id=int(request.POST.get('huesped_id')))
            huesped.tipo_documento = request.POST.get('tipo_documento', huesped.tipo_documento).strip()
            huesped.numero_documento = request.POST.get('numero_documento', huesped.numero_documento).strip()
            huesped.nombres = request.POST.get('nombres', huesped.nombres).strip()
            huesped.apellidos = request.POST.get('apellidos', huesped.apellidos).strip()
            huesped.telefono = request.POST.get('telefono', huesped.telefono).strip()
            huesped.correo = request.POST.get('correo', huesped.correo).strip()
            huesped.nacionalidad = request.POST.get('nacionalidad', huesped.nacionalidad).strip()
            huesped.save()
            messages.success(request, 'Huésped actualizado.')
            return redirect('gestion_huespedes')

    q = request.GET.get('q', '').strip()
    qs = Huesped.objects.select_related('usuario').order_by('-id')
    if q:
        qs = qs.filter(
            Q(nombres__icontains=q) | Q(apellidos__icontains=q) |
            Q(numero_documento__icontains=q) | Q(correo__icontains=q)
        )
    tipos_doc = [('CC', 'Cédula de Ciudadanía'), ('CE', 'Cédula de Extranjería'), ('PAS', 'Pasaporte'), ('TI', 'Tarjeta de Identidad')]
    return render(request, 'modulos/huespedes.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'huespedes',
        'page_obj': _paginar(request, qs),
        'q': q,
        'tipos_doc': tipos_doc,
    })


@login_required
def gestion_reservas(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para gestionar reservas.')
        return redirect('dashboard')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        if accion == 'crear':
            hab = get_object_or_404(Habitacion.objects.select_related('alojamiento'), id=int(request.POST.get('habitacion_id')))
            huesped = get_object_or_404(Huesped, id=int(request.POST.get('huesped_id')))
            f_in = datetime.strptime(request.POST.get('fecha_entrada'), '%Y-%m-%d').date()
            f_out = datetime.strptime(request.POST.get('fecha_salida'), '%Y-%m-%d').date()
            num_huespedes = int(request.POST.get('numero_huespedes', '1') or 1)
            observaciones = request.POST.get('observaciones', '').strip()
            if f_out <= f_in:
                messages.error(request, 'La fecha de salida debe ser posterior a la entrada.')
                return redirect('gestion_reservas')
            if not verificar_disponibilidad_habitacion(hab, f_in, f_out):
                messages.error(request, 'La habitación ya está ocupada en esas fechas.')
                return redirect('gestion_reservas')
            noches = (f_out - f_in).days
            total = hab.precio_noche * noches
            Reserva.objects.create(
                codigo=generar_codigo_reserva(), alojamiento=hab.alojamiento, habitacion=hab,
                huesped=huesped, creado_por=request.user, origen='RECEPCION',
                fecha_entrada=f_in, fecha_salida=f_out, numero_huespedes=num_huespedes,
                noches=noches, precio_noche=hab.precio_noche, total_estimado=total,
                estado='CONFIRMADA', observaciones=observaciones,
            )
            messages.success(request, 'Reserva creada exitosamente.')
            return redirect('gestion_reservas')
        elif accion == 'cambiar_estado':
            reserva = get_object_or_404(Reserva, id=int(request.POST.get('reserva_id')))
            nuevo_estado = request.POST.get('estado', reserva.estado).strip()
            reserva.estado = nuevo_estado
            reserva.save(update_fields=['estado', 'actualizado_en'])
            messages.success(request, f'Reserva {reserva.codigo} actualizada a {nuevo_estado}.')
            return redirect('gestion_reservas')

    q = request.GET.get('q', '').strip()
    estado_f = request.GET.get('estado', '').strip()
    qs = Reserva.objects.select_related('alojamiento', 'habitacion', 'habitacion__tipo', 'huesped').order_by('-id')
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) | Q(huesped__nombres__icontains=q) |
            Q(huesped__apellidos__icontains=q) | Q(huesped__numero_documento__icontains=q)
        )
    if estado_f:
        qs = qs.filter(estado=estado_f)

    estados = [('PENDIENTE', 'Pendiente'), ('CONFIRMADA', 'Confirmada'), ('EN_CURSO', 'En curso'), ('FINALIZADA', 'Finalizada'), ('CANCELADA', 'Cancelada')]
    return render(request, 'modulos/reservas.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'reservas',
        'page_obj': _paginar(request, qs),
        'habitaciones': Habitacion.objects.select_related('alojamiento', 'tipo').all(),
        'huespedes': Huesped.objects.all(),
        'estados': estados,
        'filtros': {'q': q, 'estado': estado_f},
    })


@login_required
def reportes_guajira(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Gerente']):
        messages.error(request, 'No tienes permiso para ver reportes.')
        return redirect('dashboard')

    fecha_inicio = request.GET.get('fecha_inicio', '').strip()
    fecha_fin = request.GET.get('fecha_fin', '').strip()
    estado_f = request.GET.get('estado', '').strip()

    reservas_qs = Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped').prefetch_related('pagos')
    if fecha_inicio:
        reservas_qs = reservas_qs.filter(fecha_entrada__gte=fecha_inicio)
    if fecha_fin:
        reservas_qs = reservas_qs.filter(fecha_salida__lte=fecha_fin)
    if estado_f:
        reservas_qs = reservas_qs.filter(estado=estado_f)

    reservas = list(reservas_qs)
    total_recaudado = Pago.objects.filter(estado='REGISTRADO').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_habitaciones = Habitacion.objects.count()
    ocupadas = Habitacion.objects.filter(estado='OCUPADA').count()
    porcentaje_ocupacion = round((ocupadas / total_habitaciones) * 100, 1) if total_habitaciones else 0

    estados = [('PENDIENTE', 'Pendiente'), ('CONFIRMADA', 'Confirmada'), ('EN_CURSO', 'En curso'), ('FINALIZADA', 'Finalizada'), ('CANCELADA', 'Cancelada')]
    return render(request, 'modulos/reportes.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'reportes',
        'reservas': reservas,
        'total_recaudado': total_recaudado,
        'porcentaje_ocupacion': porcentaje_ocupacion,
        'ocupadas': ocupadas,
        'total_habitaciones': total_habitaciones,
        'estados': estados,
        'filtros': {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, 'estado': estado_f},
    })
from django.core.paginator import Paginator


def _paginar(request, queryset, per_page=10):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get('page', 1)
    return paginator.get_page(page_number)


@login_required
def crear_usuario_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_usuarios(request)


@login_required
def guardar_alojamiento_panel(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento']):
        messages.error(request, 'No tienes permiso para administrar alojamientos.')
        return redirect('dashboard')
    if request.method == 'POST':
        aloj_id = request.POST.get('alojamiento_id', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        tipo = request.POST.get('tipo', 'Hotel').strip()
        municipio_id = (request.POST.get('municipio') or request.POST.get('municipio_id') or '').strip()
        direccion = request.POST.get('direccion', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        correo = request.POST.get('correo', '').strip()
        estrellas = int(request.POST.get('estrellas', '3') or 3)
        descripcion = request.POST.get('descripcion', '').strip()
        servicios = request.POST.get('servicios_incluidos', '').strip()

        municipio = get_object_or_404(Municipio, id=int(municipio_id))
        lat_str = (request.POST.get('latitud', '').strip().replace(',', '.') or str(municipio.latitud))
        lng_str = (request.POST.get('longitud', '').strip().replace(',', '.') or str(municipio.longitud))

        if aloj_id:
            aloj = get_object_or_404(Alojamiento, id=int(aloj_id))
            aloj.nombre = nombre or aloj.nombre
            aloj.tipo = tipo or aloj.tipo
            aloj.municipio = municipio
            aloj.direccion = direccion or aloj.direccion
            aloj.latitud = Decimal(lat_str)
            aloj.longitud = Decimal(lng_str)
            aloj.telefono = telefono or aloj.telefono
            aloj.correo = correo or aloj.correo
            aloj.estrellas = estrellas
            aloj.descripcion = descripcion or aloj.descripcion
            aloj.servicios_incluidos = servicios
            aloj.save()
            messages.success(request, f'Alojamiento "{aloj.nombre}" actualizado.')
            return redirect(f"/panel/alojamiento/?id={aloj.id}")
        else:
            aloj = Alojamiento.objects.create(
                nombre=nombre,
                tipo=tipo,
                municipio=municipio,
                direccion=direccion,
                latitud=Decimal(lat_str),
                longitud=Decimal(lng_str),
                telefono=telefono,
                correo=correo,
                estrellas=estrellas,
                descripcion=descripcion,
                servicios_incluidos=servicios,
                estado='ACTIVO',
            )
            for idx, img in enumerate(request.FILES.getlist('imagenes')):
                ImagenAlojamiento.objects.create(alojamiento=aloj, imagen=img)
            messages.success(request, f'Alojamiento "{aloj.nombre}" creado.')
            return redirect(f"/panel/alojamiento/?id={aloj.id}")
    return redirect('gestion_alojamiento')


@login_required
def subir_imagenes_alojamiento(request, alojamiento_id):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento']):
        messages.error(request, 'No tienes permiso para subir imágenes.')
        return redirect('dashboard')
    aloj = get_object_or_404(Alojamiento, id=alojamiento_id)
    if request.method == 'POST':
        marcar_principal = request.POST.get('marcar_principal') == 'on'
        archivos = request.FILES.getlist('imagenes')
        for idx, img in enumerate(archivos):
            es_prin = marcar_principal and idx == 0
            if es_prin:
                aloj.imagenes.update(es_principal=False)
            ImagenAlojamiento.objects.create(alojamiento=aloj, imagen=img, es_principal=es_prin)
        messages.success(request, f'Se subieron {len(archivos)} imagen(es) a "{aloj.nombre}".')
    return redirect(f"/panel/alojamiento/?id={aloj.id}")


@login_required
def marcar_imagen_principal(request, imagen_id):
    img = get_object_or_404(ImagenAlojamiento, id=imagen_id)
    img.alojamiento.imagenes.update(es_principal=False)
    img.es_principal = True
    img.save(update_fields=['es_principal'])
    messages.success(request, 'Imagen marcada como principal.')
    return redirect(f"/panel/alojamiento/?id={img.alojamiento.id}")


@login_required
def eliminar_imagen_alojamiento(request, imagen_id):
    img = get_object_or_404(ImagenAlojamiento, id=imagen_id)
    aloj_id = img.alojamiento.id
    img.delete()
    messages.success(request, 'Imagen eliminada de la galería.')
    return redirect(f"/panel/alojamiento/?id={aloj_id}")


@login_required
def crear_habitacion_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        if 'alojamiento' in post_data and 'alojamiento_id' not in post_data:
            post_data['alojamiento_id'] = post_data['alojamiento']
        if 'tipo' in post_data and 'tipo_id' not in post_data:
            post_data['tipo_id'] = post_data['tipo']
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_habitaciones(request)


@login_required
def editar_habitacion(request, habitacion_id):
    hab = get_object_or_404(Habitacion, id=habitacion_id)
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'editar'
        post_data['habitacion_id'] = str(hab.id)
        if 'alojamiento' in post_data and 'alojamiento_id' not in post_data:
            post_data['alojamiento_id'] = post_data['alojamiento']
        if 'tipo' in post_data and 'tipo_id' not in post_data:
            post_data['tipo_id'] = post_data['tipo']
        request.POST = post_data
    return gestion_habitaciones(request)


@login_required
def crear_tipo_habitacion(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento']):
        messages.error(request, 'No tienes permiso para crear tipos de habitación.')
        return redirect('gestion_habitaciones')
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        cap = int(request.POST.get('capacidad_sugerida', '2') or 2)
        desc = request.POST.get('descripcion', '').strip()
        if nombre:
            TipoHabitacion.objects.get_or_create(
                nombre=nombre,
                defaults={'capacidad_sugerida': cap, 'descripcion': desc}
            )
            messages.success(request, f'Tipo de habitación "{nombre}" guardado.')
    return redirect('gestion_habitaciones')


@login_required
def crear_huesped_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        request.POST = post_data
    return gestion_huespedes(request)


@login_required
def editar_huesped(request, huesped_id):
    huesped = get_object_or_404(Huesped, id=huesped_id)
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'editar'
        post_data['huesped_id'] = str(huesped.id)
        request.POST = post_data
    return gestion_huespedes(request)


@login_required
def crear_reserva_panel(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'crear'
        if 'huesped' in post_data and 'huesped_id' not in post_data:
            post_data['huesped_id'] = post_data['huesped']
        if 'habitacion' in post_data and 'habitacion_id' not in post_data:
            post_data['habitacion_id'] = post_data['habitacion']
        if 'alojamiento_id' not in post_data and post_data.get('habitacion_id'):
            hab_obj = Habitacion.objects.filter(id=int(post_data['habitacion_id'])).first()
            if hab_obj:
                post_data['alojamiento_id'] = str(hab_obj.alojamiento_id)
        request.POST = post_data
    return gestion_reservas(request)


@login_required
def cambiar_estado_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'cambiar_estado'
        post_data['reserva_id'] = str(reserva.id)
        request.POST = post_data
    return gestion_reservas(request)


@login_required
def gestion_checkin_checkout(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para acceder a Check-in / Check-out.')
        return redirect('dashboard')
    reservas_llegada = Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped').filter(
        estado__in=['PENDIENTE', 'CONFIRMADA']
    )
    reservas_hospedadas = Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped').filter(
        estado='EN_CURSO'
    )
    return render(request, 'modulos/checkin_checkout.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'checkin',
        'reservas_llegada': reservas_llegada,
        'reservas_hospedadas': reservas_hospedadas,
    })


@login_required
def procesar_checkin(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.method == 'POST':
        reserva.estado = 'EN_CURSO'
        reserva.save(update_fields=['estado', 'actualizado_en'])
        reserva.habitacion.estado = 'OCUPADA'
        reserva.habitacion.save(update_fields=['estado'])
        NovedadEstadia.objects.create(
            reserva=reserva,
            tipo='CHECK_IN',
            descripcion=f'Check-in registrado para {reserva.huesped.nombre_completo}',
            registrado_por=request.user,
        )
        messages.success(request, f'Check-in registrado para la reserva {reserva.codigo}.')
    return redirect('gestion_checkin_checkout')


@login_required
def procesar_checkout(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related('habitacion', 'huesped').prefetch_related('pagos', 'servicios_adicionales'),
        id=reserva_id
    )
    if request.method == 'POST':
        if reserva.saldo_pendiente > 0:
            messages.error(
                request,
                f'No se puede completar el check-out de {reserva.codigo}: tiene un saldo pendiente de ${reserva.saldo_pendiente:,.0f}. Registra el pago antes de finalizar.'
            )
            return redirect('gestion_checkin_checkout')

        reserva.estado = 'FINALIZADA'
        reserva.save(update_fields=['estado', 'actualizado_en'])
        reserva.habitacion.estado = 'DISPONIBLE'
        reserva.habitacion.save(update_fields=['estado'])
        NovedadEstadia.objects.create(
            reserva=reserva,
            tipo='CHECK_OUT',
            descripcion=f'Check-out registrado para {reserva.huesped.nombre_completo}',
            registrado_por=request.user,
        )
        messages.success(request, f'Check-out registrado para la reserva {reserva.codigo}.')
    return redirect('gestion_checkin_checkout')


@login_required
def registrar_pago(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para registrar pagos.')
        return redirect('dashboard')
    if request.method == 'POST':
        reserva_id = request.POST.get('reserva') or request.POST.get('reserva_id')
        reserva = get_object_or_404(Reserva, id=int(reserva_id))
        monto = Decimal(request.POST.get('monto', '0').replace(',', '.') or '0')
        metodo = (request.POST.get('metodo_pago') or request.POST.get('metodo') or 'EFECTIVO').strip()
        referencia = request.POST.get('referencia', '').strip()
        if monto > 0:
            Pago.objects.create(
                reserva=reserva,
                monto=monto,
                metodo=metodo,
                referencia=referencia,
                registrado_por=request.user,
            )
            messages.success(request, f'Pago de ${monto:,.0f} registrado en {reserva.codigo}.')
    return redirect('gestion_pagos')
@login_required
def crear_servicio_panel(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento']):
        messages.error(request, 'No tienes permiso para crear servicios.')
        return redirect('gestion_servicios')
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        precio = Decimal(request.POST.get('precio', '0').replace(',', '.') or '0')
        descripcion = request.POST.get('descripcion', '').strip()
        if nombre and precio >= 0:
            # Si tu modelo ServicioAdicional es de catálogo o asociado a reserva, lo creamos de forma segura
            fields = {f.name for f in ServicioAdicional._meta.fields}
            if 'reserva' in fields:
                reserva = Reserva.objects.first()
                if reserva:
                    ServicioAdicional.objects.create(
                        reserva=reserva,
                        nombre=nombre,
                        cantidad=1,
                        precio_unitario=precio,
                        subtotal=precio,
                    )
            else:
                ServicioAdicional.objects.create(
                    nombre=nombre,
                    precio=precio,
                    descripcion=descripcion,
                )
            messages.success(request, f'Servicio "{nombre}" guardado.')
    return redirect('gestion_servicios')


@login_required
def asociar_servicio_reserva(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para asociar servicios.')
        return redirect('gestion_servicios')

    if request.method == 'POST':
        reserva_id = request.POST.get('reserva') or request.POST.get('reserva_id')
        if not reserva_id or not str(reserva_id).isdigit():
            messages.error(request, 'Debes seleccionar una reserva válida.')
            return redirect('gestion_servicios')

        reserva = get_object_or_404(Reserva, id=int(reserva_id))

        if reserva.estado in ['FINALIZADA', 'CANCELADA']:
            messages.error(
                request,
                f'No se pueden asociar servicios a la reserva {reserva.codigo} porque está {reserva.get_estado_display().lower()}.'
            )
            return redirect('gestion_servicios')

        servicio_id = request.POST.get('servicio')
        cantidad = int(request.POST.get('cantidad', '1') or 1)
        if cantidad <= 0:
            messages.error(request, 'La cantidad debe ser mayor a 0.')
            return redirect('gestion_servicios')

        if servicio_id and servicio_id.isdigit():
            serv_cat = ServicioAdicional.objects.filter(id=int(servicio_id)).first()
            if not serv_cat:
                messages.error(request, 'El servicio seleccionado no existe.')
                return redirect('gestion_servicios')
            nombre_serv = serv_cat.nombre
            precio_u = (
                getattr(serv_cat, 'precio', None)
                or getattr(serv_cat, 'precio_unitario', None)
                or Decimal('0')
            )
        else:
            nombre_serv = request.POST.get('nombre_servicio', 'Servicio adicional').strip()
            precio_u = Decimal(request.POST.get('precio_unitario', '0').replace(',', '.') or '0')

        subtotal = Decimal(cantidad) * Decimal(precio_u)
        ServicioAdicional.objects.create(
            reserva=reserva,
            nombre=nombre_serv,
            cantidad=cantidad,
            precio_unitario=precio_u,
            subtotal=subtotal,
        )
        reserva.total_estimado = (reserva.total_estimado or Decimal('0')) + subtotal
        reserva.save(update_fields=['total_estimado', 'actualizado_en'])
        messages.success(request, f'Servicio "{nombre_serv}" asociado a {reserva.codigo}.')

    return redirect('gestion_servicios')

class _ConsumoVista:
    def __init__(self, consumo):
        self._consumo = consumo
        self.id = consumo.id
        self.reserva = getattr(consumo, 'reserva', None)
        self.cantidad = getattr(consumo, 'cantidad', 1)
        self.subtotal = getattr(consumo, 'subtotal', 0)

        precio = (
            getattr(consumo, 'precio_unitario', None)
            or getattr(consumo, 'precio', None)
            or self.subtotal
            or 0
        )
        self.precio_unitario = precio
        self.precio = precio

        nombre = getattr(consumo, 'nombre', '') or getattr(consumo, 'nombre_servicio', '')
        self.nombre = nombre
        self.nombre_servicio = nombre
        self.servicio = type('ServicioNombre', (), {'nombre': nombre, 'precio': precio})()

    def __getattr__(self, name):
        return getattr(self._consumo, name)
@login_required
@login_required
def gestion_servicios(request):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento', 'Recepcionista']):
        messages.error(request, 'No tienes permiso para acceder a Servicios.')
        return redirect('dashboard')

    consumos_qs = ServicioAdicional.objects.select_related('reserva', 'reserva__huesped').order_by('-id')
    consumos = [_ConsumoVista(c) for c in consumos_qs]

    catalogo_por_nombre = {}
    for c in consumos:
        clave = c.nombre.strip().lower()
        if clave and clave not in catalogo_por_nombre:
            catalogo_por_nombre[clave] = c
    catalogo = list(catalogo_por_nombre.values())

    reservas = (
        Reserva.objects.select_related('alojamiento', 'habitacion', 'huesped')
        .exclude(estado__in=['FINALIZADA', 'CANCELADA'])
        .order_by('-id')
    )

    return render(request, 'modulos/servicios.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'servicios',
        'servicios': catalogo,
        'consumos': consumos,
        'reservas': reservas,
    })

class _PerfilVista:
    def __init__(self, perfil):
        self._perfil = perfil
        self.id = perfil.id
        self.user = perfil.usuario
        self.usuario = perfil.usuario
        self.rol = perfil.rol
        self.telefono = getattr(perfil, 'telefono', '')
        self.activo = getattr(perfil, 'activo', perfil.usuario.is_active)
        self.foto_perfil = getattr(perfil, 'foto_perfil', None)
        
        huesped_rel = getattr(perfil.usuario, 'huesped', None)
        self.tipo_documento = (
            getattr(perfil, 'tipo_documento', '')
            or (getattr(huesped_rel, 'tipo_documento', '') if huesped_rel else '')
        )
        self.documento = (
            getattr(perfil, 'documento', '')
            or (getattr(huesped_rel, 'numero_documento', '') if huesped_rel else '')
        )
    def __getattr__(self, name):
        return getattr(self._perfil, name)


@login_required
def gestion_usuarios(request):
    if not tiene_rol(request.user, ['Administrador']):
        messages.error(request, 'Solo el Administrador puede gestionar usuarios y roles.')
        return redirect('dashboard')

    roles = Rol.objects.all()
    roles_fijos = ['Administrador', 'Gerente', 'Recepcionista', 'Cliente']

    if request.method == 'POST':
        accion = request.POST.get('accion', 'crear')
        if accion == 'crear':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            telefono = request.POST.get('telefono', '').strip()
            documento = request.POST.get('documento', '').strip()
            password = request.POST.get('password', '').strip()
            rol_valor = (request.POST.get('rol_id') or request.POST.get('rol') or '').strip()

            if not username or not password or not rol_valor:
                messages.error(request, 'Usuario, contraseña y rol son obligatorios.')
                return redirect('gestion_usuarios')

            if User.objects.filter(username__iexact=username).exists():
                messages.error(request, 'Ese nombre de usuario ya existe.')
                return redirect('gestion_usuarios')

            if PerfilUsuario.objects.filter(documento__iexact=documento).exists():
                messages.error(request, 'numero de documento ya existe.')
                return redirect('gestion_usuarios')

            if rol_valor.isdigit():
                rol_obj = get_object_or_404(Rol, id=int(rol_valor))
            else:
                rol_obj, _ = Rol.objects.get_or_create(
                    nombre=rol_valor,
                    defaults={'descripcion': f'Rol {rol_valor}'}
                )

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            PerfilUsuario.objects.create(
                usuario=user,
                rol=rol_obj,
                telefono=telefono,
                documento=documento,
                activo=True,
            )
            messages.success(request, f'Usuario {username} creado con rol {rol_obj.nombre}.')
            return redirect('gestion_usuarios')

        elif accion == 'editar':
            user_id = request.POST.get('user_id')
            usuario_edit = get_object_or_404(User, id=int(user_id))
            usuario_edit.first_name = request.POST.get('first_name', '').strip()
            usuario_edit.last_name = request.POST.get('last_name', '').strip()
            usuario_edit.email = request.POST.get('email', '').strip()
            activo = request.POST.get('activo') == 'on' if 'activo' in request.POST else True
            usuario_edit.is_active = activo
            usuario_edit.save()

            rol_valor = (request.POST.get('rol_id') or request.POST.get('rol') or '').strip()
            telefono = request.POST.get('telefono', '').strip()
            documento = request.POST.get('documento', '').strip()
            if rol_valor.isdigit():
                rol_obj = get_object_or_404(Rol, id=int(rol_valor))
            else:
                rol_obj, _ = Rol.objects.get_or_create(
                    nombre=rol_valor,
                    defaults={'descripcion': f'Rol {rol_valor}'}
                )

            perfil, _ = PerfilUsuario.objects.get_or_create(usuario=usuario_edit, defaults={'rol': rol_obj})
            perfil.rol = rol_obj
            perfil.telefono = telefono
            perfil.documento = documento
            if PerfilUsuario.objects.filter(documento__iexact=documento).exists():
                messages.error(request, 'numero de documento ya existe.')
                return redirect('gestion_usuarios')

            perfil.activo = activo
            perfil.save()

            messages.success(request, f'Usuario {usuario_edit.username} actualizado.')
            return redirect('gestion_usuarios')

    q = request.GET.get('q', '').strip()
    rol_filtro = request.GET.get('rol', '').strip()

    perfiles_qs = PerfilUsuario.objects.select_related('usuario', 'rol').order_by('id')
    if q:
        perfiles_qs = perfiles_qs.filter(
            Q(usuario__username__icontains=q) |
            Q(usuario__first_name__icontains=q) |
            Q(usuario__last_name__icontains=q) |
            Q(usuario__email__icontains=q) |
            Q(telefono__icontains=q)
        )
    if rol_filtro:
        perfiles_qs = perfiles_qs.filter(rol__nombre__iexact=rol_filtro)

    perfiles_envueltos = [_PerfilVista(p) for p in perfiles_qs]

    return render(request, 'modulos/usuarios.html', {
        'rol_actual': obtener_rol_usuario(request.user),
        'active_menu': 'usuarios',
        'page_obj': _paginar(request, perfiles_envueltos),
        'usuarios': User.objects.select_related('perfil', 'perfil__rol').order_by('id'),
        'roles': roles,
        'roles_fijos': roles_fijos,
        'q': q,
        'rol_filtro': rol_filtro,
    })


@login_required
def editar_usuario_panel(request, perfil_id):
    if not tiene_rol(request.user, ['Administrador']):
        messages.error(request, 'Solo el Administrador puede editar usuarios.')
        return redirect('dashboard')
    perfil = get_object_or_404(PerfilUsuario.objects.select_related('usuario', 'rol'), id=perfil_id)
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['accion'] = 'editar'
        post_data['user_id'] = str(perfil.usuario.id)
        if 'activo' not in post_data:
            post_data['activo'] = 'on' if perfil.activo else ''
        request.POST = post_data
    return gestion_usuarios(request)


@login_required
def toggle_usuario_panel(request, perfil_id):
    if not tiene_rol(request.user, ['Administrador']):
        messages.error(request, 'Solo el Administrador puede cambiar el estado de usuarios.')
        return redirect('dashboard')
    perfil = get_object_or_404(PerfilUsuario.objects.select_related('usuario'), id=perfil_id)
    nuevo_estado = not perfil.activo
    perfil.activo = nuevo_estado
    perfil.save(update_fields=['activo'])
    perfil.usuario.is_active = nuevo_estado
    perfil.usuario.save(update_fields=['is_active'])
    messages.success(request, f'Usuario {perfil.usuario.username} {"activado" if nuevo_estado else "desactivado"}.')
    return redirect('gestion_usuarios')

@login_required
def eliminar_alojamiento(request, alojamiento_id):
    if not tiene_rol(request.user, ['Administrador', 'Gestor de Alojamiento']):
        messages.error(request, 'No tienes permiso para eliminar alojamientos.')
        return redirect('gestion_alojamiento')

    if request.method == 'POST':
        aloj = get_object_or_404(Alojamiento, id=alojamiento_id)

        tiene_reservas_activas = Reserva.objects.filter(
            alojamiento=aloj,
            estado__in=['PENDIENTE', 'CONFIRMADA', 'EN_CURSO'],
        ).exists()

        if tiene_reservas_activas:
            messages.error(
                request,
                f'No se puede eliminar "{aloj.nombre}" porque tiene reservas activas.'
            )
            return redirect('gestion_alojamiento')

        nombre = aloj.nombre
        aloj.delete()
        messages.success(request, f'Alojamiento "{nombre}" eliminado correctamente.')

    return redirect('gestion_alojamiento')