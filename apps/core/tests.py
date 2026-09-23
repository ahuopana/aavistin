from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.management.commands.scheduler import SCHEDULE


class HomePageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "core/home.html")


class SchedulerCommandTests(TestCase):
    def test_once_enqueues_every_scheduled_task(self):
        # Under the immediate backend forced by conftest.py, .enqueue()
        # runs synchronously in-process rather than writing a DBTaskResult
        # row — so this only checks the command reports one "Enqueued"
        # line per scheduled task, not the (DatabaseBackend-only) storage.
        # The real DatabaseBackend + db_worker path is exercised manually
        # (see docs/adr/0007-background-job-backend.md); a TransactionTestCase
        # version of this was tried and dropped — it left the shared test
        # database missing migration-seeded rows for later tests when reused
        # across runs (pytest's --reuse-db), which isn't worth the flakiness
        # for what it additionally proves.
        out = StringIO()
        call_command("scheduler", "--once", stdout=out)
        self.assertEqual(out.getvalue().count("Enqueued"), len(SCHEDULE))
