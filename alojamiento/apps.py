from django.apps import AppConfig


class AlojamientoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'alojamiento'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(inicializar_datos_base, sender=self)


def inicializar_datos_base(sender, **kwargs):
    from .models import Rol, Municipio, TipoHabitacion, SitioTuristico

    roles_base = [
        ('Administrador', 'Control total del sistema, usuarios y reportes'),
        ('Gestor de Alojamiento', 'Gestión de alojamientos, habitaciones, tarifas y reportes'),
        ('Recepcionista', 'Gestión de reservas, huéspedes, check-in/check-out y pagos'),
        ('Cliente', 'Cliente que reserva alojamientos desde el portal web'),
    ]
    for nombre, desc in roles_base:
        Rol.objects.get_or_create(nombre=nombre, defaults={'descripcion': desc})

    municipios_guajira = [
        ('Riohacha', '44001', 11.544444, -72.907222, 'Capital de La Guajira, playas, malecón y reservas naturales.'),
        ('Maicao', '44430', 11.383333, -72.233333, 'Centro comercial fronterizo y cultural de La Guajira.'),
        ('Uribia', '44847', 11.713889, -72.265556, 'Capital indígena de Colombia, puerta hacia Cabo de la Vela y Punta Gallinas.'),
        ('Manaure', '44560', 11.775000, -72.445278, 'Famosa por sus charcas y extracción artesanal de sal marina.'),
        ('Dibulla', '44279', 11.273889, -73.310278, 'Destino ecoturístico entre la Sierra Nevada de Santa Marta y el mar Caribe.'),
        ('Palomino', '44279', 11.243611, -73.559444, 'Corregimiento de Dibulla reconocido por sus ríos, playas y ambiente eco-turístico.'),
        ('Cabo de la Vela', '44847', 12.203611, -72.144444, 'Destino emblemático wayuu con dunas, Pilón de Azúcar y playas desérticas.'),
        ('Punta Gallinas', '44847', 12.456111, -71.664167, 'Punto más septentrional de Colombia y Suramérica con dunas de Taroa.'),
        ('San Juan del Cesar', '44650', 10.770278, -73.003333, 'Tierra musical y cultural al sur de La Guajira.'),
        ('Fonseca', '44279', 10.885000, -72.848333, 'Municipio tradicional y comercial en el sur guajiro.'),
    ]
    municipios_obj = {}
    for nombre, dane, lat, lng, desc in municipios_guajira:
        m_obj, _ = Municipio.objects.get_or_create(
            nombre=nombre,
            defaults={
                'codigo_dane': dane,
                'latitud': lat,
                'longitud': lng,
                'descripcion': desc,
            }
        )
        municipios_obj[nombre] = m_obj

    tipos_hab = [
        ('Sencilla', 'Habitación cómoda para 1 persona'),
        ('Doble', 'Habitación para 2 personas con cama doble o dos sencillas'),
        ('Triple', 'Habitación para 3 personas'),
        ('Familiar', 'Amplia habitación para grupos o familias'),
        ('Suite', 'Habitación superior con espacio adicional y vista'),
        ('Cabaña / Eco-Habitación', 'Alojamiento natural o estilo cabaña'),
    ]
    for nombre, desc in tipos_hab:
        TipoHabitacion.objects.get_or_create(nombre=nombre, defaults={'descripcion': desc})

    sitios_base = [
        ('Riohacha', 'Malecón y Playa de Riohacha', 'Playa y Paseo', 'Recorrido costero con vista al mar Caribe y atardeceres.'),
        ('Riohacha', 'Santuario de Flora y Fauna Los Flamencos', 'Ecoturismo', 'Humedal costero famoso por sus flamencos rosados y avistamiento de aves.'),
        ('Manaure', 'Salinas de Manaure', 'Cultura y Naturaleza', 'Explora las charcas de sal y la tradición salinera wayuu.'),
        ('Cabo de la Vela', 'El Pilón de Azúcar y Faro', 'Paisaje y Playa', 'Mirador natural y playas icónicas del Cabo de la Vela.'),
        ('Punta Gallinas', 'Dunas de Taroa', 'Aventura', 'Grandes dunas de arena que se encuentran con el mar Caribe.'),
        ('Palomino', 'Río Palomino y Playa', 'Ecoturismo', 'Descenso en tubing por el río y descanso frente al mar.'),
    ]
    for m_nombre, s_nombre, cat, desc in sitios_base:
        m_obj = municipios_obj.get(m_nombre)
        if m_obj:
            SitioTuristico.objects.get_or_create(
                municipio=m_obj,
                nombre=s_nombre,
                defaults={'categoria': cat, 'descripcion': desc}
            )