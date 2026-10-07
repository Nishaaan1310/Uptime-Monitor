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