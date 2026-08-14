"""Country-adapter registry.

The core never imports a national module directly. Call ``get_adapter('GB')``.
Unknown countries raise ``AdapterNotAvailable``.
"""
from __future__ import annotations

from web.adapters.base import AdapterNotAvailable, CountryAdapter

_ADAPTERS = {
    "GB": "web.adapters.nhs",
    "UK": "web.adapters.nhs",
}


def available_countries() -> list[str]:
    return ["GB"]


def get_adapter(country_code: str) -> CountryAdapter:
    code = (country_code or "").strip().upper()
    module_name = _ADAPTERS.get(code)
    if not module_name:
        raise AdapterNotAvailable(
            f"No country adapter is registered for {country_code!r}. "
            f"Implemented: {', '.join(available_countries())}."
        )
    import importlib
    module = importlib.import_module(module_name)
    adapter = getattr(module, "adapter", module)
    return adapter
