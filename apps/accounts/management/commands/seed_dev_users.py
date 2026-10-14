import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

DEV_USERS = [
    {"username": "admin", "password": "admin", "is_staff": True, "is_superuser": True},
    {"username": "aavistin", "password": "aavistin", "is_staff": False, "is_superuser": False},
]


def _password_for(spec):
    """Password from SEED_<USERNAME>_PASSWORD, else the well-known default.

    The default is only allowed while DEBUG is on; a non-debug deployment
    must supply its own password for every seeded account.
    """
    env_name = f"SEED_{spec['username'].upper()}_PASSWORD"
    password = os.environ.get(env_name)
    if password:
        return password
    if not settings.DEBUG:
        raise CommandError(
            f"Refusing to seed '{spec['username']}' with the default password while "
            f"DEBUG is off. Set {env_name} to a strong password."
        )
    return spec["password"]


class Command(BaseCommand):
    help = (
        "Create the default local-dev accounts (admin/admin, aavistin/aavistin). "
        "Idempotent. With DEBUG off, the default passwords are refused: set "
        "SEED_ADMIN_PASSWORD and SEED_AAVISTIN_PASSWORD instead."
    )

    def handle(self, **options):
        # Resolve every password first so a refusal leaves no account half-seeded.
        passwords = {spec["username"]: _password_for(spec) for spec in DEV_USERS}
        User = get_user_model()
        for spec in DEV_USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "is_staff": spec["is_staff"],
                    "is_superuser": spec["is_superuser"],
                },
            )
            user.set_password(passwords[spec["username"]])
            user.is_staff = spec["is_staff"]
            user.is_superuser = spec["is_superuser"]
            user.save()
            verb = "Created" if created else "Reset"
            self.stdout.write(self.style.SUCCESS(f"{verb} dev user '{spec['username']}'."))
