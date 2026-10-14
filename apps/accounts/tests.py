import io
import zoneinfo
from datetime import UTC, date, datetime
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts import avatars, prefs
from apps.accounts.models import AuthSource, DateStyle, Theme, User
from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment
from apps.products.models import Product


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


# --- Profile and preferences (docs/adr/0037-user-profile-and-preferences.md) ---


def _png(size=(40, 60), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, format=fmt)
    return buf.getvalue()


class PrefsFormattingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.profile = prefs.get_profile(self.user)
        self.moment = datetime(2026, 10, 13, 22, 30, tzinfo=UTC)

    def test_profile_created_lazily_and_reused(self):
        self.assertEqual(self.profile.theme, Theme.AUTO)
        self.assertEqual(prefs.get_profile(User.objects.get(pk=self.user.pk)).pk, self.profile.pk)

    def test_anonymous_has_no_profile(self):
        self.assertIsNone(prefs.get_profile(AnonymousUser()))

    def test_iso_style_uses_time_zone(self):
        self.profile.date_style = DateStyle.ISO
        self.profile.time_zone = "Europe/Helsinki"
        self.assertEqual(prefs.format_datetime(self.moment, self.profile), "2026-10-14 01:30")
        self.assertEqual(prefs.format_date(date(2026, 10, 13), self.profile), "2026-10-13")

    def test_locale_changes_date_order(self):
        self.profile.locale = "en-us"
        us = prefs.format_date(date(2026, 10, 13), self.profile)
        self.profile.locale = "fi"
        fi = prefs.format_date(date(2026, 10, 13), self.profile)
        self.assertEqual(us, "10/13/2026")
        self.assertEqual(fi, "13.10.2026")

    def test_blank_preferences_fall_back_to_instance_defaults(self):
        self.assertEqual(prefs.effective_time_zone(self.profile), zoneinfo.ZoneInfo("UTC"))
        self.assertEqual(prefs.effective_locale(self.profile), "en-us")

    def test_invalid_stored_time_zone_falls_back(self):
        self.profile.time_zone = "Mars/Olympus"
        self.assertEqual(prefs.effective_time_zone(self.profile), zoneinfo.ZoneInfo("UTC"))


class ProfileViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="x", first_name="Alice", last_name="Aalto"
        )
        self.client.force_login(self.user)

    def _post(self, **overrides):
        data = {
            "first_name": "Alice",
            "last_name": "Aalto",
            "email": "alice@example.org",
            "theme": "dark",
            "locale": "fi",
            "date_style": "iso",
            "time_zone": "Europe/Helsinki",
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:profile"), data)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)

    def test_saves_preferences_and_renders_theme_server_side(self):
        response = self._post()
        self.assertRedirects(response, reverse("accounts:profile"))
        profile = prefs.get_profile(User.objects.get(pk=self.user.pk))
        self.assertEqual(
            (profile.theme, profile.locale, profile.date_style, profile.time_zone),
            ("dark", "fi", "iso", "Europe/Helsinki"),
        )
        page = self.client.get(reverse("core:home"))
        self.assertContains(page, '<html lang="en" data-theme="dark">')

    def test_rejects_unknown_time_zone(self):
        response = self._post(time_zone="Mars/Olympus")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")

    def test_ldap_users_cannot_edit_identity(self):
        User.objects.filter(pk=self.user.pk).update(auth_source=AuthSource.LDAP)
        self._post(first_name="Mallory", email="m@example.org")
        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(user.first_name, "Alice")
        self.assertEqual(user.email, "")
        self.assertEqual(user.profile.theme, "dark")

    def test_theme_toggle_endpoint(self):
        response = self.client.post(reverse("accounts:theme"), {"theme": "light"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(prefs.get_profile(User.objects.get(pk=self.user.pk)).theme, "light")
        bad = self.client.post(reverse("accounts:theme"), {"theme": "neon"})
        self.assertEqual(bad.status_code, 400)

    def test_time_zone_and_style_apply_to_rendered_dates(self):
        self._post()
        stamp = datetime(2026, 10, 13, 22, 30, tzinfo=UTC)
        with patch("apps.accounts.views.timezone.now", return_value=stamp):
            page = self.client.get(reverse("accounts:profile"))
        self.assertContains(page, "<strong>2026-10-14 01:30</strong> (Europe/Helsinki)")


class AvatarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.client.force_login(self.user)

    def _upload(self, content, name="me.png", **extra):
        data = {
            "theme": "auto",
            "date_style": "locale",
            "first_name": "",
            "last_name": "",
            "email": "",
            "avatar": SimpleUploadedFile(name, content, content_type="image/png"),
        }
        data.update(extra)
        return self.client.post(reverse("accounts:profile"), data)

    def test_upload_is_reencoded_square_png_and_served_to_logged_in_users(self):
        self.assertRedirects(self._upload(_png(fmt="JPEG"), "me.jpg"), reverse("accounts:profile"))
        response = self.client.get(reverse("accounts:avatar", args=[self.user.pk]))
        self.assertEqual(response["Content-Type"], "image/png")
        image = Image.open(io.BytesIO(b"".join(response.streaming_content)))
        self.assertEqual(image.size, (avatars.AVATAR_SIZE, avatars.AVATAR_SIZE))
        self.assertFalse(image.getexif())
        self.client.logout()
        anon = self.client.get(reverse("accounts:avatar", args=[self.user.pk]))
        self.assertEqual(anon.status_code, 302)

    def test_rejects_non_images(self):
        response = self._upload(b"<script>alert(1)</script>", "x.png")
        self.assertContains(response, "not a readable image")
        self.assertEqual(
            self.client.get(reverse("accounts:avatar", args=[self.user.pk])).status_code, 404
        )

    def test_rejects_large_files(self):
        response = self._upload(b"0" * (avatars.MAX_UPLOAD_BYTES + 1))
        self.assertContains(response, "larger than 2 MB")

    def test_remove_returns_to_initials(self):
        self._upload(_png())
        self.client.post(
            reverse("accounts:profile"),
            {"theme": "auto", "date_style": "locale", "remove_avatar": "on"},
        )
        self.assertEqual(
            self.client.get(reverse("accounts:avatar", args=[self.user.pk])).status_code, 404
        )

    def test_disabled_when_media_root_unset(self):
        with override_settings(UPLOADS_ENABLED=False):
            page = self.client.get(reverse("accounts:profile"))
            self.assertContains(page, "Avatar uploads are not enabled")
            self.assertNotContains(page, 'type="file"')
            self.assertEqual(
                self.client.get(reverse("accounts:avatar", args=[self.user.pk])).status_code, 404
            )
            self.assertContains(self.client.get(reverse("core:home")), "avatar-initials")

    def test_initials(self):
        self.assertEqual(
            avatars.initials(User(username="x", first_name="Anna", last_name="Berg")), "AB"
        )
        self.assertEqual(avatars.initials(User(username="jane.doe")), "JD")
        self.assertEqual(avatars.initials(User(username="aavistin")), "A")


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="old-Passw0rd-x")
        self.client.force_login(self.user)

    def test_local_user_can_change_password(self):
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "old-Passw0rd-x",
                "new_password1": "new-Passw0rd-y9",
                "new_password2": "new-Passw0rd-y9",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-Passw0rd-y9"))
        # The session survives the change.
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_wrong_old_password_is_rejected(self):
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "nope",
                "new_password1": "new-Passw0rd-y9",
                "new_password2": "new-Passw0rd-y9",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-Passw0rd-x"))

    def test_directory_users_are_sent_back_to_profile(self):
        User.objects.filter(pk=self.user.pk).update(auth_source=AuthSource.LDAP)
        response = self.client.get(reverse("accounts:password_change"))
        self.assertRedirects(response, reverse("accounts:profile"))
        page = self.client.get(reverse("accounts:profile"))
        self.assertContains(page, "Your password is managed by LDAP")
        self.assertNotContains(page, "Change password")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:password_change")).status_code, 302)


class RolesOverviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.client.force_login(self.user)
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.product = Product.objects.create(
            product_family=self.family, name="TempSense", slug="tempsense"
        )

    def test_no_roles(self):
        self.assertContains(self.client.get(reverse("accounts:profile")), "You have no roles yet")

    def test_lists_direct_and_group_grants_with_scope_links(self):
        group = Group.objects.create(name="Approvers EU")
        self.user.groups.add(group)
        RoleAssignment.objects.create(role=Role.EDITOR, user=self.user, product=self.product)
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.user, organisation=self.org)
        RoleAssignment.objects.create(role=Role.APPROVER, group=group, product_family=self.family)
        other = User.objects.create_user(username="bob", password="x")
        RoleAssignment.objects.create(role=Role.ORG_ADMIN, user=other, organisation=self.org)

        page = self.client.get(reverse("accounts:profile"))
        body = page.content.decode()

        # Broadest scope first; a group grant says which group.
        self.assertLess(body.index("Organisation: "), body.index("Product family: "))
        self.assertLess(body.index("Product family: "), body.index("Product: "))
        self.assertContains(page, "Group Approvers EU")
        self.assertContains(page, reverse("orgs:detail", args=["acme"]))
        self.assertContains(page, reverse("products:product_detail", args=[self.product.pk]))
        self.assertNotContains(page, "Organisation admin")

    def test_superuser_note(self):
        User.objects.filter(pk=self.user.pk).update(is_superuser=True)
        self.assertContains(self.client.get(reverse("accounts:profile")), "You are a superuser")
