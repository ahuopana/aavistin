from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "core/home.html")
