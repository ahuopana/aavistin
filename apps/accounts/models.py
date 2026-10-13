from django.contrib.auth.models import AbstractUser
from django.db import models


class AuthSource(models.TextChoices):
    LOCAL = "local", "Local account"
    LDAP = "ldap", "LDAP"
    OIDC = "oidc", "OIDC SSO"


class User(AbstractUser):
    """Custom user model.

    ``auth_source`` records where a user's identity comes from (see
    docs/adr/0001-user-auth-source-uniqueness.md for why ``username`` stays
    globally unique rather than scoped per source).
    """

    auth_source = models.CharField(
        max_length=16,
        choices=AuthSource.choices,
        default=AuthSource.LOCAL,
    )


class Theme(models.TextChoices):
    AUTO = "auto", "Follow system"
    LIGHT = "light", "Light"
    DARK = "dark", "Dark"


class DateStyle(models.TextChoices):
    LOCALE = "locale", "Use my locale"
    ISO = "iso", "ISO 8601 (2026-10-13 14:05)"


# Locales only control how dates and times are written; the interface stays
# English (docs/adr/0034-user-profile-and-preferences.md).
LOCALE_CHOICES = [
    ("en-us", "English (US)"),
    ("en-gb", "English (UK)"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fi", "Suomi"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("nl", "Nederlands"),
    ("sv", "Svenska"),
]


class UserProfile(models.Model):
    """Per-user display preferences. Blank locale/time zone mean "instance default"."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    theme = models.CharField(max_length=8, choices=Theme.choices, default=Theme.AUTO)
    locale = models.CharField(max_length=8, choices=LOCALE_CHOICES, blank=True)
    date_style = models.CharField(
        max_length=8, choices=DateStyle.choices, default=DateStyle.LOCALE
    )
    time_zone = models.CharField(max_length=64, blank=True)
    # Storage name of the processed avatar image; empty means initials are shown.
    avatar = models.CharField(max_length=255, blank=True)
    avatar_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user}"
