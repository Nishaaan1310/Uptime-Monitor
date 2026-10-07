from urllib.parse import urlparse
from django.core.exceptions import ValidationError

from .netguard import is_public_host


def validate_public_url(value):
    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Only HTTP and HTTPS URLs are supported.")

    hostname = parsed.hostname
    if not hostname:
        raise ValidationError("Invalid URL.")
    
    if is_public_host(hostname) is False:
        raise ValidationError("Cannot monitor private or internal addresses.")