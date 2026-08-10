"""Internationalisation helpers for FastClinic's public surface."""

from __future__ import annotations

import json
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


def t(text: str, lang: str = DEFAULT_LANG) -> str:
    if lang == DEFAULT_LANG:
        return text
    return _catalog(lang).get(text, text)


def catalog(lang: str) -> dict[str, str]:
    return dict(_catalog(lang))
