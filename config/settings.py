import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
def env_bool(name, default):
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY es obligatoria fuera de DEBUG.")
    SECRET_KEY = "unsafe-development-key"
ALLOWED_HOSTS = [v.strip() for v in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if v.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "accounts", "organizations", "sales", "payments", "documents", "reports",
    "sii", "integrations", "imports", "audit",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.environ.get("POSTGRES_DB", "cuadratura"), "USER": os.environ.get("POSTGRES_USER", "cuadratura"), "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""), "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"), "PORT": os.environ.get("POSTGRES_PORT", "5432"), "CONN_MAX_AGE": 0}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTH_USER_MODEL = "accounts.User"
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "organization-list"
LOGOUT_REDIRECT_URL = "login"
SII_GATEWAY = os.environ.get("SII_GATEWAY", "disabled")
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True

# Endurecimiento HTTP (ADR 0006). Fuera de DEBUG las cookies solo viajan por HTTPS.
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
# Solo activar si el proxy elimina X-Forwarded-Proto entrante y lo fija él mismo.
if env_bool("DJANGO_TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# API v1 (ADR 0005 y 0006).
API_REQUIRE_HTTPS = env_bool("API_REQUIRE_HTTPS", not DEBUG)
API_REQUIRE_SIGNATURES = env_bool("API_REQUIRE_SIGNATURES", not DEBUG)
API_SIGNATURE_MAX_SKEW_SECONDS = int(os.environ.get("API_SIGNATURE_MAX_SKEW_SECONDS", "300"))
API_RATE_LIMIT_PER_MINUTE = int(os.environ.get("API_RATE_LIMIT_PER_MINUTE", "60"))
API_AUTH_FAILURE_LIMIT = int(os.environ.get("API_AUTH_FAILURE_LIMIT", "10"))
API_AUTH_FAILURE_WINDOW_MINUTES = int(os.environ.get("API_AUTH_FAILURE_WINDOW_MINUTES", "15"))
API_TOKEN_DEFAULT_DAYS = int(os.environ.get("API_TOKEN_DEFAULT_DAYS", "365"))
API_TOKEN_ROTATION_GRACE_HOURS = int(os.environ.get("API_TOKEN_ROTATION_GRACE_HOURS", "24"))
# Encabezado que fija el proxy con la IP real (p. ej. HTTP_X_REAL_IP). Vacío: REMOTE_ADDR.
API_CLIENT_IP_HEADER = os.environ.get("API_CLIENT_IP_HEADER", "").strip()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {"cuadratura.api.security": {"level": "INFO", "propagate": True}},
}
