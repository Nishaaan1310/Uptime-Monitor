import requests
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from .validators import is_public_host

@dataclass(frozen=True)
class CheckOutcome:
    is_up: bool
    status_code : int | None = None
    response_time_ms: int | None = None
    error_message: str = ""

def check_url(url, timeout=10):
    hostname = urlparse(url).hostname
    if not hostname or is_public_host(hostname) is not True:
        return CheckOutcome(is_up=False, error_message="Blocked: host is not a public address.")

    start = time.monotonic()

    try:
        response = requests.get(url, timeout=timeout, allow_redirects=False)

    except requests.exceptions.Timeout:
        return CheckOutcome(is_up=False, error_message=f"Timed out after {timeout}s")

    except requests.exceptions.RequestException as e:
        return CheckOutcome(is_up=False, error_message=f"Service error: {e}")

    elapsed_ms = int((time.monotonic()-start) * 1000)
    return CheckOutcome(
       is_up=response.status_code < 400,
       status_code=response.status_code,
       response_time_ms=elapsed_ms
    )

