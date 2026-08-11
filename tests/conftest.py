"""Keep test collection isolated from deployment paths loaded from ``.env``."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


_TEST_STORAGE = tempfile.TemporaryDirectory(prefix="fastclinic-pytest-")
_TEST_ROOT = Path(_TEST_STORAGE.name)

# Some production modules load .env at import time. Defining writable state
# paths before test modules are collected prevents a local Docker path such as
# /data from leaking into unit tests, regardless of collection order. The
# committed synthetic clinical database remains the read-only test fixture.
os.environ.setdefault("FASTCLINIC_OPS_DB", str(_TEST_ROOT / "operations.sqlite"))
os.environ.setdefault("FASTSME_AUTH_DB", str(_TEST_ROOT / "accounts.sqlite"))


def pytest_unconfigure(config):
    _TEST_STORAGE.cleanup()
