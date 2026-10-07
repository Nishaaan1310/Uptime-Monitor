import os
import unittest

from django.test import SimpleTestCase

from monitors.checker import check_url


@unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS"), "set RUN_LIVE_TESTS=1 to use the internet")
class LiveTests(SimpleTestCase):
    def test_http_to_https_redirect_is_up(self):
        self.assertTrue(check_url("http://github.com").is_up)

    def test_redirect_chain_within_the_limit_is_up(self):
        self.assertTrue(check_url("https://httpbin.org/redirect/3").is_up)

    def test_redirect_chain_over_the_limit_is_down(self):
        outcome = check_url("https://httpbin.org/redirect/10")
        self.assertFalse(outcome.is_up)
        self.assertIn("Too many redirects", outcome.error_message)

    def test_redirect_to_loopback_is_blocked(self):
        outcome = check_url("https://httpbin.org/redirect-to?url=http://127.0.0.1:8000/")
        self.assertIn("Blocked", outcome.error_message)

    def test_redirect_to_cloud_metadata_is_blocked(self):
        outcome = check_url("https://httpbin.org/redirect-to?url=http://169.254.169.254/")
        self.assertIn("Blocked", outcome.error_message)