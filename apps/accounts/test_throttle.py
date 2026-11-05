from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import ThrottleEvent

User = get_user_model()

GOOD = "correct-horse-battery"


@override_settings(LOGIN_THROTTLE_MAX_FAILURES=3, LOGIN_THROTTLE_MAX_FAILURES_PER_IP=50)
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="alice", password=GOOD)
        self.url = reverse("login")

    def attempt(self, username="alice", password="wrong", **extra):
        return self.client.post(self.url, {"username": username, "password": password}, **extra)

    def test_login_works_normally(self):
        response = self.attempt(password=GOOD)
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_locks_after_max_failures_even_with_correct_password(self):
        for _ in range(2):
            self.assertContains(self.attempt(), "Incorrect username or password")
        # The third failure trips the lock, and the page says so straight away.
        self.assertContains(self.attempt(), "Too many failed sign-in attempts")
        response = self.attempt(password=GOOD)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many failed sign-in attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_usernames_lock_too(self):
        for _ in range(3):
            self.attempt(username="nobody")
        self.assertContains(self.attempt(username="nobody"), "Too many failed")

    def test_username_match_ignores_case(self):
        for _ in range(3):
            self.attempt(username="ALICE")
        self.assertContains(self.attempt(password=GOOD), "Too many failed")

    def test_lock_does_not_affect_other_users(self):
        User.objects.create_user(username="bob", password=GOOD)
        for _ in range(3):
            self.attempt()
        self.assertEqual(self.attempt(username="bob", password=GOOD).status_code, 302)

    def test_refused_attempts_do_not_extend_the_lock(self):
        for _ in range(3):
            self.attempt()
        before = ThrottleEvent.objects.count()
        self.attempt()
        self.assertEqual(ThrottleEvent.objects.count(), before)

    def test_success_clears_failures(self):
        self.attempt()
        self.attempt()
        self.assertEqual(self.attempt(password=GOOD).status_code, 302)
        self.client.logout()
        self.assertFalse(ThrottleEvent.objects.filter(key="alice").exists())

    def test_admin_login_is_covered(self):
        for _ in range(3):
            self.attempt()
        self.assertFalse(
            self.client.login(username="alice", password=GOOD),
            "backend-level lock should refuse any authenticate() call",
        )

    @override_settings(LOGIN_THROTTLE_MAX_FAILURES_PER_IP=2, LOGIN_THROTTLE_MAX_FAILURES=100)
    def test_per_address_limit(self):
        self.attempt(username="a")
        self.attempt(username="b")
        self.assertContains(self.attempt(username="c", password=GOOD), "Too many failed")
        other = self.attempt(username="alice", password=GOOD, REMOTE_ADDR="203.0.113.9")
        self.assertEqual(other.status_code, 302)

    @override_settings(CLIENT_IP_HEADER="HTTP_X_FORWARDED_FOR", LOGIN_THROTTLE_MAX_FAILURES=100)
    def test_forwarded_header_is_used_when_configured(self):
        for _ in range(50):
            self.attempt(HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7")
        self.assertTrue(ThrottleEvent.objects.filter(scope="login-ip", key="203.0.113.7").exists())

    @override_settings(LOGIN_THROTTLE_ENABLED=False)
    def test_can_be_disabled(self):
        for _ in range(10):
            self.attempt()
        self.assertEqual(self.attempt(password=GOOD).status_code, 302)
        self.assertEqual(ThrottleEvent.objects.count(), 0)
