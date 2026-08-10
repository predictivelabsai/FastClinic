#!/usr/bin/env python3
"""Inventory, check, and explicitly refresh FastClinic locale catalogues.

Production requests only read checked-in JSON. External translation is used by
this maintenance command, never by the deployed application.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.api import RESOURCES  # noqa: E402
from web.i18n import DEFAULT_LANG, LANGUAGES, LOCALES_DIR  # noqa: E402
from web.landing import FEATURES, PARTNERS  # noqa: E402


SOURCE_FILES = (ROOT / "web" / "landing.py", ROOT / "web" / "developer.py", ROOT / "web" / "account_auth.py")
TRANSLATING_CALLS = {"t", "T"}

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
    return []


def source_strings() -> set[str]:
    strings: set[str] = set()
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name in TRANSLATING_CALLS:
                strings.update(_literal(node.args[0]))
    for title, description in FEATURES:
        strings.update((title, description))
    strings.update(description for _, _, _, description in PARTNERS)
    for resource in RESOURCES:
        strings.update((resource.title, resource.description))
    strings.update({
        "Sign in to your FastClinic account",
        "Create your FastClinic account",
        "FastClinic account",
    })
    return {value for value in strings if value and value not in {"en", "/"}}


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
        if missing or stale or empty:
            valid = False
            print(f"{lang}: {len(missing)} missing, {len(stale)} stale, {len(empty)} empty")
            for label, values in (("missing", missing), ("stale", stale), ("empty", empty)):
                for value in values[:10]:
                    print(f"  {label}: {value}")
        else:
            print(f"{lang}: {len(locale)} translations complete")
    return valid


def _translate_one(text: str, lang: str) -> str:
    query = urlencode({"client": "gtx", "sl": "en", "tl": lang, "dt": "t", "q": text})
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
                return translated
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Translation failed for {lang}: {text}")


def refresh_catalogs(workers: int) -> None:
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    source = source_strings()
    for lang in LANGUAGES:
        if lang == DEFAULT_LANG:
            continue
        current = read_catalog(lang)
        locale = {key: current[key] for key in source if key in current and current[key].strip()}
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
