import requests
import time
from urllib3.util import connection as urllib3_connection
from dataclasses import dataclass
from urllib.parse import urlparse
from .validators import resolve_public_ips, BlockedAddressError

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



@dataclass(frozen=True)
class CheckOutcome:
    is_up: bool
    status_code : int | None = None
    response_time_ms: int | None = None
    error_message: str = ""

def check_url(url, timeout=10):
    start = time.monotonic()
    
    guard=install_guard()

    with requests.Session() as session:
        session.trust_env = False
        session.max_redirects = 5

        try:
            response = session.get(url, timeout=timeout)

        except requests.exceptions.TooManyRedirects:
            return CheckOutcome(is_up=False, error_message=f"Too many redirects (limit 5)")

        except requests.exceptions.Timeout:
            return CheckOutcome(is_up=False, error_message=f"Timed out after {timeout}s")

        except requests.exceptions.RequestException as e:
            return CheckOutcome(is_up=False, error_message=f"Service error: {e}")
        
        except BlockedAddressError:
            return CheckOutcome(is_up=False, error_message="Blocked: host resolves to a non-public address.")

    elapsed_ms = int((time.monotonic()-start) * 1000)

    return CheckOutcome(
        is_up=response.status_code < 400,
        status_code=response.status_code,
        response_time_ms=elapsed_ms
    )

