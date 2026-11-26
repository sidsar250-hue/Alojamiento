from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['id']

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='usuarios')
    telefono = models.CharField(max_length=25, blank=True)
    activo = models.BooleanField(default=True)
    tipo_documento = models.CharField(max_length=10, blank=True, default='CC')
    documento = models.CharField(max_length=30, blank=True, default='')

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f"{self.usuario.username} ({self.rol.nombre})"


class Municipio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_dane = models.CharField(max_length=10, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, default=11.544444)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, default=-72.907222)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Municipio'
        verbose_name_plural = 'Municipios de La Guajira'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class SitioTuristico(models.Model):
    municipio = models.ForeignKey(Municipio, on_delete=models.CASCADE, related_name='sitios_turisticos')
    nombre = models.CharField(max_length=150)
    categoria = models.CharField(max_length=80, default='Turismo')
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Sitio Turístico'
        verbose_name_plural = 'Sitios Turísticos'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - {self.municipio.nombre}"


class Alojamiento(models.Model):
    TIPO_CHOICES = [
        ('Hotel', 'Hotel'),
        ('Hostal', 'Hostal'),
        ('Cabaña', 'Cabaña'),
        ('Eco-Hotel', 'Eco-Hotel'),
        ('Posada', 'Posada'),
        ('Apartahotel', 'Apartahotel'),
    ]
    ESTADO_CHOICES = [
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
    ]

    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default='Hotel')
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT, related_name='alojamientos')
    direccion = models.CharField(max_length=200)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, default=11.544444)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, default=-72.907222)
    telefono = models.CharField(max_length=30)
    correo = models.EmailField()
    estrellas = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)])
    descripcion = models.TextField()
    servicios_incluidos = models.TextField(
        blank=True,
        help_text='Separados por coma. Ej: WiFi, Piscina, Aire acondicionado, Desayuno'
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='ACTIVO')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Alojamiento'
        verbose_name_plural = 'Alojamientos'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.municipio.nombre})"

    @property
    def lista_servicios_incluidos(self):
        if not self.servicios_incluidos:
            return []
        return [s.strip() for s in self.servicios_incluidos.split(',') if s.strip()]

    @property
    def promedio_estrellas(self):
        resenas = self.resenas.all()
        if not resenas.exists():
            return None
        total = sum(r.estrellas for r in resenas)
        return round(total / resenas.count(), 1)


class ImagenAlojamiento(models.Model):
    alojamiento = models.ForeignKey(Alojamiento, on_delete=models.CASCADE, related_name='imagenes')
    imagen = models.ImageField(upload_to='alojamientos/galeria/')
    titulo = models.CharField(max_length=120, blank=True)
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Imagen de Alojamiento'
        verbose_name_plural = 'Galería de Alojamientos'
        ordering = ['-id']

    def __str__(self):
        return f"Imagen {self.id} - {self.alojamiento.nombre}"


class TipoHabitacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Tipo de Habitación'
        verbose_name_plural = 'Tipos de Habitación'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Habitacion(models.Model):
    ESTADO_CHOICES = [
        ('DISPONIBLE', 'Disponible'),
        ('OCUPADA', 'Ocupada'),
        ('MANTENIMIENTO', 'Mantenimiento'),
    ]

    alojamiento = models.ForeignKey(Alojamiento, on_delete=models.CASCADE, related_name='habitaciones')
    tipo = models.ForeignKey(TipoHabitacion, on_delete=models.PROTECT, related_name='habitaciones')
    numero = models.CharField(max_length=20)
    piso = models.PositiveSmallIntegerField(default=1)
    capacidad = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1)])
    precio_noche = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    descripcion = models.TextField(blank=True)
    imagen = models.ImageField(upload_to='habitaciones/', blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='DISPONIBLE')

    class Meta:
        verbose_name = 'Habitación'
        verbose_name_plural = 'Habitaciones'
        unique_together = ('alojamiento', 'numero')
        ordering = ['alojamiento', 'piso', 'numero']

    def __str__(self):
        return f"{self.alojamiento.nombre} - Hab. {self.numero}"


class Huesped(models.Model):
    ORIGEN_CHOICES = [
        ('ALOJAMIENTO', 'Registrado por el alojamiento'),
        ('PORTAL_CLIENTE', 'Registrado desde el portal'),
    ]
    TIPO_DOC_CHOICES = [
        ('CC', 'Cédula de Ciudadanía'),
        ('CE', 'Cédula de Extranjería'),
        ('PA', 'Pasaporte'),
        ('TI', 'Tarjeta de Identidad'),
    ]

    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default='ALOJAMIENTO')
    tipo_documento = models.CharField(max_length=5, choices=TIPO_DOC_CHOICES, default='CC')
    numero_documento = models.CharField(max_length=30, unique=True)
    usuario = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='huesped')
    foto_perfil = models.ImageField(upload_to='perfiles_huespedes/', blank=True, null=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    telefono = models.CharField(max_length=25)
    correo = models.EmailField()
    nacionalidad = models.CharField(max_length=60, default='Colombiana')
    contacto_emergencia = models.CharField(max_length=150, blank=True)
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Huésped'
        verbose_name_plural = 'Huéspedes'
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        return f"{self.nombres} {self.apellidos} ({self.numero_documento})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()


class Reserva(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('CONFIRMADA', 'Confirmada'),
        ('EN_CURSO', 'En Curso'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
    ]
    ORIGEN_CHOICES = [
        ('WEB_CLIENTE', 'Portal Web Cliente'),
        ('RECEPCION', 'Recepción / Staff'),
    ]

    codigo = models.CharField(max_length=20, unique=True)
    alojamiento = models.ForeignKey(Alojamiento, on_delete=models.CASCADE, related_name='reservas')
    habitacion = models.ForeignKey(Habitacion, on_delete=models.PROTECT, related_name='reservas')
    huesped = models.ForeignKey(Huesped, on_delete=models.PROTECT, related_name='reservas')
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservas_creadas')
    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default='RECEPCION')
    fecha_entrada = models.DateField()
    fecha_salida = models.DateField()
    numero_huespedes = models.PositiveSmallIntegerField(default=1)
    noches = models.PositiveSmallIntegerField(default=1)
    precio_noche = models.DecimalField(max_digits=12, decimal_places=2)
    total_estimado = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Reserva'
        verbose_name_plural = 'Reservas'
        ordering = ['-creado_en']

    def __str__(self):
        return f"{self.codigo} - {self.huesped.nombre_completo}"


class ResenaAlojamiento(models.Model):
    alojamiento = models.ForeignKey(Alojamiento, on_delete=models.CASCADE, related_name='resenas')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resenas_alojamientos')
    estrellas = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Reseña de Alojamiento'
        verbose_name_plural = 'Reseñas de Alojamientos'
        ordering = ['-creado_en']
        unique_together = ('alojamiento', 'usuario')

    def __str__(self):
        return f"{self.alojamiento.nombre} - {self.usuario.username} ({self.estrellas}★)"


class Pago(models.Model):
    METODO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia Bancaria'),
        ('TARJETA', 'Tarjeta Débito/Crédito'),
        ('NEQUI_DAVIPLATA', 'Nequi / Daviplata'),
    ]
    ESTADO_CHOICES = [
        ('REGISTRADO', 'Registrado'),
        ('ANULADO', 'Anulado'),
    ]

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=25, choices=METODO_CHOICES, default='EFECTIVO')
    referencia = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='REGISTRADO')
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    notas = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-fecha_pago']

    def __str__(self):
        return f"Pago ${self.monto} - {self.reserva.codigo}"


class ServicioAdicional(models.Model):
    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name='servicios_adicionales')
    nombre = models.CharField(max_length=120)
    cantidad = models.PositiveSmallIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Servicio Adicional'
        verbose_name_plural = 'Servicios Adicionales'
        ordering = ['-registrado_en']

    def __str__(self):
        return f"{self.nombre} x{self.cantidad} ({self.reserva.codigo})"


class NovedadEstadia(models.Model):
    TIPO_CHOICES = [
        ('CHECK_IN', 'Check-In'),
        ('CHECK_OUT', 'Check-Out'),
        ('NOVEDAD', 'Novedad / Incidencia'),
    ]

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name='novedades')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='NOVEDAD')
    descripcion = models.TextField()
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Novedad de Estadía'
        verbose_name_plural = 'Novedades de Estadía'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.tipo} - {self.reserva.codigo}"
