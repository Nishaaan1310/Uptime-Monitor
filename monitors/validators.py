import ipaddress
import socket
from urllib.parse import urlparse
from django.core.exceptions import ValidationError

def is_public_host(hostname):

    """True if every address is public, False if any is not, None if unresolvable."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return None

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global:
            return False
    return True

def validate_public_url(value):
    hostname = urlparse(value).hostname
    if not hostname:
        raise ValidationError("Invalid URL.")
    
    if is_public_host(hostname) is False:
        raise ValidationError("Cannot monitor private or internal addresses.")