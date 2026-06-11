"""Render SEO audit screens — index, per-component, prompt editor."""
from __future__ import annotations

import os

from fasthtml.common import (
    Div, H1, H3, H4, P, Span, A, Form, Input, Button, Table, Thead, Tbody, Tr, Th, Td,
    Textarea, Label, NotStr,
)

from web import seo

# Site to audit — overridable via env (matches web_app's SEO_SITE).
SEO_SITE = os.getenv("FASTCLINIC_SEO_SITE", "https://fastclinic.example")
SEO_SITE_LABEL = SEO_SITE.replace("https://", "").replace("http://", "").rstrip("/")


# ---------- nav items consumed by layout ----------
def nav_items() -> list[tuple[str, str, str, str]]:
    """Return (key, label, icon, href) entries for the left-nav drilldowns."""
    return [(c["slug"], c["title"], c["icon"], f"/seo/{c['slug']}") for c in seo.load_config()]


# ---------- index ----------
def index_view(default_url: str = SEO_SITE):
    rows = seo.overview_rows()
    data_rows = []
    for r in rows:
        status = (Span("✓ data", cls="status-pill completed") if r["has_data"]
                  else Span("no data", cls="status-pill pending"))
        data_rows.append(Tr(
            Td(Span(r["icon"], style="margin-right:6px;"),
               A(r["title"], href=f"/seo/{r['slug']}")),
            Td(status),
            Td(f"{r['rows']:,}" if r["rows"] else "—"),
            Td(r.get("run_date") or "—", style="font-size:12px;"),
            Td(A("Run", href=f"/seo/{r['slug']}/run-confirm", cls="btn primary",
                 style="padding:3px 8px;font-size:11px;"),
               " ",
               A("Prompt", href=f"/seo/{r['slug']}/prompt", cls="btn",
                 style="padding:3px 8px;font-size:11px;")),
        ))

    return Div(
        Div(
            Div(H1("SEO Audit"),
                Div("Editable prompts + LLM-driven audits for " + SEO_SITE_LABEL,
                    cls="sub")),
            cls="page-title",
        ),
        Div(
            Div(H3("Run full audit suite"), cls="card-header"),
            Form(
                Div(
                    Label("Site URL: ", style="font-size:12px; color:var(--text-dim);"),
                    Input(type="url", name="site_url", value=default_url,
                          style="flex:1; padding:6px 10px; border:1px solid var(--border); border-radius:6px;"),
                    Button("Run all 10", cls="btn primary", type="submit"),
                    style="display:flex; gap:10px; align-items:center;",
                ),
                method="post", action="/seo/run-all",
            ),
            P(NotStr("Audits call OpenAI (<code>gpt-4o-mini</code>). Outputs persist to "
                     "<code>data/seo/seo_audit_&lt;slug&gt;_&lt;YYYY-MM-DD&gt;.csv</code>; "
                     "re-running on the same day overwrites, new days add new files."),
              style="color:var(--text-mute); font-size:12px; margin:8px 0 0;"),
            cls="card",
        ),
        Div(
            Div(H3("Audit Components"), cls="card-header"),
            Table(
                Thead(Tr(Th("Component"), Th("Status"), Th("Rows"),
                         Th("Run date"), Th("Actions"))),
                Tbody(*data_rows),
                cls="tbl",
            ),
            cls="card",
        ),
    )


# ---------- per-component ----------
def component_view(slug: str):
    comp = seo.component(slug)
    if not comp:
        return Div(H1("Not Found"), P(f"Unknown component: {slug}"))

    header, rows = seo.load_csv(slug)
    meta = seo.load_meta(slug) or {}

    meta_bar = Div(
        Span(f"Rows: {len(rows)}", style="margin-right:16px;") if rows else
            Span("No data yet.", style="color:var(--text-mute);"),
        Span(f"Run date: {meta.get('run_date', '—')}", style="color:var(--text-mute);")
            if meta.get("run_date") else None,
        style="font-size:12px; margin-bottom:8px;",
    )

    if not rows:
        table = Div(
            P("No audit data yet for this component.",
              style="color:var(--text-mute); padding:16px 0;"),
        )
    else:
        table = Table(
            Thead(Tr(*[Th(h.replace("_", " ").title()) for h in header])),
            Tbody(*[Tr(*[Td(_cell(c)) for c in r]) for r in rows]),
            cls="tbl",
        )

    # Run form + nav to prompt editor
    actions = Form(
        Input(type="url", name="site_url",
              value=SEO_SITE,
              style="flex:1; padding:6px 10px; border:1px solid var(--border); border-radius:6px;"),
        Button("Run audit", cls="btn primary", type="submit"),
        A("Edit prompt", href=f"/seo/{slug}/prompt", cls="btn",
          style="text-decoration:none;"),
        A("Download CSV", href=f"/seo/{slug}/csv", cls="btn",
          style="text-decoration:none;") if rows else None,
        A("Download XLS", href=f"/seo/{slug}/xlsx", cls="btn primary",
          style="text-decoration:none;") if rows else None,
        method="post", action=f"/seo/{slug}/run",
        style="display:flex; gap:10px; align-items:center;",
    )

    return Div(
        Div(
            Div(H1(f"{comp['icon']} {comp['title']}"),
                Div(meta.get("site_url", ""), cls="sub") if meta.get("site_url") else None),
            cls="page-title",
        ),
        Div(Div(H3("Run"), cls="card-header"), actions, cls="card"),
        Div(Div(H3("Results"), cls="card-header"), meta_bar, table, cls="card"),
    )


def _cell(value: str):
    """Render a CSV cell with small styling for score-like or status-like values."""
    v = (value or "").strip()
    low = v.lower()
    if low in ("yes", "pass", "good", "excellent", "high"):
        return Span(v, cls="status-pill completed")
    if low in ("no", "fail", "poor", "missing"):
        return Span(v, cls="status-pill cancelled")
    if low in ("partial", "warn", "ok", "fair", "medium", "pending"):
        return Span(v, cls="status-pill pending")
    return v


# ---------- prompt editor ----------
def prompt_editor_view(slug: str, saved: bool = False):
    comp = seo.component(slug)
    if not comp:
        return Div(H1("Not Found"))
    prompt_text = seo.read_prompt(slug)

    return Div(
        Div(
            Div(H1(f"Prompt — {comp['title']}"),
                Div(f"prompts/seo/{slug}.md · placeholders: {{site_url}}, {{site_content}}",
                    cls="sub")),
            cls="page-title",
        ),
        Div("✓ Saved.", cls="status-pill completed",
            style="margin-bottom:10px; padding:4px 10px;") if saved else None,
        Div(
            Div(H3("Edit prompt template"),
                A("← Back to audit", href=f"/seo/{slug}", cls="btn",
                  style="padding:4px 10px;font-size:12px;"),
                cls="card-header"),
            Form(
                Textarea(prompt_text, name="prompt", rows=24,
                         style="width:100%; font-family:ui-monospace,monospace; "
                               "font-size:12px; padding:12px; border:1px solid var(--border); "
                               "border-radius:6px; resize:vertical;"),
                Div(
                    Button("Save", cls="btn primary", type="submit"),
                    A("Cancel", href=f"/seo/{slug}", cls="btn"),
                    style="margin-top:10px; display:flex; gap:8px;",
                ),
                method="post", action=f"/seo/{slug}/prompt",
            ),
            cls="card",
        ),
    )


# ---------- run-confirm (shows spinner + auto-submits) ----------
def run_confirm_view(slug: str, site_url: str | None = None):
    comp = seo.component(slug)
    url = site_url or SEO_SITE
    return Div(
        Div(Div(H1(f"Running — {comp['title']}"),
                Div("Fetching site + calling LLM…", cls="sub")),
            cls="page-title"),
        Div(
            P(Span(cls="spinner"), f" Auditing {url}"),
            NotStr(f"""
<form id='runfrm' method='post' action='/seo/{slug}/run'>
  <input type='hidden' name='site_url' value='{url}'>
</form>
<script>document.getElementById('runfrm').submit();</script>
"""),
            cls="card",
        ),
    )
