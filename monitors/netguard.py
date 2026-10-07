import ipaddress
import socket

from urllib3.util import connection as urllib3_connection

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


_original_create_connection = urllib3_connection.create_connection

def guarded_create_connection(address, *args, **kwargs):
    host, port = address
    host = host.strip("[]")
    ips = resolve_public_ips(host, port)

    last_error = None
    for ip in ips:
        try:
            return _original_create_connection((ip, port), *args, **kwargs)
        except OSError as e:
            last_error = e
    raise last_error

def install_guard():
    if urllib3_connection.create_connection is not guarded_create_connection:
        urllib3_connection.create_connection = guarded_create_connection

