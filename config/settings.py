"""
Django settings for the aavistin project.

Configuration comes from environment variables (see ``.env.example``),
read with django-environ. No secrets live in this repository.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)

_INSECURE_DEFAULT_KEY = "insecure-dev-key-change-me"
SECRET_KEY = env("DJANGO_SECRET_KEY", default=_INSECURE_DEFAULT_KEY)
if not DEBUG and (
    not SECRET_KEY or SECRET_KEY in (_INSECURE_DEFAULT_KEY, "change-me-to-a-random-value")
):
    # Fail closed: sessions and signed cookies must never be signed with a
    # published key. (docs/adr/0043-production-security-settings.md)
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is unset or a placeholder. Set it to a long random value "
        "(e.g. python -c 'import secrets; print(secrets.token_urlsafe(64))')."
    )

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Origins allowed to POST when served behind a proxy on another scheme/host,
# e.g. https://aavistin.example.org (scheme required).
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    "ninja",
    "django_tasks",
    "django_tasks_db",
    "apps.accounts",
    "apps.core",
    "apps.orgs",
    "apps.products",
    "apps.packages",
    "apps.assessments",
    "apps.risk",
    "apps.evidence",
    "apps.reports",
    "apps.userguide",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ProfileMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.navigation",
                "apps.accounts.context_processors.profile",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# PostgreSQL in development, CI and production; see docs/ARCHITECTURE.md.

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://aavistin:aavistin@localhost:5432/aavistin",
    ),
}


# Custom user model — must be set before the first migration.
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"


# Authentication backends
# https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#other-authentication-sources
#
# ModelBackend always stays enabled, for local accounts and as a
# break-glass path when LDAP is down. LDAP is off by default; set
# LDAP_ENABLED=True and the AUTH_LDAP_* variables below to turn it on.
# See docs/architecture.md, "Authentication and authorization".

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

LDAP_ENABLED = env.bool("LDAP_ENABLED", default=False)

if LDAP_ENABLED:
    import ldap
    from django_auth_ldap.config import GroupOfNamesType, LDAPSearch

    AUTH_LDAP_SERVER_URI = env("AUTH_LDAP_SERVER_URI")
    AUTH_LDAP_BIND_DN = env("AUTH_LDAP_BIND_DN", default="")
    AUTH_LDAP_BIND_PASSWORD = env("AUTH_LDAP_BIND_PASSWORD", default="")

    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        env("AUTH_LDAP_USER_SEARCH_BASE"),
        ldap.SCOPE_SUBTREE,
        env("AUTH_LDAP_USER_SEARCH_FILTER", default="(uid=%(user)s)"),
    )
    AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
        env("AUTH_LDAP_GROUP_SEARCH_BASE"),
        ldap.SCOPE_SUBTREE,
        "(objectClass=groupOfNames)",
    )
    AUTH_LDAP_GROUP_TYPE = GroupOfNamesType()

    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }

    # Group mapping to internal roles lives in apps.orgs (RoleAssignment with
    # a group scope), never as direct LDAP group name checks in code.
    AUTH_LDAP_FIND_GROUP_PERMS = True
    AUTH_LDAP_CACHE_TIMEOUT = 3600

    AUTH_LDAP_ALWAYS_UPDATE_USER = True
    AUTH_LDAP_USER_FLAGS_BY_GROUP = {}

    AUTHENTICATION_BACKENDS = [
        "django_auth_ldap.backend.LDAPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# `collectstatic` target; WhiteNoise serves it in production
# (docs/adr/0036-whitenoise-and-optional-uploads.md).
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# Uploaded evidence files (docs/architecture.md, "Evidence"). Uploads are
# opt-in: with MEDIA_ROOT unset, file evidence is disabled (links and
# reference notes still work). Files are never served from MEDIA_URL; they
# go through the authenticated evidence download view.
MEDIA_ROOT = env.str("MEDIA_ROOT", default="")
UPLOADS_ENABLED = bool(MEDIA_ROOT)

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Transport and cookie security (docs/adr/0043-production-security-settings.md).
#
# Behind a TLS-terminating reverse proxy, set TRUST_X_FORWARDED_PROTO=True so
# Django sees the request as secure. It is off by default: if the app is ever
# reachable without the proxy, a client could forge the header. Only enable
# it when the proxy overwrites X-Forwarded-Proto and gunicorn is not exposed.
if env.bool("TRUST_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Everything below is on outside DEBUG, each overridable by environment variable
# for plain-HTTP evaluation setups. Local development (DEBUG=True) stays on HTTP.
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=12 * 60 * 60)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
# HSTS is only sent on HTTPS responses. Start small; raise to a year once HTTPS
# is confirmed working, and only then consider preload.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if DEBUG else 3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


# Background jobs
# https://docs.djangoproject.com/en/5.2/topics/tasks/ (docs/adr/0007-background-job-backend.md)
#
# Postgres-backed in every environment, same as DATABASES — no separate
# broker service. Consumed by `manage.py db_worker`. Tests force the
# immediate (synchronous, in-process) backend via conftest.py.

TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.backend.DatabaseBackend",
    },
}
