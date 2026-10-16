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
    # published key. (docs/adr/0048-production-security-settings.md)
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is unset or a placeholder. Set it to a long random value "
        "(e.g. python -c 'import secrets; print(secrets.token_urlsafe(64))')."
    )

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
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
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
    "apps.core.middleware.RequestSizeLimitMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "apps.accounts.mfa.MFAEnforcementMiddleware",
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
    "apps.accounts.throttle.ThrottleBackend",
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
        "apps.accounts.throttle.ThrottleBackend",
        "django_auth_ldap.backend.LDAPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]


# Failed-login throttling (docs/adr/0049-throttling-and-upload-limits.md).
# A username (existing or not) is locked after LOGIN_THROTTLE_MAX_FAILURES failures
# within the window, and a client address after LOGIN_THROTTLE_MAX_FAILURES_PER_IP.
# Behind a proxy set CLIENT_IP_HEADER (e.g. HTTP_X_FORWARDED_FOR) or every client
# shares the proxy's address; only do so if the proxy overwrites that header.
LOGIN_THROTTLE_ENABLED = env.bool("LOGIN_THROTTLE_ENABLED", default=True)
LOGIN_THROTTLE_MAX_FAILURES = env.int("LOGIN_THROTTLE_MAX_FAILURES", default=5)
LOGIN_THROTTLE_MAX_FAILURES_PER_IP = env.int("LOGIN_THROTTLE_MAX_FAILURES_PER_IP", default=30)
LOGIN_THROTTLE_WINDOW_SECONDS = env.int("LOGIN_THROTTLE_WINDOW_SECONDS", default=15 * 60)
CLIENT_IP_HEADER = env.str("CLIENT_IP_HEADER", default="")


# Two-factor authentication (docs/adr/0050-two-factor-authentication.md). Required for
# administrators and every local account; enrolment is forced at the next sign-in.
# Turn off only for local development or automated browser tests.
MFA_ENFORCE = env.bool("MFA_ENFORCE", default=True)
OTP_TOTP_ISSUER = env.str("OTP_TOTP_ISSUER", default="Aavistin")


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

# Upload and request size limits (docs/adr/0049-throttling-and-upload-limits.md).
EVIDENCE_MAX_UPLOAD_BYTES = env.int("EVIDENCE_MAX_UPLOAD_BYTES", default=25 * 1024 * 1024)
EVIDENCE_ALLOWED_EXTENSIONS = frozenset(
    ext.strip().lower().lstrip(".")
    for ext in env.list(
        "EVIDENCE_ALLOWED_EXTENSIONS",
        default=[
            "pdf",
            "txt",
            "md",
            "csv",
            "json",
            "xml",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "docx",
            "xlsx",
            "pptx",
            "odt",
            "ods",
            "odp",
            "zip",
        ],  # fmt: skip
    )
    if ext.strip()
)
# Public report verification (/verify/<id>/): can be switched off entirely.
REPORT_VERIFY_ENABLED = env.bool("REPORT_VERIFY_ENABLED", default=True)
REPORT_VERIFY_MAX_BYTES = env.int("REPORT_VERIFY_MAX_BYTES", default=20 * 1024 * 1024)
REPORT_VERIFY_RATE_LIMIT = env.int("REPORT_VERIFY_RATE_LIMIT", default=20)
REPORT_VERIFY_RATE_WINDOW_SECONDS = env.int("REPORT_VERIFY_RATE_WINDOW_SECONDS", default=600)
# Largest request body accepted at all (413 above this, before the body is read).
MAX_REQUEST_BYTES = env.int(
    "MAX_REQUEST_BYTES",
    default=max(EVIDENCE_MAX_UPLOAD_BYTES, REPORT_VERIFY_MAX_BYTES) + 1024 * 1024,
)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # non-file form data

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Hardening for a deployment served over HTTPS (docs/adr/0044-https-hardening-settings.md,
# extended by docs/adr/0048-production-security-settings.md).
# Everything defaults to off so plain-HTTP local use and CI keep working;
# `manage.py check --deploy` lists what is still off.
# HTTPS_ONLY redirects HTTP to HTTPS and marks the session and CSRF cookies secure.
HTTPS_ONLY = env.bool("HTTPS_ONLY", default=False)
SECURE_SSL_REDIRECT = HTTPS_ONLY
SESSION_COOKIE_SECURE = HTTPS_ONLY
CSRF_COOKIE_SECURE = HTTPS_ONLY
# HSTS is sticky in browsers, so it is a separate, explicit choice (seconds).
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
# Needed when the site is served from a name the proxy rewrites, e.g. https://aavistin.example.org
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# X-Forwarded-Proto is only believed when the operator says a proxy sets it. Setting
# HTTPS_ONLY implies that (the README requires the proxy to send it); otherwise a client
# that can reach the app port directly could forge the header. Set TRUST_X_FORWARDED_PROTO
# explicitly to override either way.
TRUST_X_FORWARDED_PROTO = env.bool("TRUST_X_FORWARDED_PROTO", default=HTTPS_ONLY)
if TRUST_X_FORWARDED_PROTO:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=12 * 60 * 60)
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
