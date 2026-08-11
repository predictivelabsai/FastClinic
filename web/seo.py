"""Search metadata, structured data, sitemap, and crawler policy."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests
import yaml

from fasthtml.common import Link, Meta, NotStr, Script
from starlette.responses import Response

PRODUCT = 'FastClinic'
BASE_URL = 'https://fastclinic.dev'
DESCRIPTION = 'Run appointments, patient operations, billing, recall, revenue, and multi-specialty workflows from one clinical cockpit.'
KEYWORDS = ('FastClinic', 'open source clinic operations', 'clinic operations software', 'SME clinic operations', 'Appointments and availability', 'Patient and treatment operations', 'Billing and balanced ledgers', 'FastSME', 'open source business software')
FEATURES = ('Appointments and availability', 'Patient and treatment operations', 'Billing and balanced ledgers')
SITEMAP_PATHS = ('/', '/developers')

# The dashboard audit backend lives alongside the public search-discovery helpers
# below.  Both were historically in this module and the authenticated routes still
# consume this interface.
ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts" / "seo"
DATA_DIR = ROOT / "data" / "seo"
CONFIG_PATH = PROMPTS_DIR / "_config.yaml"


def _today() -> str:
    return date.today().isoformat()


def load_config() -> list[dict]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["components"]


def component(slug: str) -> dict | None:
    return next((entry for entry in load_config() if entry["slug"] == slug), None)


def prompt_path(slug: str) -> Path:
    return PROMPTS_DIR / f"{slug}.md"


def csv_path(slug: str, run_date: str | None = None) -> Path:
    return DATA_DIR / f"seo_audit_{slug}_{run_date or _today()}.csv"


def latest_csv_path(slug: str) -> Path | None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(DATA_DIR.glob(f"seo_audit_{slug}_*.csv"))
    return candidates[-1] if candidates else None


def _date_from_filename(path: Path) -> str:
    match = re.search(r"_(\d{4}-\d{2}-\d{2})\.", path.name)
    return match.group(1) if match else ""


def read_prompt(slug: str) -> str:
    path = prompt_path(slug)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_prompt(slug: str, text: str) -> None:
    prompt_path(slug).write_text(text, encoding="utf-8")


def load_csv(slug: str) -> tuple[list[str], list[list[str]]]:
    path = latest_csv_path(slug)
    if not path:
        return [], []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        return header, list(reader)


def load_meta(slug: str) -> dict | None:
    path = latest_csv_path(slug)
    if not path:
        return None
    return {"run_date": _date_from_filename(path), "csv_path": str(path.relative_to(ROOT))}


def fetch_site_context(url: str, max_chars: int = 32000, max_pages: int = 8) -> str:
    """Fetch a bounded site excerpt for an audit prompt.

    This deliberately preserves the existing public contract while keeping the
    crawler conservative: same-host links from the landing page, at most
    ``max_pages`` responses, and a hard prompt-size limit.
    """
    from urllib.parse import urldefrag, urljoin, urlparse

    root_host = urlparse(url).netloc.lower().removeprefix("www.")
    queue = [url]
    seen: set[str] = set()
    pages: list[str] = []
    headers = {"User-Agent": "FastClinic-SEO-Audit/1.0"}
    while queue and len(seen) < max_pages:
        current = urldefrag(queue.pop(0))[0]
        if current in seen:
            continue
        seen.add(current)
        try:
            response = requests.get(current, timeout=15, headers=headers, allow_redirects=True)
            if response.status_code >= 400:
                pages.append(f"## {current}\nHTTP {response.status_code}")
                continue
            html = response.text
        except Exception as exc:  # noqa: BLE001 - audit reports fetch failures as context
            pages.append(f"## {current}\nFetch error: {exc}")
            continue
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"<[^>]+>", " ", title_match.group(1)).strip() if title_match else ""
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
        pages.append(f"## {current}\nTitle: {title}\nBody: {body[:3500]}")
        for href in re.findall(r'<a[^>]+href=["\']([^"\']+)', html, re.I):
            target = urldefrag(urljoin(current, href))[0]
            if urlparse(target).netloc.lower().removeprefix("www.") == root_host and target not in seen:
                queue.append(target)
    return "\n\n".join(pages)[:max_chars]


def run_component(slug: str, site_url: str, site_content: str,
                  model: str = "gpt-4o-mini") -> dict[str, Any]:
    comp = component(slug)
    if not comp:
        return {"ok": False, "error": f"Unknown component {slug}"}
    prompt_template = read_prompt(slug)
    if not prompt_template:
        return {"ok": False, "error": f"Missing prompt for {slug}"}
    prompt = prompt_template.replace("{{site_url}}", site_url).replace(
        "{{site_content}}", site_content)
    started = time.time()
    try:
        from openai import OpenAI
        response = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid CSV using the requested headers."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"^```(?:csv)?\s*\n|\n```\s*$", "", raw.strip(), flags=re.M).strip()
        parsed = list(csv.reader(io.StringIO(raw)))
        if not parsed:
            raise ValueError("empty CSV")
        header, rows = parsed[0], [row for row in parsed[1:] if any(cell.strip() for cell in row)]
    except Exception as exc:  # noqa: BLE001 - returned to the audit workflow
        return {"ok": False, "error": str(exc), "seconds": time.time() - started}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = csv_path(slug)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return {"ok": True, "rows": rows, "header": header,
            "seconds": round(time.time() - started, 2), "model": model,
            "csv_path": str(path.relative_to(ROOT)), "run_date": _today()}


def overview_rows() -> list[dict]:
    rows = []
    for entry in load_config():
        _, body = load_csv(entry["slug"])
        latest = latest_csv_path(entry["slug"])
        rows.append({**entry, "rows": len(body),
                     "run_date": _date_from_filename(latest) if latest else "",
                     "has_data": bool(body)})
    return rows


def seo_meta(
    *,
    path: str = "/",
    title: str | None = None,
    description: str | None = None,
):
    canonical = BASE_URL + (path if path != "/" else "")
    page_title = title or f"{PRODUCT} · Open-source {KEYWORDS[2].title()}"
    page_description = description or DESCRIPTION
    structured = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": PRODUCT,
        "url": canonical,
        "description": page_description,
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web",
        "isAccessibleForFree": True,
        "license": "https://opensource.org/license/mit",
        "featureList": list(FEATURES),
        "publisher": {
            "@type": "Organization",
            "name": "FastSME",
            "url": "https://fastsme.com",
        },
    }
    return (
        Link(rel="canonical", href=canonical),
        Meta(name="robots", content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"),
        Meta(name="keywords", content=", ".join(KEYWORDS)),
        Meta(property="og:type", content="website"),
        Meta(property="og:site_name", content="FastSME"),
        Meta(property="og:title", content=page_title),
        Meta(property="og:description", content=page_description),
        Meta(property="og:url", content=canonical),
        Meta(name="twitter:card", content="summary"),
        Meta(name="twitter:title", content=page_title),
        Meta(name="twitter:description", content=page_description),
        Script(NotStr(json.dumps(structured, separators=(",", ":"))), type="application/ld+json"),
    )


async def sitemap():
    urls = "\n".join(
        f'  <url><loc>{BASE_URL}{path}</loc><changefreq>{"weekly" if path == "/" else "monthly"}</changefreq><priority>{"1.0" if path == "/" else "0.6"}</priority></url>'
        for path in SITEMAP_PATHS
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
    return Response(xml, media_type="application/xml")


async def robots():
    body = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /app
Disallow: /auth/
Disallow: /login
Disallow: /register
Disallow: /api/

Sitemap: {BASE_URL}/sitemap.xml
"""
    return Response(body, media_type="text/plain")


def register_seo_routes(app):
    paths = {getattr(route, "path", None) for route in app.routes}
    if "/sitemap.xml" not in paths:
        app.route("/sitemap.xml", methods=["GET"])(sitemap)
        app.routes.insert(0, app.routes.pop())
    if "/robots.txt" not in paths:
        app.route("/robots.txt", methods=["GET"])(robots)
        app.routes.insert(0, app.routes.pop())
