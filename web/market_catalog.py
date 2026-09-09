"""Editorial competitor targets and wellness-service taxonomy.

The target list makes important competitors durable before a crawler has managed to
extract a price list.  It is deliberately separate from observed market facts: every
price, address and source shown as evidence still comes from the append-only market
tables.
"""

from __future__ import annotations

import re


CAPABILITIES = [
    ("iv_therapy", "IV therapy"),
    ("longevity", "Longevity"),
    ("primary_care", "Primary care"),
    ("diagnostics", "Diagnostics"),
    ("multi_specialty", "Multi-specialty"),
]


TARGETS = [
    {
        "slug": "sync",
        "name": "SYNC Longevity Clinic",
        "domains": ("syncclinic.lt",),
        "segment": "IV / longevity specialist",
        "cities": ("Vilnius",),
        "positioning": "IV-led longevity and recovery protocols",
        "scope": 2,
        "iv_focus": 5,
        "capabilities": ("iv_therapy", "longevity", "diagnostics"),
        "service_url": "https://syncclinic.lt/laselines-iv-terapijos/",
    },
    {
        "slug": "id-clinic",
        "name": "ID Clinic",
        "domains": ("idclinic.lt",),
        "segment": "IV / longevity specialist",
        "cities": ("Vilnius",),
        "positioning": "Longevity programmes and dedicated infusion menu",
        "scope": 2,
        "iv_focus": 5,
        "capabilities": ("iv_therapy", "longevity", "diagnostics"),
        "service_url": "https://idclinic.lt/paslauga/longevity-programa/",
    },
    {
        "slug": "aum",
        "name": "AUM Wellness Clinic",
        "domains": ("aumclinic.lt",),
        "segment": "IV / longevity specialist",
        "cities": ("Vilnius",),
        "positioning": "Premium preventive medicine and wellness",
        "scope": 3,
        "iv_focus": 5,
        "capabilities": ("iv_therapy", "longevity", "diagnostics"),
        "service_url": "https://www.aumclinic.lt/intravenines-terapijos/",
    },
    {
        "slug": "unavita",
        "name": "UnaVita Private Clinic",
        "domains": ("unavita.lt",),
        "segment": "IV / longevity specialist",
        "cities": ("Vilnius",),
        "positioning": "Private clinic with a distinct IV therapy line",
        "scope": 2,
        "iv_focus": 4,
        "capabilities": ("iv_therapy", "longevity", "diagnostics"),
        "service_url": "https://unavita.lt/lt/paslaugos/intravenines-terapijos",
    },
    {
        "slug": "unomeda",
        "name": "Unomeda Klinika",
        "domains": ("unomeda.lt",),
        "segment": "IV / longevity specialist",
        "cities": ("Vilnius", "Kaunas", "Klaipėda"),
        "positioning": "Specialist network with vitamin/mineral IV therapy",
        "scope": 3,
        "iv_focus": 4,
        "capabilities": ("iv_therapy", "diagnostics", "multi_specialty"),
        "service_url": "https://unomeda.lt/vilnius/paslauga/",
    },
    {
        "slug": "bendrystes",
        "name": "Bendrystės klinika",
        "domains": ("bendrystesklinika.lt",),
        "segment": "IV / longevity specialist",
        "cities": ("Vilnius",),
        "positioning": "Medically positioned infusion therapy",
        "scope": 2,
        "iv_focus": 4,
        "capabilities": ("iv_therapy", "primary_care"),
        "service_url": "https://www.bendrystesklinika.lt/lasines-infuzijos",
    },
    {
        "slug": "northway",
        "name": "Northway",
        "domains": ("nmc.lt",),
        "segment": "Multi-specialty clinic",
        "cities": ("Vilnius", "Kaunas", "Klaipėda"),
        "positioning": "Direct multi-city competitor with medicine and IV therapy",
        "scope": 5,
        "iv_focus": 3,
        "capabilities": ("iv_therapy", "primary_care", "diagnostics", "multi_specialty"),
        "service_url": "https://nmc.lt/medicinos-paslaugos/laselines/",
    },
    {
        "slug": "meliva",
        "name": "Meliva",
        "domains": ("meliva.lt", "inmedica.lt"),
        "segment": "Multi-specialty clinic",
        "cities": ("National",),
        "positioning": "Lithuania's broad private medical network",
        "scope": 5,
        "iv_focus": 2,
        "capabilities": ("iv_therapy", "primary_care", "diagnostics", "multi_specialty"),
        "service_url": "https://inmedica.lt/paslaugos-ir-kainos/768/intravenine-infuzija-iki-30-min.-be-vaistu-ir-med.-priemoniu-kainos",
    },
    {
        "slug": "affidea",
        "name": "Affidea Lietuva",
        "domains": ("affidea.lt",),
        "segment": "Multi-specialty clinic",
        "cities": ("National",),
        "positioning": "Large diagnostics and multi-specialty network",
        "scope": 5,
        "iv_focus": 2,
        "capabilities": ("iv_therapy", "diagnostics", "multi_specialty"),
        "service_url": "https://affidea.lt/lt/",
    },
    {
        "slug": "anteja",
        "name": "Antėja",
        "domains": ("anteja.lt",),
        "segment": "Multi-specialty clinic",
        "cities": ("National",),
        "positioning": "Diagnostics-led private clinic network",
        "scope": 5,
        "iv_focus": 2,
        "capabilities": ("iv_therapy", "primary_care", "diagnostics", "multi_specialty"),
        "service_url": "https://anteja.lt/",
    },
    {
        "slug": "privatus-gydytojas",
        "name": "Privatus gydytojas",
        "domains": ("privatus-gydytojas.lt",),
        "segment": "Multi-specialty clinic",
        "cities": ("Vilnius",),
        "positioning": "Family and specialist medicine with wellness IV add-ons",
        "scope": 3,
        "iv_focus": 2,
        "capabilities": ("iv_therapy", "primary_care", "diagnostics", "multi_specialty"),
        "service_url": "https://privatus-gydytojas.lt/apie-klinika/",
    },
    {
        "slug": "rvl",
        "name": "RVL klinika",
        "domains": ("rvl.lt",),
        "segment": "Multi-specialty clinic",
        "cities": ("Vilnius",),
        "positioning": "Family clinic with procedure-room infusions",
        "scope": 3,
        "iv_focus": 2,
        "capabilities": ("iv_therapy", "primary_care", "diagnostics", "multi_specialty"),
        "service_url": "https://rvl.lt/paslaugos/",
    },
]


WELLNESS_TERMS = re.compile(
    r"intraven|infuz|laš(?:el|in)|las(?:el|in)|vitamin(?:ų|u|\s+drip)|"
    r"\biv\b|nad\+?|glutation|glutathion|hydration|detox|recovery|longevity|"
    r"anti[ -]?aging|wellness|sveikating|ilgaamž"
    r"|after party|leaky gut|beauty\s*(?:&|and)\s*glow|immune shield|"
    r"energy boost|anti[ -]?stress|burnout relax",
    re.IGNORECASE,
)


def is_wellness_service(row_or_text) -> bool:
    """Classify IV, longevity and adjacent wellness services across LT/EN labels."""
    if isinstance(row_or_text, dict):
        text = " ".join(
            str(row_or_text.get(key, ""))
            for key in ("service", "original_name", "evidence")
        )
    else:
        text = str(row_or_text or "")
    return bool(WELLNESS_TERMS.search(text))


def target_for_domain(host: str):
    host = (host or "").lower().removeprefix("www.")
    return next((t for t in TARGETS if host in t["domains"]), None)


def target_search_jobs():
    """High-value, official-domain searches used by the bounded market worker."""
    terms = (
        'intraveninė terapija lašelinė infuzija vitaminai NAD glutationas '
        'kainos kainynas paslaugos kontaktai "privati klinika"'
    )
    return [
        (
            "LT",
            f"site:{target['domains'][0]} {terms}",
            list(target["domains"]),
            target["slug"],
        )
        for target in TARGETS
    ]
