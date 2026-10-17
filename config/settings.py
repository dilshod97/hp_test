"""
HP Test tizimi sozlamalari.
Barcha muhim qiymatlar muhit o'zgaruvchilaridan (.env) olinadi.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


DEBUG = env_bool("DEBUG", True)
SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-only-change-me" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY берилмаган (DEBUG=false).")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*")  # ички тармоқ учун; хоҳласангиз IP билан чекланг
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tinymce",  # faqat lokal TinyMCE fayllari uchun (internet kerak emas)
    "exam",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "exam.middleware.SafeExamBrowserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
        }
    }

AUTH_USER_MODEL = "exam.User"
LOGIN_URL = "staff_login"
LOGIN_REDIRECT_URL = "dashboard"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

LANGUAGE_CODE = "uz"
TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
IMAGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
# Номзод расмлари шунча кундан кейин автоматик ўчирилади
PHOTO_RETENTION_DAYS = int(os.environ.get("PHOTO_RETENTION_DAYS", "180"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if DEBUG:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Xodimlar sessiyasi 8 soat, nomzod sessiyasi brauzer yopilguncha
SESSION_COOKIE_AGE = 8 * 60 * 60

# ---- Safe Exam Browser ----
# REQUIRE_SEB=true bo'lsa, nomzod sahifalari faqat SEB orqali ochiladi.
# Lokal sinovda (DEBUG=true) o'chiq, aks holda brauzerda sinab bo'lmaydi.
REQUIRE_SEB = env_bool("REQUIRE_SEB", not DEBUG)  # serverda (DEBUG=false) standart holatda yoqiq
# SEB Config Tool ko'rsatadigan "Config Key" (bir nechta bo'lsa vergul bilan).
# Berilsa, har bir so'rovdagi X-SafeExamBrowser-ConfigKeyHash sarlavhasi tekshiriladi.
SEB_CONFIG_KEYS = env_list("SEB_CONFIG_KEYS")

# Blok vaqti tugagandan keyin tarmoq kechikishi uchun qo'shimcha soniyalar
ANSWER_GRACE_SECONDS = 10

# HTTPS орқали ишлаганда cookie'лар фақат шифрланган уланишда юборилади
if env_bool("HTTPS", False):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
