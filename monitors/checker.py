import requests
import time
from urllib.parse import urlparse
from .validators import is_public_host

def check_url(url, timeout=10):
    result= {
        "is_up": False,
        "status_code": None,
        "response_time_ms": None,
        "error_message": "",
    }

    hostname = urlparse(url).hostname
    if not hostname or is_public_host(hostname) is not True:
        result["error_message"] = "Blocked: host is not a public address."
        return result

    start = time.monotonic()

    try:
        response = requests.get(url, timeout=timeout, allow_redirects=False)

    except requests.exceptions.Timeout:
        result["error_message"] = f"Timed out after {timeout}s"
    except requests.exceptions.RequestException as e:
        result["error_message"] = f"Service error: {e}"

    else:
        result["status_code"] = response.status_code
        result["is_up"] = response.status_code < 400
        result["response_time_ms"] = int((time.monotonic()-start) * 1000)
    return result

