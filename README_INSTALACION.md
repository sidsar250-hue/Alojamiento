# SysHSENA — Sistema Integral de Alojamientos y Turismo de La Guajira

Proyecto final desarrollado en **Python + Django + MySQL + Bootstrap 5** con arquitectura de **una sola aplicación (`alojamiento`)**.

## Pasos para ejecutar en tu PC (Windows / Laragon / VS Code)

1. **Crear la base de datos en MySQL (Laragon / phpMyAdmin):**
   ```sql
   CREATE DATABASE syshsena_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
   *(Verifica en `syshsena_project/settings.py` los datos de `DATABASES` si tu usuario/contraseña de MySQL son distintos a `root` / vacío).*

2. **Crear y activar entorno virtual:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Ejecutar migraciones (crea automáticamente los 4 roles, los 15 municipios de La Guajira, tipos de habitación, servicios y sitios turísticos):**
   ```bash
   python manage.py makemigrations alojamiento
   python manage.py migrate
   ```

4. **Crear tu usuario Administrador:**
   ```bash
   python manage.py createsuperuser
   ```

5. **Iniciar el servidor:**
   ```bash
   python manage.py runserver
   ```
   - Portal público turístico: `http://127.0.0.1:8000/`
   - Inicio de sesión / Panel administrativo: `http://127.0.0.1:8000/login/`

## Configurar API Key de Google Maps (Opcional)
El sistema ya incluye un mapa interactivo funcional por coordenadas. Si tienes tu clave de **Google Maps JavaScript API**, agrégala en `syshsena_project/settings.py` en la variable `GOOGLE_MAPS_API_KEY = 'TU_CLAVE_AQUI'` para activar el marcador arrastrable y selección por clic en el mapa.
