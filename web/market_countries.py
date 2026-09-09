"""European Economic Area market registry and multilingual discovery queries.

Country coverage is data-driven so dashboards, campaign queues and scrapers do
not need another code path whenever a market is activated. The registry covers
the 27 EU Member States plus Iceland, Liechtenstein and Norway.
"""

from __future__ import annotations


EEA = {
    "AT": {"name": "Austria", "currency": "EUR", "language": "German", "cities": ("Vienna", "Graz", "Linz", "Salzburg"), "local": "Privatklinik Krankenhaus Behandlungen Preise"},
    "BE": {"name": "Belgium", "currency": "EUR", "language": "Dutch, French", "cities": ("Brussels", "Antwerp", "Ghent", "Liège"), "local": "privékliniek clinique privée ziekenhuis hôpital tarifs prijzen"},
    "BG": {"name": "Bulgaria", "currency": "EUR", "language": "Bulgarian", "cities": ("Sofia", "Plovdiv", "Varna", "Burgas"), "local": "частна клиника болница услуги цени"},
    "HR": {"name": "Croatia", "currency": "EUR", "language": "Croatian", "cities": ("Zagreb", "Split", "Rijeka", "Osijek"), "local": "privatna klinika bolnica usluge cjenik"},
    "CY": {"name": "Cyprus", "currency": "EUR", "language": "Greek, Turkish", "cities": ("Nicosia", "Limassol", "Larnaca", "Paphos"), "local": "ιδιωτική κλινική νοσοκομείο θεραπείες τιμές"},
    "CZ": {"name": "Czechia", "currency": "CZK", "language": "Czech", "cities": ("Prague", "Brno", "Ostrava", "Plzeň"), "local": "soukromá klinika nemocnice služby ceník"},
    "DK": {"name": "Denmark", "currency": "DKK", "language": "Danish", "cities": ("Copenhagen", "Aarhus", "Odense", "Aalborg"), "local": "privathospital privatklinik behandling priser"},
    "EE": {"name": "Estonia", "currency": "EUR", "language": "Estonian", "cities": ("Tallinn", "Tartu", "Pärnu", "Narva"), "local": "erakliinik erahaigla teenused hinnakiri"},
    "FI": {"name": "Finland", "currency": "EUR", "language": "Finnish, Swedish", "cities": ("Helsinki", "Tampere", "Turku", "Oulu"), "local": "yksityinen klinikka sairaala hoidot hinnasto"},
    "FR": {"name": "France", "currency": "EUR", "language": "French", "cities": ("Paris", "Lyon", "Marseille", "Toulouse"), "local": "clinique privée hôpital traitements tarifs"},
    "DE": {"name": "Germany", "currency": "EUR", "language": "German", "cities": ("Berlin", "Munich", "Hamburg", "Frankfurt"), "local": "Privatklinik Krankenhaus Behandlungen Preise"},
    "GR": {"name": "Greece", "currency": "EUR", "language": "Greek", "cities": ("Athens", "Thessaloniki", "Patras", "Heraklion"), "local": "ιδιωτική κλινική νοσοκομείο θεραπείες τιμές"},
    "HU": {"name": "Hungary", "currency": "HUF", "language": "Hungarian", "cities": ("Budapest", "Debrecen", "Szeged", "Pécs"), "local": "magánklinika magánkórház kezelések árlista"},
    "IE": {"name": "Ireland", "currency": "EUR", "language": "English, Irish", "cities": ("Dublin", "Cork", "Galway", "Limerick"), "local": "private clinic hospital treatments prices"},
    "IT": {"name": "Italy", "currency": "EUR", "language": "Italian", "cities": ("Rome", "Milan", "Naples", "Turin"), "local": "clinica privata ospedale trattamenti prezzi"},
    "LV": {"name": "Latvia", "currency": "EUR", "language": "Latvian", "cities": ("Riga", "Daugavpils", "Liepāja", "Jelgava"), "local": "privāta klīnika slimnīca pakalpojumi cenrādis"},
    "LT": {"name": "Lithuania", "currency": "EUR", "language": "Lithuanian", "cities": ("Vilnius", "Kaunas", "Klaipėda", "Šiauliai"), "local": "privati klinika ligoninė paslaugos kainynas"},
    "LU": {"name": "Luxembourg", "currency": "EUR", "language": "Luxembourgish, French, German", "cities": ("Luxembourg", "Esch-sur-Alzette", "Differdange", "Dudelange"), "local": "clinique privée Privatklinik traitements tarifs"},
    "MT": {"name": "Malta", "currency": "EUR", "language": "Maltese, English", "cities": ("Sliema", "Valletta", "Birkirkara", "St Julian's"), "local": "private clinic hospital treatments prices"},
    "NL": {"name": "Netherlands", "currency": "EUR", "language": "Dutch", "cities": ("Amsterdam", "Rotterdam", "The Hague", "Utrecht"), "local": "privékliniek ziekenhuis behandelingen prijzen"},
    "PL": {"name": "Poland", "currency": "PLN", "language": "Polish", "cities": ("Warsaw", "Kraków", "Wrocław", "Gdańsk"), "local": "prywatna klinika szpital usługi cennik"},
    "PT": {"name": "Portugal", "currency": "EUR", "language": "Portuguese", "cities": ("Lisbon", "Porto", "Braga", "Coimbra"), "local": "clínica privada hospital tratamentos preços"},
    "RO": {"name": "Romania", "currency": "RON", "language": "Romanian", "cities": ("Bucharest", "Cluj-Napoca", "Timișoara", "Iași"), "local": "clinică privată spital servicii tratamente tarife prețuri"},
    "SK": {"name": "Slovakia", "currency": "EUR", "language": "Slovak", "cities": ("Bratislava", "Košice", "Žilina", "Nitra"), "local": "súkromná klinika nemocnica služby cenník"},
    "SI": {"name": "Slovenia", "currency": "EUR", "language": "Slovene", "cities": ("Ljubljana", "Maribor", "Celje", "Koper"), "local": "zasebna klinika bolnišnica storitve cenik"},
    "ES": {"name": "Spain", "currency": "EUR", "language": "Spanish", "cities": ("Madrid", "Barcelona", "Valencia", "Málaga"), "local": "clínica privada hospital tratamientos precios"},
    "SE": {"name": "Sweden", "currency": "SEK", "language": "Swedish", "cities": ("Stockholm", "Gothenburg", "Malmö", "Uppsala"), "local": "privatklinik privatsjukhus behandling priser"},
    "IS": {"name": "Iceland", "currency": "ISK", "language": "Icelandic", "cities": ("Reykjavík", "Kópavogur", "Hafnarfjörður", "Akureyri"), "local": "einkarekin læknastofa sjúkrahús meðferð verðskrá"},
    "LI": {"name": "Liechtenstein", "currency": "CHF", "language": "German", "cities": ("Vaduz", "Schaan", "Balzers", "Triesen"), "local": "Privatklinik Arztpraxis Behandlungen Preise"},
    "NO": {"name": "Norway", "currency": "NOK", "language": "Norwegian", "cities": ("Oslo", "Bergen", "Trondheim", "Stavanger"), "local": "privatklinikk privatsykehus behandling priser"},
}

COUNTRIES = {code: row["name"] for code, row in EEA.items()}
CAMPAIGN_ORDER = (
    "LT", "LV", "EE", "RO",
    "PL", "CZ", "SK", "HU", "BG",
    "DE", "AT", "NL", "BE", "LU", "LI",
    "DK", "FI", "SE", "NO", "IS",
    "ES", "PT", "IT", "GR", "CY", "MT",
    "FR", "IE", "HR", "SI",
)
COUNTRY_BY_SLUG = {
    row["name"].casefold().replace(" ", "-"): code for code, row in EEA.items()
}
COUNTRY_BY_SLUG.update({"czech-republic": "CZ"})

SPECIALTY_SEARCHES = (
    "IV therapy wellness longevity infusion",
    "orthopaedic surgery",
    "diagnostic imaging laboratory",
    "fertility IVF gynaecology",
    "dental clinic implant",
    "dermatology cosmetic surgery",
    "cardiology private hospital",
    "general surgery private hospital",
)


def discovery_queries(code: str) -> list[str]:
    """Return a balanced 15-query discovery pack for one EEA market."""
    row = EEA[code]
    name, local = row["name"], row["local"]
    queries = [
        f"{name} {local} official website",
        f"{name} private hospital clinic treatment services prices official website",
        f"{local} kontakt contact address official",
    ]
    queries.extend(
        f"{city} {local} official clinic website" for city in row["cities"]
    )
    queries.extend(
        f"{name} private {specialty} prices official clinic"
        for specialty in SPECIALTY_SEARCHES
    )
    return list(dict.fromkeys(queries))[:15]


def contact_paths(code: str) -> tuple[str, ...]:
    """Likely contact routes; generic crawling still follows same-domain links."""
    localized = {
        "LT": "kontaktai", "LV": "kontakti", "EE": "kontakt", "RO": "contact",
        "DE": "kontakt", "AT": "kontakt", "LI": "kontakt", "FR": "contact",
        "ES": "contacto", "PT": "contactos", "IT": "contatti", "PL": "kontakt",
        "CZ": "kontakt", "SK": "kontakt", "SI": "kontakt", "HR": "kontakt",
        "HU": "kapcsolat", "NL": "contact", "BE": "contact", "LU": "contact",
        "DK": "kontakt", "SE": "kontakt", "NO": "kontakt", "FI": "yhteystiedot",
        "IS": "hafa-samband", "GR": "epikoinonia", "CY": "epikoinonia",
        "BG": "kontakti", "MT": "contact", "IE": "contact",
    }.get(code, "contact")
    return tuple(
        dict.fromkeys(
            (f"/{localized}/", f"/{localized}", "/contact/", "/locations/")
        )
    )
