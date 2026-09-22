"""
Django settings for the aavistin project.

Configuration comes from environment variables (see ``.env.example``),
read with django-environ. No secrets live in this repository.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


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
    "apps.accounts",
    "apps.core",
    "apps.orgs",
    "apps.products",
    "apps.packages",
    "apps.assessments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Security: honour X-Forwarded-Proto from the reverse proxy in production.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
