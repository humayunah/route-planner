from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "route_planner",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

ROOT_URLCONF = "config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}

# Route planner settings
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
OSRM_BASE_URL = "https://router.project-osrm.org"
VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10
STATION_BUFFER_MILES = 25
ROUTE_SAMPLE_INTERVAL_MILES = 20
