"""Pure X-Road REST request-context builder for TEHIK sandbox previews."""
from __future__ import annotations

import uuid


def headers(
    *, client: str, user_personal_code: str, issue: str,
    request_id: str | None = None,
) -> dict[str, str]:
    if client.count("/") != 3:
        raise ValueError("X-Road client must be INSTANCE/CLASS/MEMBER/SUBSYSTEM")
    if not issue.strip():
        raise ValueError("X-Road issue (purpose) is required")
    return {
        "X-Road-Client": client,
        "X-Road-UserId": f"EE{user_personal_code}",
        "X-Road-Id": request_id or str(uuid.uuid4()),
        "X-Road-ProtocolVersion": "4.0",
        "X-Road-Issue": issue.strip(),
    }


def mpi_urls(*, security_server: str, instance: str = "ee-dev") -> dict:
    base = security_server.rstrip("/")
    return {
        "auth": f"{base}/r1/{instance}/GOV/70009770/tis/auth",
        "mpi": f"{base}/r1/{instance}/GOV/70009770/tis/mpi",
    }
