from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import AuthSource

User = get_user_model()
PASSWORD = "correct-horse-battery"


def code(device, drift=0):
    return f"{totp(device.bin_key, device.step, device.t0, device.digits, drift):06d}"


class MFATests(TestCase):
    def setUp(self):
        # Entered here, not as a class decorator: conftest turns enforcement off per test.
        self.enterContext(override_settings(MFA_ENFORCE=True))
        self.user = User.objects.create_user(username="alice", password=PASSWORD)
        self.home = reverse("orgs:portfolio")

    def sign_in(self, username="alice"):
        return self.client.post(reverse("login"), {"username": username, "password": PASSWORD})

    def enrol(self):
        """Walk a signed-in user through enrolment; returns (device, recovery codes)."""
        self.sign_in()
        self.client.get(reverse("accounts:mfa_setup"))
        device = TOTPDevice.objects.get(user=self.user, confirmed=False)
        response = self.client.post(reverse("accounts:mfa_setup"), {"token": code(device)})
        device.refresh_from_db()
        return device, response.context["codes"]

    def test_unenrolled_local_user_is_sent_to_setup_everywhere(self):
        self.sign_in()
        for url in (self.home, reverse("accounts:profile"), "/admin/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("accounts:mfa_setup")))

    def test_enrolment_confirms_device_logs_in_and_issues_recovery_codes(self):
        device, codes = self.enrol()
        self.assertTrue(device.confirmed)
        self.assertEqual(len(codes), 10)
        self.assertEqual(self.client.get(self.home).status_code, 200)

    def test_wrong_code_does_not_confirm(self):
        self.sign_in()
        self.client.get(reverse("accounts:mfa_setup"))
        response = self.client.post(reverse("accounts:mfa_setup"), {"token": "000000"})
        self.assertContains(response, "not valid")
        self.assertFalse(TOTPDevice.objects.get(user=self.user).confirmed)
        self.assertEqual(self.client.get(self.home).status_code, 302)

    def test_new_session_must_verify(self):
        device, _ = self.enrol()
        self.client.logout()
        self.sign_in()
        response = self.client.get(self.home)
        self.assertTrue(response["Location"].startswith(reverse("accounts:mfa_verify")))
        ok = self.client.post(reverse("accounts:mfa_verify"), {"token": code(device, drift=1)})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(self.client.get(self.home).status_code, 200)

    def test_verify_rejects_bad_code(self):
        self.enrol()
        self.client.logout()
        self.sign_in()
        response = self.client.post(reverse("accounts:mfa_verify"), {"token": "123456"})
        self.assertContains(response, "not valid")
        self.assertEqual(self.client.get(self.home).status_code, 302)

    def test_recovery_code_works_once(self):
        _, codes = self.enrol()
        self.client.logout()
        self.sign_in()
        self.client.post(reverse("accounts:mfa_verify"), {"token": codes[0]})
        self.assertEqual(self.client.get(self.home).status_code, 200)
        self.client.logout()
        self.sign_in()
        self.client.post(reverse("accounts:mfa_verify"), {"token": codes[0]})
        self.assertEqual(self.client.get(self.home).status_code, 302)

    def test_password_alone_cannot_add_a_device_to_an_enrolled_account(self):
        self.enrol()
        self.client.logout()
        self.sign_in()
        response = self.client.get(reverse("accounts:mfa_setup"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:mfa_verify"))
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)

    @override_settings(LOGIN_THROTTLE_MAX_FAILURES=3)
    def test_second_factor_guessing_locks(self):
        device, _ = self.enrol()
        self.client.logout()
        self.sign_in()
        for _ in range(3):
            self.client.post(reverse("accounts:mfa_verify"), {"token": "000000"})
        response = self.client.post(reverse("accounts:mfa_verify"), {"token": code(device, 1)})
        self.assertContains(response, "Too many attempts")
        self.assertEqual(self.client.get(self.home).status_code, 302)

    def test_ldap_user_is_not_required_but_ldap_admin_is(self):
        User.objects.create_user(
            username="ldapper", password=PASSWORD, auth_source=AuthSource.LDAP
        )
        self.sign_in("ldapper")
        self.assertEqual(self.client.get(self.home).status_code, 200)
        self.client.logout()
        User.objects.create_user(
            username="ldapadmin", password=PASSWORD, auth_source=AuthSource.LDAP, is_staff=True
        )
        self.sign_in("ldapadmin")
        self.assertEqual(self.client.get(self.home).status_code, 302)

    def test_superuser_is_required(self):
        User.objects.create_superuser(username="root", password=PASSWORD)
        self.sign_in("root")
        response = self.client.get("/admin/")
        self.assertTrue(response["Location"].startswith(reverse("accounts:mfa_setup")))

    def test_next_is_preserved_and_open_redirects_refused(self):
        device, _ = self.enrol()
        self.client.logout()
        self.sign_in()
        url = reverse("accounts:mfa_verify")
        response = self.client.post(
            url, {"token": code(device, 1), "next": "https://evil.example/"}
        )
        self.assertEqual(response["Location"], "/")

    def test_htmx_requests_get_hx_redirect(self):
        self.sign_in()
        response = self.client.get(self.home, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.assertIn("mfa/setup", response["HX-Redirect"])

    def test_regenerate_recovery_codes_invalidates_old_ones(self):
        _, old = self.enrol()
        response = self.client.post(reverse("accounts:mfa_recovery_codes"))
        new = response.context["codes"]
        self.assertEqual(len(new), 10)
        self.assertFalse(set(old) & set(new))
        self.assertEqual(StaticDevice.objects.filter(user=self.user).count(), 1)

    def test_reset_command_forces_re_enrolment(self):
        self.enrol()
        call_command("reset_mfa", "alice")
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.client.logout()
        self.sign_in()
        self.assertTrue(
            self.client.get(self.home)["Location"].startswith(reverse("accounts:mfa_setup"))
        )

    def test_setup_page_shows_qr_and_authenticator_hint(self):
        self.sign_in()
        response = self.client.get(reverse("accounts:mfa_setup"))
        self.assertContains(response, "<svg")
        self.assertContains(response, "Microsoft Authenticator")
        device = TOTPDevice.objects.get(user=self.user)
        self.assertContains(response, device.bin_key and "Can't scan")

    @override_settings(MFA_ENFORCE=False)
    def test_can_be_disabled(self):
        self.sign_in()
        self.assertEqual(self.client.get(self.home).status_code, 200)
