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
