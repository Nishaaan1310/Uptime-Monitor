import socket
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from monitors.forms import MonitorForm
from monitors.models import Monitor
from monitors.validators import validate_public_url
from .helpers import fake_dns


class ValidatePublicUrlTests(SimpleTestCase):
    def test_non_web_schemes_are_rejected(self):
        for url in ["ftp://example.com", "file:///etc/passwd", "gopher://example.com", "javascript:alert(1)"]:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    validate_public_url(url)

    def test_url_without_a_host_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_public_url("http://")

    def test_internal_hosts_are_rejected(self):
        cases = [("http://localhost/", "127.0.0.1"), ("http://[::1]/", "::1"), ("http://10.0.0.5/", "10.0.0.5")]
        for url, address in cases:
            with self.subTest(url=url), fake_dns(address):
                with self.assertRaises(ValidationError):
                    validate_public_url(url)

    def test_public_host_is_accepted(self):
        with fake_dns("8.8.8.8"):
            validate_public_url("https://example.com")       # no error means accepted

    def test_uppercase_scheme_is_accepted(self):
        with fake_dns("8.8.8.8"):
            validate_public_url("HTTPS://example.com")

    def test_unresolvable_host_is_accepted_on_purpose(self):
        # a site that is down or not live yet can still be added; the checker marks it down
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            validate_public_url("https://not-live-yet.example")


class MonitorFormUrlTests(TestCase):
    def form(self, url):
        return MonitorForm(data={"name": "Test", "url": url, "interval_seconds": 60})

    def test_validator_is_attached_to_the_model_field(self):
        self.assertIn(validate_public_url, Monitor._meta.get_field("url").validators)

    def test_public_url_is_accepted(self):
        with fake_dns("8.8.8.8"):
            self.assertTrue(self.form("https://example.com").is_valid())

    def test_internal_url_is_rejected(self):
        with fake_dns("127.0.0.1"):
            form = self.form("http://localhost:8000/")
            self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_non_web_scheme_is_rejected(self):
        form = self.form("ftp://example.com")
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)