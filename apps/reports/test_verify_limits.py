import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ThrottleEvent
from apps.orgs.models import Organisation, ProductFamily
from apps.products.models import Configuration, Product, SoftwareRelease

from .models import Report


class VerifyLimitTests(TestCase):
    def setUp(self):
        org = Organisation.objects.create(name="Acme", slug="acme")
        family = ProductFamily.objects.create(organisation=org, name="S", slug="s")
        product = Product.objects.create(product_family=family, name="P", slug="p")
        release = SoftwareRelease.objects.create(product=product, version="1.0")
        configuration = Configuration.objects.create(name="C", software_release=release)
        self.pdf = b"%PDF-1.7 fake"
        self.report = Report.objects.create(
            report_id="AAV-TEST-0000-0001",
            configuration=configuration,
            title="T",
            generated_at=timezone.now(),
            sections=[],
            content={},
            content_sha256="0" * 64,
            pdf=self.pdf,
            pdf_sha256=hashlib.sha256(self.pdf).hexdigest(),
        )
        self.url = reverse("verify", args=[self.report.report_id])

    def post(self, data):
        return self.client.post(self.url, {"pdf": SimpleUploadedFile("r.pdf", data)})

    def test_match_and_mismatch(self):
        self.assertContains(self.post(self.pdf), "identical to the issued report")
        self.assertContains(self.post(b"other"), "does not match")

    @override_settings(REPORT_VERIFY_MAX_BYTES=10)
    def test_oversized_upload_is_refused_without_hashing(self):
        response = self.post(b"x" * 11)
        self.assertContains(response, "larger than")
        self.assertNotContains(response, "does not match")

    @override_settings(REPORT_VERIFY_ENABLED=False)
    def test_can_be_disabled(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post(self.pdf).status_code, 404)

    @override_settings(REPORT_VERIFY_RATE_LIMIT=3)
    def test_rate_limited_per_address(self):
        for _ in range(3):
            self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        other = self.client.get(self.url, REMOTE_ADDR="203.0.113.9")
        self.assertEqual(other.status_code, 200)

    @override_settings(REPORT_VERIFY_RATE_LIMIT=3)
    def test_unknown_ids_count_toward_the_limit(self):
        missing = reverse("verify", args=["AAV-NOPE-NOPE-NOPE"])
        for _ in range(3):
            self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.client.get(missing).status_code, 429)
        self.assertEqual(ThrottleEvent.objects.filter(scope="verify").count(), 3)

    @override_settings(MAX_REQUEST_BYTES=1000)
    def test_request_size_middleware_returns_413(self):
        response = self.client.post(self.url, {"pdf": SimpleUploadedFile("r.pdf", b"x" * 5000)})
        self.assertEqual(response.status_code, 413)
