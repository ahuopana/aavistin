from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment

DEV_GROUP_ROLES = [
    (Role.VIEWER, "Viewer"),
    (Role.EDITOR, "Editor"),
    (Role.APPROVER, "Approver"),
    (Role.CONTENT_CURATOR, "Content curator"),
    (Role.ORG_ADMIN, "Organisation admin"),
]

# The seeded dev user (apps.accounts.management.commands.seed_dev_users)
# holds both roles here, so one login can exercise the whole
# add -> approve -> delete flow without switching accounts.
DEV_USER_GROUP_ROLES = [Role.EDITOR, Role.APPROVER]


class Command(BaseCommand):
    help = (
        "Create default Role groups, a default organisation/product family, and grant "
        "the seeded 'aavistin' dev user editor+approver there. Local development only."
    )

    def handle(self, **options):
        groups = {}
        for role, label in DEV_GROUP_ROLES:
            group, created = Group.objects.get_or_create(name=label)
            groups[role] = group
            verb = "Created" if created else "Found"
            self.stdout.write(f"{verb} group '{label}'.")

        organisation, created = Organisation.objects.get_or_create(
            slug="default", defaults={"name": "Default Organisation"}
        )
        self.stdout.write(
            f"{'Created' if created else 'Found'} organisation '{organisation.name}'."
        )

        family, created = ProductFamily.objects.get_or_create(
            organisation=organisation, slug="default", defaults={"name": "Default Family"}
        )
        self.stdout.write(f"{'Created' if created else 'Found'} product family '{family.name}'.")

        for role in DEV_USER_GROUP_ROLES:
            _, created = RoleAssignment.objects.get_or_create(
                group=groups[role], role=role, organisation=organisation
            )
            verb = "Granted" if created else "Already had"
            self.stdout.write(f"{verb} '{groups[role].name}' group role={role} on {organisation}.")

        User = get_user_model()
        try:
            dev_user = User.objects.get(username="aavistin")
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    "No 'aavistin' user found (run seed_dev_users first) — "
                    "groups and role assignments were still created."
                )
            )
            return

        for role in DEV_USER_GROUP_ROLES:
            dev_user.groups.add(groups[role])
        self.stdout.write(
            self.style.SUCCESS(
                f"Added 'aavistin' to {', '.join(groups[r].name for r in DEV_USER_GROUP_ROLES)}."
            )
        )
