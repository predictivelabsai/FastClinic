"""Live TEHIK/X-Road transport gate."""
from __future__ import annotations

import os

from web.adapters.base import AdapterNotAvailable

LIVE_FLAG = "EE_TIS_LIVE_ENABLED"
REQUIRED = (
    "EE_XROAD_SECURITY_SERVER", "EE_XROAD_INSTANCE", "EE_XROAD_CLIENT",
    "EE_TIS_ORGANIZATION_CODE", "EE_TIS_PROFILE_VERSION",
)


def live_enabled() -> bool:
    return (os.getenv(LIVE_FLAG) or "").strip().lower() in {"1", "true", "yes"}


def missing_live_config() -> list[str]:
    return [key for key in REQUIRED if not (os.getenv(key) or "").strip()]


def submit(*_args, **_kwargs):
    raise AdapterNotAvailable(
        "Live TIS transport is disabled. Production requires a licensed Estonian "
        "healthcare provider, X-Road membership/security-server subsystem, TEHIK "
        "service permissions, approved formats and acceptance tests. "
        f"{LIVE_FLAG}={live_enabled()}; missing={missing_live_config() or 'none'}."
    )
