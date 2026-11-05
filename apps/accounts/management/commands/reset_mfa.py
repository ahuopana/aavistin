from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp import devices_for_user


class Command(BaseCommand):
    help = (
        "Remove a user's two-factor devices and recovery codes, so they enrol again at "
        "their next sign-in. For lost phones; verify the person's identity first."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {username!r}.") from exc
        removed = 0
        for device in devices_for_user(user, confirmed=None):
            device.delete()
            removed += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {removed} device(s) for {username}; they enrol again at next sign-in."
            )
        )
