from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    OTP_TTL_SECONDS=(int, 300),
    OTP_ATTEMPT_LIMIT=(int, 5),
    OTP_REQUEST_LIMIT=(int, 10),
    OTP_REQUEST_WINDOW_SECONDS=(int, 600),
    LOGIN_ATTEMPT_LIMIT=(int, 5),
    LOGIN_ATTEMPT_WINDOW_SECONDS=(int, 600),
    SESSION_COOKIE_AGE=(int, 1200),
    OTP_PRINT_TO_TERMINAL=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env("DEBUG", default=True)
SECRET_KEY = env("SECRET_KEY", default="django-insecure-kisan-asara-dev-key")
configured_allowed_hosts = env.list("ALLOWED_HOSTS", default=[])
ALLOWED_HOSTS = configured_allowed_hosts or (["*"] if DEBUG else ["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "kisan1",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "kisan1.middleware.SessionSecurityMiddleware",
    "kisan1.middleware.RequestAuditMiddleware",
    "kisan1.middleware.GlobalExceptionMiddleware",
]

ROOT_URLCONF = "farmer_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "farmer_project.wsgi.application"
ASGI_APPLICATION = "farmer_project.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "kisan1.validators.PasswordComplexityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "main_home"
LOGOUT_REDIRECT_URL = "welcome"

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", _("English")),
    ("hi", _("Hindi")),
    ("mr", _("Marathi")),
    ("ta", _("Tamil")),
    ("te", _("Telugu")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "kisan1" / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "kisan-asara-cache",
    }
}

OTP_TTL_SECONDS = env("OTP_TTL_SECONDS")
OTP_ATTEMPT_LIMIT = env("OTP_ATTEMPT_LIMIT")
OTP_REQUEST_LIMIT = env("OTP_REQUEST_LIMIT")
OTP_REQUEST_WINDOW_SECONDS = env("OTP_REQUEST_WINDOW_SECONDS")
LOGIN_ATTEMPT_LIMIT = env("LOGIN_ATTEMPT_LIMIT")
LOGIN_ATTEMPT_WINDOW_SECONDS = env("LOGIN_ATTEMPT_WINDOW_SECONDS")
OTP_PRINT_TO_TERMINAL = env("OTP_PRINT_TO_TERMINAL")

SESSION_COOKIE_AGE = env("SESSION_COOKIE_AGE")
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000 if not DEBUG else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=not DEBUG)

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", default="INFO"),
    },
}
