"""Internationalisation helpers for every FastClinic user-facing surface.

English source copy is kept in the Python views and browser script.  The other
languages are checked-in JSON catalogues, so production never depends on a
translation service.  A request-local context lets shared view helpers translate
without threading ``lang`` through every function, while explicit ``lang``
arguments remain supported for public pages and background work.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


DEFAULT_LANG = "en"

LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
    "et": {"name": "Estonian", "native": "Eesti", "flag": "🇪🇪"},
    "de": {"name": "German", "native": "Deutsch", "flag": "🇩🇪"},
    "fr": {"name": "French", "native": "Français", "flag": "🇫🇷"},
    "sv": {"name": "Swedish", "native": "Svenska", "flag": "🇸🇪"},
    "lv": {"name": "Latvian", "native": "Latviešu", "flag": "🇱🇻"},
    "no": {"name": "Norwegian", "native": "Norsk", "flag": "🇳🇴"},
    "da": {"name": "Danish", "native": "Dansk", "flag": "🇩🇰"},
    "pl": {"name": "Polish", "native": "Polski", "flag": "🇵🇱"},
    "nl": {"name": "Dutch", "native": "Nederlands", "flag": "🇳🇱"},
    "fi": {"name": "Finnish", "native": "Suomi", "flag": "🇫🇮"},
    "lt": {"name": "Lithuanian", "native": "Lietuvių", "flag": "🇱🇹"},
}

SUPPORTED_LANGS = frozenset(LANGUAGES)
LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_CURRENT_LANG: ContextVar[str] = ContextVar("fastclinic_lang", default=DEFAULT_LANG)


class NoTranslate(str):
    """Marker for user-entered, clinical, identifier, and source-system values."""


def preserve(value: Any) -> NoTranslate:
    return NoTranslate("" if value is None else str(value))


@lru_cache(maxsize=None)
def _catalog(lang: str) -> dict[str, str]:
    if lang == DEFAULT_LANG or lang not in SUPPORTED_LANGS:
        return {}
    path = LOCALES_DIR / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def detect_language(request) -> str:
    header = (getattr(request, "headers", {}) or {}).get("accept-language", "")
    preferences: list[tuple[float, int, str]] = []
    for index, item in enumerate(header.split(",")):
        parts = item.strip().split(";")
        code = parts[0].split("-")[0].lower()
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.strip().startswith("q="):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0.0
        if quality > 0:
            preferences.append((quality, -index, code))
    for _, _, code in sorted(preferences, reverse=True):
        if code in SUPPORTED_LANGS:
            return code
    return DEFAULT_LANG


def get_lang(session: dict[str, Any], request=None) -> str:
    code = str(session.get("lang") or "").lower()
    if code in SUPPORTED_LANGS:
        return code
    code = detect_language(request) if request is not None else DEFAULT_LANG
    session["lang"] = code
    return code


def set_lang(session: dict[str, Any], lang: str) -> str:
    code = (lang or "").lower()
    if code in SUPPORTED_LANGS:
        session["lang"] = code
    return get_lang(session)


def safe_return_path(value: str | None) -> str:
    """Keep language changes on this application and reject open redirects."""
    value = value or "/"
    parsed = urlsplit(value)
    decoded = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or not decoded.startswith("/")
        or decoded.startswith("//")
        or "\\" in decoded
        or any(ord(character) < 32 for character in unquote(value))
    ):
        return "/"
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def current_lang() -> str:
    """Return the language active for the current request/task."""
    return _CURRENT_LANG.get()


@contextmanager
def using_lang(lang: str):
    """Temporarily activate a locale without leaking it across requests."""
    code = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    token = _CURRENT_LANG.set(code)
    try:
        yield code
    finally:
        _CURRENT_LANG.reset(token)


def t(text: str, lang: str | None = None, **values: Any) -> str:
    """Translate source text and optionally interpolate named placeholders."""
    code = current_lang() if lang is None else lang
    translated = text if code == DEFAULT_LANG else _catalog(code).get(text, text)
    if values:
        try:
            return translated.format(**values)
        except (KeyError, ValueError):
            return text.format(**values)
    return translated


def catalog(lang: str) -> dict[str, str]:
    return dict(_catalog(lang))


def js_translations(lang: str, keys: tuple[str, ...] | list[str]) -> dict[str, str]:
    """Return the small catalogue embedded for browser-generated UI copy."""
    return {key: t(key, lang) for key in keys}


def localize_tree(value: Any, lang: str | None = None) -> Any:
    """Translate known literal text and accessibility attributes in an FT tree.

    Only strings that exist as catalogue keys change.  Database and user-entered
    values therefore remain byte-for-byte intact, even though they share the same
    render tree as UI labels.
    """
    code = current_lang() if lang is None else lang
    if code == DEFAULT_LANG:
        return value
    translations = _catalog(code)

    try:
        from fastcore.basics import NotStr
        from fastcore.xml import FT
    except ImportError:  # pragma: no cover - only useful without the web extra
        return value

    def walk(node: Any) -> Any:
        if isinstance(node, NoTranslate):
            return node
        if isinstance(node, FT):
            node.children = tuple(walk(child) for child in node.children)
            for attr in ("placeholder", "title", "aria-label", "aria_label"):
                raw = node.attrs.get(attr)
                if isinstance(raw, str) and raw in translations:
                    node.attrs[attr] = translations[raw]
            return node
        if isinstance(node, NotStr):
            raw = str(node)
            return NotStr(translations.get(raw, raw))
        if isinstance(node, str):
            return translations.get(node, node)
        if isinstance(node, tuple):
            return tuple(walk(item) for item in node)
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(value)


_DECIMAL_COMMA = frozenset({"et", "de", "fr", "sv", "lv", "no", "da", "pl", "nl", "fi", "lt"})


def format_number(value: float | int, lang: str | None = None, decimals: int = 0) -> str:
    """Format a number using the active locale's decimal/group separators."""
    code = current_lang() if lang is None else lang
    rendered = f"{value:,.{decimals}f}"
    if code in _DECIMAL_COMMA:
        group = "\u202f" if code == "fr" else "\u00a0"
        rendered = rendered.replace(",", "\0").replace(".", ",").replace("\0", group)
    return rendered


def format_currency(value: float | int | None, currency: str = "GBP", lang: str | None = None,
                    decimals: int = 0) -> str:
    code = current_lang() if lang is None else lang
    amount = format_number(float(value or 0), code, decimals)
    symbol = {"GBP": "£", "EUR": "€"}.get(currency, currency)
    return f"{amount}\u00a0{symbol}" if code in _DECIMAL_COMMA else f"{symbol}{amount}"


def format_date(value: str | date | datetime | None, lang: str | None = None) -> str:
    """Format ISO dates for display; invalid/source values are left untouched."""
    if not value:
        return "—"
    code = current_lang() if lang is None else lang
    try:
        parsed = value.date() if isinstance(value, datetime) else value
        if isinstance(parsed, str):
            parsed = date.fromisoformat(parsed[:10])
        if not isinstance(parsed, date):
            return str(value)[:10]
    except (TypeError, ValueError):
        return str(value)[:10]
    if code == "en":
        return parsed.strftime("%d/%m/%Y")
    if code in {"sv", "lt"}:
        return parsed.strftime("%Y-%m-%d")
    return parsed.strftime("%d.%m.%Y")
