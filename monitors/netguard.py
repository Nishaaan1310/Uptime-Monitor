import ipaddress
import socket
from urllib3.util import connection as urllib3_connection
from itertools import zip_longest

class BlockedAddressError(Exception):
    pass

def resolve_public_ips(host, port=None):
    
    # type=socket.SOCK_STREAM, for to ignore UDP and get only TCP records.(Removes duplicates)
    
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise BlockedAddressError("non-public address")
        ips.append(str(ip))
    return ips

def is_public_host(hostname):

    """True if every address is public, False if any is not, None if unresolvable."""
    try:
        resolve_public_ips(hostname)
    except BlockedAddressError:
        return False
    except socket.gaierror:
        return None
    return True


def interleave_families(ips):
    """
    Splits IP addresses into IPv4 and IPv6 groups and interleaves them.
    Guarantees that a limited slice (e.g. [:4]) tests both IPv6 and IPv4 routes.
    """

    v4 = [ip for ip in ips if ":" not in ip]
    v6 = [ip for ip in ips if ":" in ip]
    ordered = []
    for pair in zip_longest(v6, v4):
        ordered.extend(ip for ip in pair if ip)
    return ordered


MAX_ADDRESSES = 4

_original_create_connection = urllib3_connection.create_connection

def guarded_create_connection(address, *args, **kwargs):
    host, port = address
    host = host.strip("[]")
    ips = resolve_public_ips(host, port)

    ordered_ips = interleave_families(ips)

    last_error = None
    for ip in ordered_ips[:MAX_ADDRESSES]:
        try:
            return _original_create_connection((ip, port), *args, **kwargs)
        except OSError as e:
            last_error = e
    raise last_error

def install_guard():
    if urllib3_connection.create_connection is not guarded_create_connection:
        urllib3_connection.create_connection = guarded_create_connection

