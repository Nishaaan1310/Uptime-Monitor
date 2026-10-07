import importlib
import socket
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase
from urllib3.util import connection as urllib3_connection

from monitors import checker, netguard
from monitors.checker import check_url
from monitors.netguard import BlockedAddressError, install_guard
from .helpers import fake_dns


def fake_response(status_code):
    return SimpleNamespace(status_code=status_code)


def patched_get(**kwargs):
    return patch("requests.Session.get", autospec=True, **kwargs)


class CheckUrlResultTests(SimpleTestCase):
    """How outcomes are reported."""

    def test_up_or_down_depends_on_the_final_status(self):
        cases = {200: True, 301: True, 399: True, 400: False, 404: False, 500: False, 503: False}
        for status, expected in cases.items():
            with self.subTest(status=status):
                with patched_get(return_value=fake_response(status)):
                    outcome = check_url("https://example.com")
                self.assertIs(outcome.is_up, expected)
                self.assertEqual(outcome.status_code, status)
                self.assertIsInstance(outcome.response_time_ms, int)
                self.assertEqual(outcome.error_message, "")

    def check_with_error(self, error, **kwargs):
        with patched_get(side_effect=error):
            return check_url("https://example.com", **kwargs)

    def test_timeout(self):
        outcome = self.check_with_error(requests.exceptions.Timeout(), timeout=3)
        self.assertFalse(outcome.is_up)
        self.assertIn("Timed out after 3s", outcome.error_message)
        self.assertIsNone(outcome.status_code)
        self.assertIsNone(outcome.response_time_ms)

    def test_too_many_redirects(self):
        outcome = self.check_with_error(requests.exceptions.TooManyRedirects())
        self.assertFalse(outcome.is_up)
        self.assertIn("Too many redirects", outcome.error_message)

    def test_other_request_errors_are_service_errors(self):
        outcome = self.check_with_error(requests.exceptions.ConnectionError("boom"))
        self.assertFalse(outcome.is_up)
        self.assertEqual(outcome.error_message, "Service error: boom")

    def test_blocked_address_is_reported_without_leaking_it(self):
        outcome = self.check_with_error(BlockedAddressError("10.0.0.5"))
        self.assertFalse(outcome.is_up)
        self.assertIn("Blocked", outcome.error_message)
        self.assertNotIn("10.0.0.5", outcome.error_message)


class CheckUrlSessionTests(SimpleTestCase):
    """How the request is made."""

    def test_session_ignores_proxies_and_caps_redirects(self):
        with patched_get(return_value=fake_response(200)) as mock_get:
            check_url("https://example.com")
        session = mock_get.call_args.args[0]
        self.assertFalse(session.trust_env)
        self.assertEqual(session.max_redirects, 5)

    def test_url_and_timeout_are_passed_on_and_redirects_stay_on(self):
        with patched_get(return_value=fake_response(200)) as mock_get:
            check_url("https://example.com", timeout=3)
        self.assertEqual(mock_get.call_args.args[1], "https://example.com")
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 3)
        self.assertTrue(mock_get.call_args.kwargs.get("allow_redirects", True))


class CheckUrlEndToEndTests(SimpleTestCase):
    """Real requests, real guard, no network: these are refused before dialing."""

    def test_literal_loopback_address_is_blocked(self):
        outcome = check_url("http://127.0.0.1:8000/")
        self.assertFalse(outcome.is_up)
        self.assertIn("Blocked", outcome.error_message)

    def test_name_that_resolves_to_an_internal_address_is_blocked(self):
        with fake_dns("10.0.0.5"):
            outcome = check_url("http://example.com/")
        self.assertFalse(outcome.is_up)
        self.assertIn("Blocked", outcome.error_message)

    def test_ipv6_loopback_is_blocked(self):
        with fake_dns("::1"):
            outcome = check_url("http://[::1]/")
        self.assertFalse(outcome.is_up)
        self.assertIn("Blocked", outcome.error_message)

    def test_unresolvable_name_is_a_service_error_not_blocked(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            outcome = check_url("https://nonexistent-site-12345.invalid")
        self.assertFalse(outcome.is_up)
        self.assertTrue(outcome.error_message.startswith("Service error"))


class GuardIsInstalledTests(SimpleTestCase):
    def test_importing_the_checker_installs_the_guard(self):
        self.addCleanup(install_guard)                 # make sure the guard is back afterwards
        urllib3_connection.create_connection = netguard._original_create_connection   # remove it
        importlib.reload(checker)                      # run checker.py's top-level code again
        self.assertIs(urllib3_connection.create_connection, netguard.guarded_create_connection)