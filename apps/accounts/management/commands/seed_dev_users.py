from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEV_USERS = [
    {"username": "admin", "password": "admin", "is_staff": True, "is_superuser": True},
    {"username": "aavistin", "password": "aavistin", "is_staff": False, "is_superuser": False},
]


class Command(BaseCommand):
    help = (
        "Create the default local-dev accounts (admin/admin, aavistin/aavistin). "
        "Idempotent; never run this against a non-dev database."
    )

    def handle(self, **options):
        User = get_user_model()
        for spec in DEV_USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "is_staff": spec["is_staff"],
                    "is_superuser": spec["is_superuser"],
                },
            )
            user.set_password(spec["password"])
            user.is_staff = spec["is_staff"]
            user.is_superuser = spec["is_superuser"]
            user.save()
            verb = "Created" if created else "Reset"
            self.stdout.write(self.style.SUCCESS(f"{verb} dev user '{spec['username']}'."))
