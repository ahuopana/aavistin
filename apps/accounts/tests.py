from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.accounts.models import AuthSource, User


class UserModelTests(TestCase):
    def test_default_auth_source_is_local(self):
        user = User.objects.create_user(username="alice", password="x")
        self.assertEqual(user.auth_source, AuthSource.LOCAL)

    def test_username_stays_globally_unique(self):
        User.objects.create_user(username="alice", password="x", auth_source=AuthSource.LOCAL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="alice", password="x", auth_source=AuthSource.LDAP)


@override_settings(DEBUG=True)
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


@override_settings(DEBUG=False)
class SeedDevUsersWithoutDebugTests(TestCase):
    def test_refuses_default_passwords(self):
        with self.assertRaises(CommandError):
            call_command("seed_dev_users")
        self.assertFalse(User.objects.filter(username__in=["admin", "aavistin"]).exists())

    def test_refuses_if_only_one_password_supplied(self):
        with patch.dict("os.environ", {"SEED_ADMIN_PASSWORD": "s3cret-admin"}):
            with self.assertRaises(CommandError):
                call_command("seed_dev_users")
        self.assertFalse(User.objects.filter(username="admin").exists())

    def test_seeds_with_supplied_passwords(self):
        env = {"SEED_ADMIN_PASSWORD": "s3cret-admin", "SEED_AAVISTIN_PASSWORD": "s3cret-user"}
        with patch.dict("os.environ", env):
            call_command("seed_dev_users")
        self.assertTrue(User.objects.get(username="admin").check_password("s3cret-admin"))
        self.assertTrue(User.objects.get(username="aavistin").check_password("s3cret-user"))
