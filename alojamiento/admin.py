from django.contrib import admin
from .models import (
    Rol, PerfilUsuario, Municipio, SitioTuristico, Alojamiento,
    ImagenAlojamiento, TipoHabitacion, Habitacion, Huesped,
    Reserva, ResenaAlojamiento, Pago, ServicioAdicional, NovedadEstadia
)


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'descripcion')


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'rol', 'telefono', 'activo')
    list_filter = ('rol', 'activo')


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'codigo_dane', 'latitud', 'longitud')
    search_fields = ('nombre',)


@admin.register(SitioTuristico)
class SitioTuristicoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'municipio', 'categoria')
    list_filter = ('municipio', 'categoria')


@admin.register(Alojamiento)
class AlojamientoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'tipo', 'municipio', 'estrellas', 'estado')
    list_filter = ('municipio', 'tipo', 'estado', 'estrellas')
    search_fields = ('nombre', 'direccion', 'correo')


@admin.register(ImagenAlojamiento)
class ImagenAlojamientoAdmin(admin.ModelAdmin):
    list_display = ('id', 'alojamiento', 'titulo', 'subido_en')
    list_filter = ('alojamiento',)


@admin.register(TipoHabitacion)
class TipoHabitacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')


@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'alojamiento', 'numero', 'tipo', 'piso', 'capacidad', 'precio_noche', 'estado')
    list_filter = ('alojamiento', 'tipo', 'estado')
    search_fields = ('numero', 'alojamiento__nombre')


@admin.register(Huesped)
class HuespedAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombres', 'apellidos', 'tipo_documento', 'numero_documento', 'origen', 'correo')
    list_filter = ('origen', 'tipo_documento', 'nacionalidad')
    search_fields = ('nombres', 'apellidos', 'numero_documento', 'correo')


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'alojamiento', 'habitacion', 'huesped', 'fecha_entrada', 'fecha_salida', 'noches', 'total_estimado', 'estado', 'origen')
    list_filter = ('estado', 'origen', 'alojamiento')
    search_fields = ('codigo', 'huesped__nombres', 'huesped__apellidos', 'huesped__numero_documento')


@admin.register(ResenaAlojamiento)
class ResenaAlojamientoAdmin(admin.ModelAdmin):
    list_display = ('id', 'alojamiento', 'usuario', 'estrellas', 'creado_en')
    list_filter = ('estrellas', 'alojamiento')
    search_fields = ('alojamiento__nombre', 'usuario__username', 'comentario')


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'reserva', 'monto', 'metodo', 'referencia', 'estado', 'fecha_pago')
    list_filter = ('metodo', 'estado')


@admin.register(ServicioAdicional)
class ServicioAdicionalAdmin(admin.ModelAdmin):
    list_display = ('id', 'reserva', 'nombre', 'cantidad', 'precio_unitario', 'subtotal')


@admin.register(NovedadEstadia)
class NovedadEstadiaAdmin(admin.ModelAdmin):
    list_display = ('id', 'reserva', 'tipo', 'fecha_registro')
    list_filter = ('tipo',)