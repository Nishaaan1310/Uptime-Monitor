import socket
from unittest.mock import patch


def fake_addrinfo(*addresses):
    results = []
    for address in addresses:
        if ":" in address:
            family = socket.AF_INET6
            sockaddr = (address, 0, 0, 0)       # IPv6 entries have four parts
        else:
            family = socket.AF_INET
            sockaddr = (address, 0)             # IPv4 entries have two
        results.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
    return results


def fake_dns(*addresses):
    """Every DNS lookup answers with these addresses."""
    return patch("socket.getaddrinfo", return_value=fake_addrinfo(*addresses))


from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from monitors.models import Monitor


def make_user(email="owner@example.com"):
    return get_user_model().objects.create_user(email=email, password="pass12345")


def make_monitor(owner, name="Blog", url="https://example.com", next_check_at=None, **extra):
    return Monitor.objects.create(
        owner=owner,
        name=name,
        url=url,
        next_check_at=next_check_at or timezone.now() - timedelta(minutes=1),   # due by default
        **extra,
    )