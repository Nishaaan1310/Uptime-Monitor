import ipaddress
import socket
from urllib.parse import urlparse
from django.core.exceptions import ValidationError

class BlockedAddressError(Exception):
    pass

def resolve_public_ips(host, port=None):
    
    # By adding socktype=socket.SOCK_STREAM, we tell it: 
    # "Only give me TCP records. Ignore UDP duplicates!"
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


def validate_public_url(value):
    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Only HTTP and HTTPS URLs are supported.")

    hostname = parsed.hostname
    if not hostname:
        raise ValidationError("Invalid URL.")
    
    if is_public_host(hostname) is False:
        raise ValidationError("Cannot monitor private or internal addresses.")