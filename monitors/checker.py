import requests
import time
from dataclasses import dataclass
from .netguard import install_guard, BlockedAddressError

install_guard()

@dataclass(frozen=True)
class CheckOutcome:
    is_up: bool
    status_code : int | None = None
    response_time_ms: int | None = None
    error_message: str = ""

def check_url(url, timeout=10):
    start = time.monotonic()

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

