import requests
import time
from dataclasses import dataclass
from .netguard import install_guard, BlockedAddressError
from urllib.parse import urljoin, urlparse

install_guard()

@dataclass(frozen=True)
class CheckOutcome:
    is_up: bool
    status_code : int | None = None
    response_time_ms: int | None = None
    error_message: str = ""


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
MAX_ERROR_LENGTH = 300
DEFAULT_TIMEOUT = 10

def short(text):
    return text if len(text) <= MAX_ERROR_LENGTH else text[:MAX_ERROR_LENGTH] + "..."

def check_url(url, timeout=DEFAULT_TIMEOUT):
    start = time.monotonic()
    deadline = start + timeout
    current_url = url

    with requests.Session() as session:
        session.trust_env = False

        for _ in range(MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0 :
                return CheckOutcome(is_up=False, error_message= f"Timed out after {timeout}s")

            try:
                response = session.get(
                    current_url,
                    timeout=(min(5, remaining), remaining),
                    allow_redirects=False,
                    stream=True
                )
            
            except BlockedAddressError:
                return CheckOutcome(is_up=False, error_message="Blocked: host resolves to a non-public address.")
            except requests.exceptions.Timeout:
                return CheckOutcome(is_up=False, error_message=f"Timed out after {timeout}s")
            except requests.exceptions.RequestException as e:
                return CheckOutcome(is_up=False, error_message=short(f"Service error: {e}"))
            
            location = response.headers.get("Location")
            if response.status_code in REDIRECT_STATUSES and location:
                response.close()
                current_url = urljoin(current_url, location)
                if urlparse(current_url).scheme not in ("http", "https"):
                    return CheckOutcome(is_up=False, error_message="Redirected to an unsupported address")
                continue

            status = response.status_code
            response.close()
            elapsed_ms = int((time.monotonic()-start) * 1000)

            return CheckOutcome(
                is_up=status < 400,
                status_code=response.status_code,
                response_time_ms=elapsed_ms
            )
            
    return CheckOutcome(is_up=False, error_message=f"Too many redirects (limit {MAX_REDIRECTS})")



