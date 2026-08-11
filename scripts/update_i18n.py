#!/usr/bin/env python3
"""Inventory, check, and explicitly refresh FastClinic locale catalogues.

Production requests only read checked-in JSON. External translation is used by
this maintenance command, never by the deployed application.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.api import API_GROUPS, RESOURCES  # noqa: E402
from web.i18n import DEFAULT_LANG, LANGUAGES, LOCALES_DIR  # noqa: E402
from web.landing import FEATURES, PARTNERS  # noqa: E402
from web.layout import JS_I18N_KEYS, NAV_ITEMS, SAMPLE_QUESTIONS  # noqa: E402
from web.help_views import SHORTCUTS  # noqa: E402
from web.activation import RECUR_LABELS  # noqa: E402
from web.account_auth import AUTH_MESSAGES  # noqa: E402
from web.consent import SUPPRESSED_MSG  # noqa: E402
from pms.catalog import CATEGORY_LABELS, GENDER_LABELS, SPECIALTY_LABELS  # noqa: E402


SOURCE_FILES = tuple(sorted((ROOT / "web").glob("*.py"))) + (
    ROOT / "web_app.py",
    ROOT / "graph" / "clinic_assistant.py",
)
TRANSLATING_CALLS = {"t", "T"}
UI_CALLS = {
    "A", "Button", "Div", "H1", "H2", "H3", "H4", "Label", "Li", "NotStr",
    "Input", "Option", "P", "Select", "Span", "Strong", "Td", "Textarea", "Th", "Title",
}
SEMANTIC_CALLS = {"_page_title", "_table", "kpi_card"}
TRANSLATABLE_ATTRIBUTES = {"placeholder", "title", "aria_label"}
DO_NOT_TRANSLATE = {
    "", "en", "/", "—", "–", "&laquo;", "&rsaquo;", "&middot;", "×", "#", "F", "or", "£",
    "Fast", "Clinic", "FastClinic", "FastClinic Cockpit", "admin@fastclinic.example",
    "prompts/system_prompt.md", "e.g. 12", "e.g. 1206", "patient@example.com",
}
RUNTIME_UI_STRINGS = {
    "All", "Immunisations", "Health checks", "Repeat prescriptions",
    "Pending", "Scheduled", "Confirmed", "Cancelled", "Completed", "Blocked", "Failed",
    "pending", "scheduled", "confirmed", "cancelled", "completed", "blocked", "failed",
    "Paid", "Partly Paid", "Unpaid", "Overdue", "Manual", "Appointment",
    "Immunisation & plan due", "Lapsed reactivation", "Post-visit follow-up",
    "Contacts", "Clinical notes", "Billed items", "When", "Code", "For", "Total",
    "Account", "Normal", "Debit", "Credit", "Balance", "Setting", "Value",
    "Reply-To", "Message stream", "API token", "Configured", "Not configured yet", "Not set",
    "Env Vars", "Contact ID", "Date of birth", "age", "Clinician #{id}",
    "{count} mo", "{count}d", "✓ ledger balanced", "⚠ ledger NOT balanced",
    "Accounts Receivable", "Cash", "Fee Income",
}

OVERRIDE_KEYS = ("Choose language", "Partners", "Developers", "Sign In", "Register", "Clinic operations", "Continue with Google")
OVERRIDE_VALUES = {
    "et": ("Vali keel", "Partnerid", "Arendajatele", "Logi sisse", "Registreeru", "Kliiniku töökorraldus", "Jätka Google'iga"),
    "de": ("Sprache wählen", "Partner", "Entwickler", "Anmelden", "Registrieren", "Klinikbetrieb", "Mit Google fortfahren"),
    "fr": ("Choisir la langue", "Partenaires", "Développeurs", "Se connecter", "S’inscrire", "Opérations cliniques", "Continuer avec Google"),
    "sv": ("Välj språk", "Partner", "Utvecklare", "Logga in", "Registrera", "Klinikverksamhet", "Fortsätt med Google"),
    "lv": ("Izvēlēties valodu", "Partneri", "Izstrādātājiem", "Pierakstīties", "Reģistrēties", "Klīnikas darbība", "Turpināt ar Google"),
    "no": ("Velg språk", "Partnere", "Utviklere", "Logg inn", "Registrer", "Klinikkdrift", "Fortsett med Google"),
    "da": ("Vælg sprog", "Partnere", "Udviklere", "Log ind", "Registrer", "Klinikdrift", "Fortsæt med Google"),
    "pl": ("Wybierz język", "Partnerzy", "Dla deweloperów", "Zaloguj się", "Zarejestruj się", "Działalność kliniki", "Kontynuuj przez Google"),
    "nl": ("Kies taal", "Partners", "Ontwikkelaars", "Inloggen", "Registreren", "Kliniekactiviteiten", "Doorgaan met Google"),
    "fi": ("Valitse kieli", "Kumppanit", "Kehittäjille", "Kirjaudu sisään", "Rekisteröidy", "Klinikan toiminta", "Jatka Googlella"),
    "lt": ("Pasirinkti kalbą", "Partneriai", "Kūrėjams", "Prisijungti", "Registruotis", "Klinikos veikla", "Tęsti su „Google“"),
}
MANUAL_OVERRIDES = {
    lang: dict(zip(OVERRIDE_KEYS, values, strict=True))
    for lang, values in OVERRIDE_VALUES.items()
}


def _literal(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _literal(node.body) + _literal(node.orelse)
    return []


def source_strings() -> set[str]:
    strings: set[str] = set()
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name in TRANSLATING_CALLS and node.args:
                strings.update(_literal(node.args[0]))
            elif name in UI_CALLS:
                for argument in node.args:
                    strings.update(_literal(argument))
                for keyword in node.keywords:
                    if keyword.arg in TRANSLATABLE_ATTRIBUTES:
                        strings.update(_literal(keyword.value))
            elif name in SEMANTIC_CALLS:
                if name in {"_page_title", "kpi_card"} and node.args:
                    strings.update(_literal(node.args[0]))
                    if name == "_page_title" and len(node.args) > 1:
                        strings.update(_literal(node.args[1]))
                elif name == "_table" and node.args:
                    for item in getattr(node.args[0], "elts", ()):  # literal header list/tuple
                        strings.update(_literal(item))
    for title, description in FEATURES:
        strings.update((title, description))
    strings.update(description for _, _, _, description in PARTNERS)
    for resource in RESOURCES:
        strings.update((resource.title, resource.description))
    for title, description, operations in API_GROUPS:
        strings.update((title, description))
        for _methods, _path, summary, access in operations:
            strings.update((summary, access))
    strings.update(JS_I18N_KEYS)
    strings.update(SAMPLE_QUESTIONS)
    strings.update(RECUR_LABELS.values())
    strings.update(AUTH_MESSAGES)
    strings.add(SUPPRESSED_MSG)
    strings.update(CATEGORY_LABELS.values())
    strings.update(SPECIALTY_LABELS.values())
    strings.update(GENDER_LABELS.values())
    seo_config = yaml.safe_load((ROOT / "prompts" / "seo" / "_config.yaml").read_text(encoding="utf-8"))
    strings.update(component["title"] for component in seo_config.get("components", []))
    strings.update(column.replace("_", " ").title()
                   for component in seo_config.get("components", [])
                   for column in component.get("columns", []))
    strings.update({"yes", "pass", "good", "excellent", "high", "no", "fail", "poor",
                    "missing", "partial", "warn", "ok", "fair", "medium", "pending"})
    strings.update(RUNTIME_UI_STRINGS)
    strings.update(description for _, description in SHORTCUTS)
    for section, items in NAV_ITEMS:
        strings.add(section)
        strings.update(label for _, label, _, _ in items)
    strings.update({
        "Sign in to your FastClinic account",
        "Create your FastClinic account",
        "FastClinic account",
    })
    return {value for value in strings if value.strip() and value not in DO_NOT_TRANSLATE}


def read_catalog(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in data.items()):
        raise ValueError(f"{path} must contain a string-to-string JSON object")
    return data


def check_catalogs() -> bool:
    source = source_strings()
    valid = True
    for lang in LANGUAGES:
        if lang == DEFAULT_LANG:
            continue
        locale = read_catalog(lang)
        missing = sorted(source - locale.keys())
        stale = sorted(locale.keys() - source)
        empty = sorted(key for key, value in locale.items() if not value.strip())
        placeholders = sorted(
            key for key, value in locale.items()
            if _fields(key) != _fields(value)
        )
        markup = sorted(
            key for key, value in locale.items()
            if _markup_signature(key) != _markup_signature(value)
        )
        if missing or stale or empty or placeholders or markup:
            valid = False
            print(f"{lang}: {len(missing)} missing, {len(stale)} stale, {len(empty)} empty, "
                  f"{len(placeholders)} placeholder mismatches, {len(markup)} markup mismatches")
            for label, values in (("missing", missing), ("stale", stale), ("empty", empty),
                                  ("placeholder", placeholders), ("markup", markup)):
                for value in values[:10]:
                    print(f"  {label}: {value}")
        else:
            print(f"{lang}: {len(locale)} translations complete")
    return valid


def _fields(value: str) -> set[str]:
    try:
        return {name for _, name, _, _ in string.Formatter().parse(value) if name}
    except ValueError:
        return {"<invalid>"}


def _markup_signature(value: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Markup/code that translations must preserve exactly."""
    tags = tuple(re.findall(r"<[^>]+>", value))
    code = tuple(re.findall(r"<code[^>]*>(.*?)</code>", value, flags=re.DOTALL))
    entities = tuple(re.findall(r"&(?:[A-Za-z][A-Za-z0-9]+|#\d+|#x[0-9A-Fa-f]+);", value))
    return tags, code, entities


def _translate_plain(text: str, lang: str) -> str:
    if not text.strip():
        return text
    leading = text[:len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    source = text.strip()
    placeholders: dict[str, str] = {}
    protected_pattern = re.compile(
        r"&(?:[A-Za-z][A-Za-z0-9]+|#\d+|#x[0-9A-Fa-f]+);|"
        r"\{[A-Za-z_]\w*(?:![^}:]+)?(?::[^}]+)?\}",
        flags=re.DOTALL,
    )

    def protect(match: re.Match) -> str:
        token = f"⟦{len(placeholders)}⟧"
        placeholders[token] = match.group(0)
        return token

    protected = protected_pattern.sub(protect, source)
    query = urlencode({"client": "gtx", "sl": "en", "tl": lang, "dt": "t", "q": protected})
    request = Request(
        f"https://translate.googleapis.com/translate_a/single?{query}",
        headers={"User-Agent": "FastClinic translation maintenance/1.0"},
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
            if translated:
                for token, raw in placeholders.items():
                    translated = translated.replace(token, raw)
                if _fields(translated) != _fields(source):
                    raise ValueError(f"Translation changed placeholders: {source!r} -> {translated!r}")
                return leading + translated + trailing
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Translation failed for {lang}: {text}")


def _translate_one(text: str, lang: str) -> str:
    """Translate plain text or each text node of an HTML fragment safely."""
    if "<" not in text:
        return _translate_plain(text, lang)
    parts = re.split(r"(<code[^>]*>.*?</code>|<[^>]+>)", text, flags=re.DOTALL)
    translated = "".join(
        part if not part or part.startswith("<") else _translate_plain(part, lang)
        for part in parts
    )
    if _fields(translated) != _fields(text):
        raise ValueError(f"Translation changed placeholders: {text!r} -> {translated!r}")
    if _markup_signature(translated) != _markup_signature(text):
        raise ValueError(f"Translation changed markup: {text!r} -> {translated!r}")
    return translated


def refresh_catalogs(workers: int) -> None:
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    source = source_strings()
    for lang in LANGUAGES:
        if lang == DEFAULT_LANG:
            continue
        current = read_catalog(lang)
        locale = {key: current[key] for key in source
                  if key in current and current[key].strip()
                  and _fields(key) == _fields(current[key])
                  and _markup_signature(key) == _markup_signature(current[key])}
        missing = sorted(source - locale.keys())
        print(f"{lang}: translating {len(missing)} of {len(source)} strings")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_translate_one, text, lang): text for text in missing}
            for index, future in enumerate(as_completed(futures), 1):
                locale[futures[future]] = future.result()
                if index % 25 == 0 or index == len(missing):
                    print(f"  {index}/{len(missing)}")
        locale.update(MANUAL_OVERRIDES[lang])
        path = LOCALES_DIR / f"{lang}.json"
        path.write_text(json.dumps(locale, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translate", action="store_true", help="translate missing copy and rewrite catalogues")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.translate:
        refresh_catalogs(max(1, args.workers))
    return 0 if check_catalogs() else 1


if __name__ == "__main__":
    raise SystemExit(main())
