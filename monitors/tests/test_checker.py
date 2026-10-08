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


class FakeResponse:
    def __init__(self, status_code, location=None):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        self.closed = False

    @property
    def content(self):
        raise AssertionError("the body must never be read")

    @property
    def text(self):
        raise AssertionError("the body must never be read")

    def close(self):
        self.closed = True


def patched_get(**kwargs):
    return patch("requests.Session.get", autospec=True, **kwargs)


class CheckUrlResultTests(SimpleTestCase):
    """How outcomes are reported."""

    def test_up_or_down_depends_on_the_final_status(self):
        cases = {200: True, 399: True, 400: False, 404: False, 500: False, 503: False}
        for status, expected in cases.items():
            with self.subTest(status=status):
                with patched_get(return_value=FakeResponse(status)):
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

    def test_session_ignores_proxies(self):
        with patched_get(return_value=FakeResponse(200)) as mock_get:
            check_url("https://example.com")
        session = mock_get.call_args.args[0]
        self.assertFalse(session.trust_env)

    def test_the_url_is_passed_on(self):
        with patched_get(return_value=FakeResponse(200)) as mock_get:
            check_url("https://example.com/page")
        self.assertEqual(mock_get.call_args.args[1], "https://example.com/page")


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

class RedirectTests(SimpleTestCase):
    def check(self, responses, url="https://example.com/start"):
        with patched_get(side_effect=responses) as mock_get:
            outcome = check_url(url)
        return outcome, mock_get

    def test_follows_a_redirect_to_the_final_answer(self):
        outcome, mock_get = self.check([FakeResponse(301, "https://example.com/final"), FakeResponse(200)])
        self.assertTrue(outcome.is_up)
        self.assertEqual(outcome.status_code, 200)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_get.call_args_list[1].args[1], "https://example.com/final")

    def test_relative_location_is_resolved_against_the_current_url(self):
        _, mock_get = self.check([FakeResponse(302, "/login"), FakeResponse(200)])
        self.assertEqual(mock_get.call_args_list[1].args[1], "https://example.com/login")

    def test_the_final_status_decides_up_or_down(self):
        outcome, _ = self.check([FakeResponse(301, "https://example.com/broken"), FakeResponse(500)])
        self.assertFalse(outcome.is_up)
        self.assertEqual(outcome.status_code, 500)

    def test_five_redirects_are_allowed(self):
        responses = [FakeResponse(302, f"https://example.com/{i}") for i in range(5)] + [FakeResponse(200)]
        outcome, mock_get = self.check(responses)
        self.assertTrue(outcome.is_up)
        self.assertEqual(mock_get.call_count, 6)

    def test_a_sixth_redirect_is_too_many(self):
        responses = [FakeResponse(302, f"https://example.com/{i}") for i in range(6)]
        outcome, mock_get = self.check(responses)
        self.assertFalse(outcome.is_up)
        self.assertIn("Too many redirects", outcome.error_message)
        self.assertEqual(mock_get.call_count, 6)

    def test_redirect_to_an_unsupported_scheme_is_refused(self):
        outcome, mock_get = self.check([FakeResponse(302, "ftp://example.com/file")])
        self.assertFalse(outcome.is_up)
        self.assertIn("unsupported", outcome.error_message)
        self.assertEqual(mock_get.call_count, 1)

    def test_a_blocked_second_hop_is_reported_as_blocked(self):
        outcome, _ = self.check([FakeResponse(302, "http://internal.example/"), BlockedAddressError("10.0.0.5")])
        self.assertFalse(outcome.is_up)
        self.assertIn("Blocked", outcome.error_message)

    def test_every_redirect_status_is_followed(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                outcome, mock_get = self.check(
                    [FakeResponse(status, "https://example.com/next"), FakeResponse(200)]
                )
                self.assertEqual(mock_get.call_count, 2)


class ResourceLimitTests(SimpleTestCase):
    def test_the_body_is_never_read_and_every_response_is_closed(self):
        redirect = FakeResponse(302, "https://example.com/next")
        final = FakeResponse(200)
        with patched_get(side_effect=[redirect, final]):
            check_url("https://example.com")
        self.assertTrue(redirect.closed)
        self.assertTrue(final.closed)

    def test_requests_stream_and_do_not_follow_redirects_themselves(self):
        with patched_get(return_value=FakeResponse(200)) as mock_get:
            check_url("https://example.com")
        self.assertTrue(mock_get.call_args.kwargs["stream"])
        self.assertFalse(mock_get.call_args.kwargs["allow_redirects"])

    def test_timeouts_come_from_the_remaining_budget(self):
        with patched_get(return_value=FakeResponse(200)) as mock_get:
            check_url("https://example.com", timeout=10)
        connect, read = mock_get.call_args.kwargs["timeout"]
        self.assertLessEqual(connect, 5)
        self.assertLessEqual(read, 10)

    def test_a_spent_budget_reports_a_timeout_without_making_a_request(self):
        with patch("monitors.checker.time") as fake_time, patched_get() as mock_get:
            fake_time.monotonic.side_effect = [0, 100]     # the stopwatch jumps past the deadline
            outcome = check_url("https://example.com", timeout=10)
        self.assertIn("Timed out", outcome.error_message)
        mock_get.assert_not_called()

    def test_long_error_text_is_cut(self):
        with patched_get(side_effect=requests.exceptions.ConnectionError("x" * 5000)):
            outcome = check_url("https://example.com")
        self.assertLessEqual(len(outcome.error_message), 303)
        self.assertTrue(outcome.error_message.endswith("..."))


def test_both_families_are_tried_within_the_cap(self):
    def dial(address, *args, **kwargs):
        if ":" in address[0]:
            raise OSError("no ipv6 here")
        return "connected"

    self.dial.side_effect = dial
    six_ipv6_then_one_ipv4 = [
        "2606:4700:4700::1111", "2606:4700:4700::1001",
        "2001:4860:4860::8888", "2001:4860:4860::8844",
        "2620:fe::fe", "2620:fe::9",
        "1.1.1.1",
    ]
    with fake_dns(*six_ipv6_then_one_ipv4):
        self.assertEqual(guarded_create_connection(("example.com", 443)), "connected")

