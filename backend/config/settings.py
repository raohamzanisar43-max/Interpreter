"""EQAL settings. SQLite by default; set EQAL_DB_NAME (+ EQAL_DB_USER/PASSWORD/HOST/PORT) to switch to PostgreSQL."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


DEBUG = env("EQAL_DEBUG", "1") == "1"
SECRET_KEY = env("EQAL_SECRET_KEY", "dev-only-insecure-secret-key-change-me-in-production-0123456789")
ALLOWED_HOSTS = ["*"] if DEBUG else env("EQAL_ALLOWED_HOSTS", "localhost").split(",")
FRONTEND_URL = env("EQAL_FRONTEND_URL", "http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "accounts",
    "organisations",
    "rounds",
    "submissions",
    "rating",
    "reports",
    "notifications",
    "compliance",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

if env("EQAL_DB_NAME"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("EQAL_DB_NAME"), "USER": env("EQAL_DB_USER", ""), "PASSWORD": env("EQAL_DB_PASSWORD", ""),
        "HOST": env("EQAL_DB_HOST", "localhost"), "PORT": env("EQAL_DB_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": env("EQAL_SQLITE_PATH", str(BASE_DIR / "db.sqlite3"))}}

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# Private file storage: nothing is served directly, only through short-lived signed URLs.
MEDIA_ROOT = Path(env("EQAL_MEDIA_ROOT", str(BASE_DIR / "media_private")))
SIGNED_URL_TTL = int(env("EQAL_SIGNED_URL_TTL", "600"))
MAX_UPLOAD_MB = int(env("EQAL_MAX_UPLOAD_MB", "50"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(MEDIA_ROOT)}},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

EMAIL_BACKEND = env("EQAL_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("EQAL_FROM_EMAIL", "EQAL <no-reply@eqal.example>")

# 2FA is mandatory for admin + rater. Only disable for local experiments.
REQUIRE_2FA = env("EQAL_REQUIRE_2FA", "1") == "1"
LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "accounts.authentication.AssignmentTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "config.errors.exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"auth": "60/min"},
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "SIGNING_KEY": SECRET_KEY,
}
REFRESH_COOKIE = "eqal_refresh"
REFRESH_COOKIE_SECURE = not DEBUG

CORS_ALLOWED_ORIGINS = env("EQAL_CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
