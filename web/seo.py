"""SEO Audit module — editable prompts, multi-page crawler, LLM runner, CSV persistence.

File layout:
    prompts/seo/_config.yaml                          — component registry
    prompts/seo/<slug>.md                             — editable prompt template per component
    data/seo/seo_audit_<slug>_<YYYY-MM-DD>.csv        — structured output (dated)

Re-running on the same day overwrites that day's file; a new day creates a new
dated file, preserving history. Loaders always return the most recent dated file.

The prompt template uses `{{site_url}}` and `{{site_content}}` placeholders.
`{{site_content}}` is assembled from a **multi-page crawl** of the site: home +
up to 8 discovered same-domain pages. Each page contributes title, meta, headings,
a body excerpt, and its outbound links, so the LLM can do real per-page auditing
rather than guessing from one homepage.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts" / "seo"
DATA_DIR = ROOT / "data" / "seo"
CONFIG_PATH = PROMPTS_DIR / "_config.yaml"


def _today() -> str:
    return date.today().isoformat()  # YYYY-MM-DD


def load_config() -> list[dict]:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)["components"]


def component(slug: str) -> dict | None:
    for c in load_config():
        if c["slug"] == slug:
            return c
    return None


def prompt_path(slug: str) -> Path:
    return PROMPTS_DIR / f"{slug}.md"


def csv_path(slug: str, run_date: str | None = None) -> Path:
    """Write path for a given run date (defaults to today)."""
    return DATA_DIR / f"seo_audit_{slug}_{run_date or _today()}.csv"


def latest_csv_path(slug: str) -> Path | None:
    """Most recent dated CSV for a component, or None if none exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(DATA_DIR.glob(f"seo_audit_{slug}_*.csv"))
    return candidates[-1] if candidates else None


def _date_from_filename(p: Path) -> str:
    """Extract YYYY-MM-DD suffix from filename, or empty string."""
    m = re.search(r"_(\d{4}-\d{2}-\d{2})\.", p.name)
    return m.group(1) if m else ""


def read_prompt(slug: str) -> str:
    p = prompt_path(slug)
    return p.read_text() if p.exists() else ""


def write_prompt(slug: str, text: str) -> None:
    prompt_path(slug).write_text(text)


def load_csv(slug: str) -> tuple[list[str], list[list[str]]]:
    """Load most recent dated CSV. Returns (header, rows) or ([], []) if none."""
    p = latest_csv_path(slug)
    if not p:
        return [], []
    with open(p, newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        rows = list(reader)
    return header, rows


def load_meta(slug: str) -> dict | None:
    """Return minimal metadata derived from the latest CSV filename."""
    p = latest_csv_path(slug)
    if not p:
        return None
    return {"run_date": _date_from_filename(p), "csv_path": str(p.relative_to(ROOT))}


# ------------------------- site fetching -------------------------
from urllib.parse import urljoin, urlparse, urldefrag

DEFAULT_SEED_PATHS = [
    "/", "/faq", "/about", "/contact",
    "/book", "/services", "/services/health-check",
    "/services/private-gp", "/services/flu-jab",
    "/clinics", "/blog", "/pricing",
]

UA = "Mozilla/5.0 (compatible; FastClinic-SEO-Audit/1.0)"


def _http_get(url: str, timeout: int = 15) -> str | None:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA},
                         allow_redirects=True)
        if r.status_code >= 400:
            return None
        return r.text
    except Exception:
        return None


def _strip_tags(html: str) -> str:
    try:
        from markdownify import markdownify as md
        return re.sub(r"\n{3,}", "\n\n", md(html, heading_style="ATX")).strip()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _extract_page_info(url: str, html: str) -> dict:
    """Parse a single page's HTML into a structured dict for the LLM."""
    info: dict = {"url": url}

    # title
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    info["title"] = (m.group(1).strip() if m else "")

    # meta description / robots / canonical
    info["meta_description"] = ""
    info["meta_robots"] = ""
    info["canonical"] = ""
    info["og_tags"] = []
    for tag in re.findall(r"<meta\s+[^>]+>", html, re.I):
        nm = re.search(r'name=["\']([^"\']+)["\']', tag, re.I)
        pr = re.search(r'property=["\']([^"\']+)["\']', tag, re.I)
        cv = re.search(r'content=["\']([^"\']*)["\']', tag, re.I)
        content = cv.group(1) if cv else ""
        if nm:
            n = nm.group(1).lower()
            if n == "description":
                info["meta_description"] = content
            elif n == "robots":
                info["meta_robots"] = content
        if pr and pr.group(1).lower().startswith(("og:", "twitter:")):
            info["og_tags"].append(f"{pr.group(1)}={content}")
    mcan = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
                     html, re.I)
    if mcan:
        info["canonical"] = mcan.group(1)

    # headings
    info["h1"] = [re.sub(r"<[^>]+>", "", h).strip()[:140]
                  for h in re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)]
    info["h2"] = [re.sub(r"<[^>]+>", "", h).strip()[:140]
                  for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.I | re.S)][:12]

    # images + alt coverage
    imgs = re.findall(r"<img\s[^>]*>", html, re.I)
    info["img_count"] = len(imgs)
    info["img_with_alt"] = sum(1 for i in imgs if re.search(r'\balt=', i, re.I))

    # ld+json blocks
    info["ld_json"] = [b.strip()[:1500] for b in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.I | re.S)]

    # outbound links (dedup)
    base = url
    links: list[str] = []
    seen = set()
    for href in re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.I):
        href = urldefrag(href)[0].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base, href)
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    info["links"] = links

    # body excerpt (markdown)
    body = _strip_tags(html)
    info["body_excerpt"] = body[:2200]
    return info


def _same_domain(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.lower().lstrip("www.") == \
               urlparse(b).netloc.lower().lstrip("www.")
    except Exception:
        return False


def fetch_site_files(root_url: str) -> dict:
    """Fetch `/robots.txt`, `/llms.txt`, `/sitemap.xml` — used by GEO audits
    that need to see what AI crawlers see. Returns a dict keyed by filename."""
    out: dict[str, dict] = {}
    for name in ("robots.txt", "llms.txt", "sitemap.xml"):
        u = urljoin(root_url, f"/{name}")
        try:
            r = requests.get(u, timeout=10, headers={"User-Agent": UA},
                             allow_redirects=True)
            if r.status_code < 400:
                # Cap at 6k chars — enough to read; keeps prompt lean
                body = r.text
                truncated = len(body) > 6000
                out[name] = {"url": u, "status": r.status_code,
                             "body": body[:6000], "truncated": truncated}
            else:
                out[name] = {"url": u, "status": r.status_code,
                             "body": "", "truncated": False}
        except Exception as e:
            out[name] = {"url": u, "status": 0, "error": str(e)[:120]}
    return out


def crawl_site(root_url: str, max_pages: int = 8) -> list[dict]:
    """Fetch the root page + up to N-1 discovered same-domain pages.
    Returns a list of structured page dicts (from _extract_page_info)."""
    pages: list[dict] = []
    seen: set[str] = set()

    # Always start with the root
    html = _http_get(root_url)
    if html is None:
        return [{"url": root_url, "error": "fetch failed"}]
    root_info = _extract_page_info(root_url, html)
    pages.append(root_info)
    seen.add(root_url.rstrip("/"))

    # Priority queue: seed paths (if they exist as links), then discovered links
    candidates: list[str] = []
    link_set = {urljoin(root_url, l) for l in root_info["links"]}
    for path in DEFAULT_SEED_PATHS:
        u = urljoin(root_url, path)
        if u in link_set or path in ("/faq", "/about", "/contact"):
            candidates.append(u)
    for l in root_info["links"]:
        if l not in candidates:
            candidates.append(l)

    for u in candidates:
        if len(pages) >= max_pages:
            break
        if u.rstrip("/") in seen:
            continue
        if not _same_domain(root_url, u):
            continue
        # skip static/media
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|webp|ico|css|js|zip)(?:\?|$)", u, re.I):
            continue
        html = _http_get(u)
        if html is None:
            continue
        pages.append(_extract_page_info(u, html))
        seen.add(u.rstrip("/"))

    return pages


def _format_site_files(files: dict) -> str:
    """Render robots.txt / llms.txt / sitemap.xml excerpts for the prompt."""
    lines: list[str] = ["# SITE FILES (for GEO / AI-crawler audits)"]
    for name, info in files.items():
        lines.append(f"\n## /{name}")
        if info.get("error"):
            lines.append(f"(fetch error: {info['error']})")
            continue
        status = info.get("status", 0)
        lines.append(f"HTTP {status}")
        if status >= 400 or not info.get("body"):
            lines.append("(not present or empty)")
            continue
        lines.append("```")
        lines.append(info["body"])
        if info.get("truncated"):
            lines.append("…(truncated)…")
        lines.append("```")
    return "\n".join(lines)


def _format_pages_for_prompt(pages: list[dict], max_chars: int = 26000,
                             site_files: dict | None = None) -> str:
    """Render a list of page dicts as a structured string for the LLM.
    If `site_files` is provided, prepend robots.txt / llms.txt / sitemap excerpts."""
    out: list[str] = []
    if site_files:
        out.append(_format_site_files(site_files))
        out.append("")  # blank line
    for i, p in enumerate(pages, 1):
        if "error" in p:
            out.append(f"## PAGE {i}: {p['url']}\n(fetch error: {p['error']})")
            continue
        alt_cov = ("—" if p["img_count"] == 0
                   else f"{p['img_with_alt']}/{p['img_count']}")
        lines = [
            f"## PAGE {i}: {p['url']}",
            f"- TITLE: {p['title']}",
            f"- META DESCRIPTION: {p['meta_description']}",
            f"- META ROBOTS: {p['meta_robots'] or '(none)'}",
            f"- CANONICAL: {p['canonical'] or '(none)'}",
            f"- H1: {' | '.join(p['h1']) if p['h1'] else '(none)'}",
            f"- H2: {' | '.join(p['h2']) if p['h2'] else '(none)'}",
            f"- IMAGES with alt: {alt_cov}",
            f"- OG/TW TAGS: {', '.join(p['og_tags'][:6]) if p['og_tags'] else '(none)'}",
        ]
        if p["ld_json"]:
            lines.append("- LD+JSON BLOCKS:")
            for j, ld in enumerate(p["ld_json"][:3], 1):
                lines.append(f"  [{j}] {ld[:600].strip()}")
        lines.append("- OUTBOUND LINKS (first 20):")
        for l in p["links"][:20]:
            lines.append(f"  - {l}")
        lines.append("- BODY EXCERPT:")
        lines.append(p["body_excerpt"])
        out.append("\n".join(lines))
    combined = "\n\n".join(out)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n…(truncated)…"
    return combined


def fetch_site_context(url: str, max_chars: int = 32000, max_pages: int = 8) -> str:
    """Public entrypoint: crawl + fetch site files + format for prompt injection."""
    pages = crawl_site(url, max_pages=max_pages)
    files = fetch_site_files(url)
    return _format_pages_for_prompt(pages, max_chars=max_chars, site_files=files)


# ------------------------- LLM runner -------------------------
def run_component(slug: str, site_url: str, site_content: str,
                  model: str = "gpt-4o-mini") -> dict[str, Any]:
    """Call the LLM with the component's prompt, parse CSV, persist outputs.
    Returns a result dict: {ok, rows, error, seconds, model, csv_path}."""
    comp = component(slug)
    if not comp:
        return {"ok": False, "error": f"Unknown component {slug}"}

    prompt_tpl = read_prompt(slug)
    if not prompt_tpl:
        return {"ok": False, "error": f"Missing prompt for {slug}"}

    t0 = time.time()
    prompt = prompt_tpl.replace("{{site_url}}", site_url).replace(
        "{{site_content}}", site_content
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content":
                 "You are a senior SEO analyst. Return ONLY valid CSV in your response — "
                 "no markdown, no prose, no code fences. Use the exact header columns "
                 "specified in the prompt."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        return {"ok": False, "error": f"LLM call failed: {e}", "seconds": time.time() - t0}

    # Strip code fences if the model ignored instructions
    raw_clean = re.sub(r"^```(?:csv)?\s*\n|\n```\s*$", "", raw.strip(), flags=re.M).strip()

    # Parse CSV
    try:
        reader = csv.reader(io.StringIO(raw_clean))
        rows = list(reader)
        if not rows:
            raise ValueError("empty CSV")
        header = [h.strip() for h in rows[0]]
        body = [r for r in rows[1:] if any(c.strip() for c in r)]
    except Exception as e:
        return {"ok": False, "error": f"CSV parse failed: {e}",
                "seconds": time.time() - t0, "raw": raw[:500]}

    # Persist — only the CSV, dated; same-day re-runs overwrite
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = _today()
    csv_p = csv_path(slug, run_date)
    with open(csv_p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    seconds = round(time.time() - t0, 2)
    return {"ok": True, "rows": body, "header": header, "seconds": seconds,
            "model": model, "csv_path": str(csv_p.relative_to(ROOT)),
            "run_date": run_date}


# ------------------------- view helpers -------------------------
def overview_rows() -> list[dict]:
    """Summary row per component for the SEO Audit landing page."""
    out = []
    for c in load_config():
        header, body = load_csv(c["slug"])
        latest = latest_csv_path(c["slug"])
        out.append({
            **c,
            "rows": len(body),
            "run_date": _date_from_filename(latest) if latest else "",
            "has_data": bool(body),
        })
    return out
