"""Rate limiting configuration using slowapi.

Default limits:
- Public endpoints (/health): unlimited
- Authenticated endpoints: 100 req/min per IP
- Camera registration: 10 req/min (spam prevention)
- Firmware upload: 5 req/min (prevent loop attacks)
- Person enrollment: 20 req/min
"""

from slowapi import Limiter
from slowapi.util import get_remote_address


class NoOpLimiter:
    """Passthrough limiter that doesn't enforce limits (temporary)."""
    def limit(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


limiter = NoOpLimiter()  # Temporarily disabled — see TODO below

# Rate limit profiles
LIMIT_DEFAULT = "100/minute"  # Standard authenticated endpoint
LIMIT_REGISTER = "10/minute"  # Camera registration (spam prevention)
LIMIT_FIRMWARE = "5/minute"   # Firmware upload (prevent OTA loop DoS)
LIMIT_PERSON = "20/minute"    # Person management
LIMIT_TRIGGER = "60/minute"   # Per-IP camera trigger (bursts allowed)
LIMIT_WEBHOOK = "30/minute"   # Webhook management
