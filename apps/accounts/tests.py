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
