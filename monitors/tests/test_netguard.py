import socket
from unittest.mock import patch

import requests
from django.test import SimpleTestCase
from urllib3.util import connection as urllib3_connection

from monitors.netguard import (
    BlockedAddressError,
    guarded_create_connection,
    install_guard,
    is_public_host,
    resolve_public_ips,
)
from .helpers import fake_addrinfo, fake_dns


class ResolvePublicIpsTests(SimpleTestCase):
    """The rule: which addresses are allowed."""

    def test_public_address_is_returned(self):
        with fake_dns("8.8.8.8"):
            self.assertEqual(resolve_public_ips("example.com", 443), ["8.8.8.8"])

    def test_every_public_address_is_returned(self):
        with fake_dns("8.8.8.8", "1.1.1.1"):
            self.assertEqual(resolve_public_ips("example.com"), ["8.8.8.8", "1.1.1.1"])

    def test_internal_addresses_are_blocked(self):
        internal = [
            "127.0.0.1",          # loopback
            "10.0.0.5",           # private
            "172.16.0.1",         # private
            "192.168.1.10",       # private
            "169.254.169.254",    # link-local (cloud metadata)
            "100.64.0.1",         # carrier-grade NAT range
            "0.0.0.0",            # unspecified
            "::1",                # IPv6 loopback
            "fe80::1",            # IPv6 link-local
            "fc00::1",            # IPv6 private
            "::ffff:127.0.0.1",   # IPv4 loopback in disguise
            "::ffff:10.0.0.5",    # IPv4 private in disguise
        ]
        for address in internal:
            with self.subTest(address=address):
                with fake_dns(address):
                    with self.assertRaises(BlockedAddressError):
                        resolve_public_ips("example.com")

    def test_one_bad_address_blocks_the_whole_name(self):
        with fake_dns("8.8.8.8", "10.0.0.5"):
            with self.assertRaises(BlockedAddressError):
                resolve_public_ips("example.com")

    def test_unresolvable_name_raises_gaierror(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            with self.assertRaises(socket.gaierror):
                resolve_public_ips("nonexistent.invalid")

    def test_asks_for_tcp_addresses_only(self):
        # protects against each address being listed (and dialed) once per socket type
        with fake_dns("8.8.8.8") as lookup:
            resolve_public_ips("example.com", 443)
        lookup.assert_called_once_with("example.com", 443, type=socket.SOCK_STREAM)


class IsPublicHostTests(SimpleTestCase):
    """The three-way answer the form relies on."""

    def test_true_for_a_public_name(self):
        with fake_dns("8.8.8.8"):
            self.assertIs(is_public_host("example.com"), True)

    def test_false_for_an_internal_name(self):
        with fake_dns("127.0.0.1"):
            self.assertIs(is_public_host("localhost"), False)

    def test_none_for_an_unresolvable_name(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            self.assertIsNone(is_public_host("nonexistent.invalid"))


class GuardedConnectionTests(SimpleTestCase):
    """The guard: it only dials approved numbers."""

    def setUp(self):
        patcher = patch("monitors.netguard._original_create_connection")
        self.dial = patcher.start()          # the real dialer is replaced by a fake
        self.addCleanup(patcher.stop)        # and put back after each test

    def test_dials_the_validated_ip_not_the_name(self):
        with fake_dns("8.8.8.8"):
            guarded_create_connection(("example.com", 443))
        self.dial.assert_called_once_with(("8.8.8.8", 443))

    def test_passes_extra_arguments_through(self):
        with fake_dns("8.8.8.8"):
            guarded_create_connection(("example.com", 443), 5, source_address=None)
        self.dial.assert_called_once_with(("8.8.8.8", 443), 5, source_address=None)

    def test_internal_address_is_refused_and_nothing_is_dialed(self):
        with fake_dns("127.0.0.1"):
            with self.assertRaises(BlockedAddressError):
                guarded_create_connection(("example.com", 80))
        self.dial.assert_not_called()

    def test_looks_the_name_up_only_once(self):
        # a second lookup would answer with a private address (DNS rebinding)
        answers = [fake_addrinfo("8.8.8.8"), fake_addrinfo("127.0.0.1")]
        with patch("socket.getaddrinfo", side_effect=answers) as lookup:
            guarded_create_connection(("evil.example", 443))
        self.assertEqual(lookup.call_count, 1)
        self.dial.assert_called_once_with(("8.8.8.8", 443))

    def test_tries_the_next_address_when_one_fails(self):
        self.dial.side_effect = [OSError("unreachable"), "connected"]
        with fake_dns("2001:4860:4860::8888", "1.1.1.1"):
            result = guarded_create_connection(("example.com", 443))
        self.assertEqual(result, "connected")
        self.assertEqual(self.dial.call_count, 2)
        self.dial.assert_any_call(("1.1.1.1", 443))

    def test_raises_the_last_error_when_every_address_fails(self):
        self.dial.side_effect = [OSError("first"), OSError("second")]
        with fake_dns("8.8.8.8", "1.1.1.1"):
            with self.assertRaises(OSError) as caught:
                guarded_create_connection(("example.com", 443))
        self.assertEqual(str(caught.exception), "second")

    def test_ipv6_brackets_are_removed_before_the_lookup(self):
        with fake_dns("::1") as lookup:
            with self.assertRaises(BlockedAddressError):
                guarded_create_connection(("[::1]", 80))
        lookup.assert_called_once_with("::1", 80, type=socket.SOCK_STREAM)


class InstallGuardTests(SimpleTestCase):
    def test_install_replaces_the_library_dialer_and_is_repeatable(self):
        install_guard()
        install_guard()
        self.assertIs(urllib3_connection.create_connection, guarded_create_connection)


class LibraryWiringTests(SimpleTestCase):
    """Real requests and urllib3, but no traffic: the address is refused before dialing."""

    def test_requests_really_goes_through_the_guard(self):
        install_guard()
        with requests.Session() as session:
            session.trust_env = False
            with self.assertRaises(BlockedAddressError):
                session.get("http://127.0.0.1:9/", timeout=2)