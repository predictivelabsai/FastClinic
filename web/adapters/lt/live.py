"""Live Lithuanian transports: configuration-aware and fail-closed."""
from __future__ import annotations

import os

from web.adapters.base import AdapterNotAvailable

LIVE_FLAG = "LT_ESPBI_LIVE_ENABLED"
REQUIRED = (
    "LT_ESPBI_BASE_URL", "LT_ESPBI_CONSUMER_KEY", "LT_ESPBI_PRIVATE_KEY_FILE",
    "LT_ESPBI_ORGANIZATION_JAR", "LT_ESPBI_SPEC_VERSION",
)


def live_enabled() -> bool:
    return (os.getenv(LIVE_FLAG) or "").strip().lower() in {"1", "true", "yes"}


def missing_live_config() -> list[str]:
    return [key for key in REQUIRED if not (os.getenv(key) or "").strip()]


def submit(*_args, **_kwargs):
    missing = missing_live_config()
    raise AdapterNotAvailable(
        "Live ESPBI transport is deliberately disabled: a clinic-specific "
        "Registru centras agreement, approved endpoint/profile versions, test "
        "acceptance and qualified-signature provider are required. "
        f"{LIVE_FLAG}={live_enabled()}; missing={missing or 'none'}."
    )
