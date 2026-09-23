from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import AuthSource, User


class UserModelTests(TestCase):
    def test_default_auth_source_is_local(self):
        user = User.objects.create_user(username="alice", password="x")
        self.assertEqual(user.auth_source, AuthSource.LOCAL)

    def test_username_stays_globally_unique(self):
        User.objects.create_user(username="alice", password="x", auth_source=AuthSource.LOCAL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="alice", password="x", auth_source=AuthSource.LDAP)


class SeedDevUsersCommandTests(TestCase):
    def test_creates_admin_and_regular_user(self):
        call_command("seed_dev_users")

        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("admin"))

        user = User.objects.get(username="aavistin")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("aavistin"))

    def test_idempotent(self):
        call_command("seed_dev_users")
        call_command("seed_dev_users")

        self.assertEqual(User.objects.filter(username="admin").count(), 1)
