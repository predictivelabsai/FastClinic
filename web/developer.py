"""Public and in-app developer documentation for FastClinic."""
from fasthtml.common import *

from .api import API_GROUPS, RESOURCES
from .i18n import t
from .landing import FAVICON, LANGUAGE_JS, language_switcher
from .seo import seo_meta

ACCENT = "#1e6fb8"
TINT = "#eef7ff"
BASE_URL = "https://fastclinic.dev"
REPOSITORY = "https://github.com/predictivelabsai/FastClinic"

DEVELOPER_CSS = """
.dev-docs{--dev-accent:#1e6fb8;--dev-tint:#eef7ff;--dev-ink:#111827;--dev-muted:#667085;--dev-line:#e7eaf0;color:var(--dev-ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}
.dev-docs *{box-sizing:border-box} .dev-wrap{max-width:1120px;margin:auto;padding:56px 24px 80px}
.dev-eyebrow{color:var(--dev-accent);font-size:12px;font-weight:750;text-transform:uppercase;letter-spacing:.16em}
.dev-docs h1{font-size:clamp(40px,6vw,68px);line-height:1.02;letter-spacing:-.05em;max-width:850px;margin:18px 0}
.dev-lede{font-size:19px;line-height:1.65;color:var(--dev-muted);max-width:760px}
.dev-actions{display:flex;gap:10px;flex-wrap:wrap;margin:28px 0 46px} .dev-btn{display:inline-flex;padding:10px 16px;border-radius:999px;text-decoration:none;font-size:14px;font-weight:700;border:1px solid var(--dev-line);color:var(--dev-ink);background:white} .dev-btn.primary{background:var(--dev-accent);color:white;border-color:var(--dev-accent)}
.dev-note{background:var(--dev-tint);border:1px solid color-mix(in srgb,var(--dev-accent) 18%,white);border-radius:18px;padding:20px 22px;line-height:1.6;margin-bottom:42px} .dev-note strong{color:var(--dev-accent)}
.dev-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:18px 0 46px} .dev-card{background:white;border:1px solid var(--dev-line);border-radius:18px;padding:22px;box-shadow:0 8px 24px rgba(17,24,39,.04)} .dev-card h2{font-size:19px;margin:0 0 8px} .dev-card p{color:var(--dev-muted);line-height:1.55;min-height:48px} .dev-route{display:block;background:#111827;color:#f8fafc;padding:9px 11px;border-radius:8px;margin-top:8px;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:auto} .dev-method{color:#86efac;font-weight:800}
.dev-capability{margin:18px 0 30px}.dev-capability-head{display:grid;grid-template-columns:220px 1fr;gap:24px;margin-bottom:12px}.dev-capability-head h3{margin:0;font-size:21px}.dev-capability-head p{margin:0;color:var(--dev-muted);line-height:1.55}.dev-op-list{border:1px solid var(--dev-line);border-radius:16px;overflow:hidden;background:#fff}.dev-op{display:grid;grid-template-columns:150px minmax(250px,1fr) 1.2fr 170px;gap:14px;align-items:center;padding:14px 16px;border-bottom:1px solid var(--dev-line)}.dev-op:last-child{border-bottom:0}.dev-methods{display:flex;gap:4px;flex-wrap:wrap}.dev-method-chip{padding:4px 6px;border-radius:6px;background:#e8f5ee;color:#14734a;font:700 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace}.dev-op code{font-size:12px;color:var(--dev-ink);overflow-wrap:anywhere}.dev-op-desc{font-size:13px;color:var(--dev-muted);line-height:1.45}.dev-access{font-size:11px;font-weight:700;color:var(--dev-accent)}
.dev-example{background:#111827;color:#e5e7eb;border-radius:16px;padding:22px;overflow:auto;font:13px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace} .dev-docs h3{font-size:24px;margin:42px 0 14px} .dev-small{color:var(--dev-muted);font-size:13px;line-height:1.6}
.dev-public-nav{height:68px;display:flex;align-items:center;justify-content:space-between;max-width:1120px;margin:auto;padding:0 24px;border-bottom:1px solid var(--dev-line)} .dev-brand{display:flex;align-items:center;gap:10px;color:var(--dev-ink);text-decoration:none;font-weight:750} .dev-diamond{width:28px;height:28px;border-radius:8px;background:var(--dev-accent);transform:rotate(45deg);display:inline-block}.dev-nav-actions{display:flex;align-items:center;gap:10px}
.lp-lang{position:relative}.lp-lang-trigger{border:1px solid transparent;border-radius:6px;padding:4px 7px;font-size:16px;line-height:1;background:transparent;cursor:pointer}.lp-lang-trigger:hover{border-color:var(--dev-line)}.lp-lang-trigger:focus{outline:2px solid color-mix(in srgb,var(--dev-accent) 30%,white)}.lp-lang-menu{display:none;position:absolute;right:0;top:calc(100% + 7px);z-index:60;min-width:142px;padding:4px 0;background:#fff;border:1px solid var(--dev-line);border-radius:10px;box-shadow:0 18px 45px rgba(17,24,39,.14)}.lp-lang-menu.open{display:block}.lp-lang-item{display:flex;align-items:center;gap:9px;padding:7px 12px;color:var(--dev-muted);font-size:12px;text-decoration:none}.lp-lang-item:hover,.lp-lang-item:focus{background:var(--dev-tint);color:var(--dev-ink);outline:0}.lp-lang-item.active{background:var(--dev-tint);color:var(--dev-ink);font-weight:700}.lp-lang-flag{font-size:16px;line-height:1}
@media(max-width:850px){.dev-op{grid-template-columns:1fr}.dev-capability-head{grid-template-columns:1fr;gap:6px}.dev-grid{grid-template-columns:1fr}.dev-docs h1{font-size:42px}}
@media(max-width:600px){.dev-public-nav{height:auto;min-height:68px;flex-wrap:wrap;gap:8px;padding:10px 18px}.dev-nav-actions{width:100%;gap:6px}.dev-nav-actions .dev-btn{padding:8px 12px;font-size:12px}.dev-wrap{padding:56px 24px 72px}}
"""


def developer_content(lang="en"):
    T = lambda text: t(text, lang)
    cards = []
    for resource in RESOURCES:
        cards.append(
            Article(
                H2(T(resource.title)),
                P(T(resource.description)),
                Code(Span("GET", cls="dev-method"), f" /api/v1/{resource.slug}", cls="dev-route"),
                Code(Span("GET", cls="dev-method"), f" /api/v1/{resource.slug}/{{id}}", cls="dev-route"),
                cls="dev-card",
            )
        )
    return Div(
        Style(DEVELOPER_CSS),
        Div(
            Span(T("Developer platform · API v1"), cls="dev-eyebrow"),
            H1(T("Build with the FastClinic API.")),
            P(T("Explore the live synthetic demo through a typed, versioned API with public reads and token-gated operations."), cls="dev-lede"),
            Div(
                A(T("Open Swagger UI"), href="/api/docs", cls="dev-btn primary"),
                A(T("Open ReDoc"), href="/api/redoc", cls="dev-btn"),
                A(T("Download swagger.json"), href="/swagger.json", cls="dev-btn"),
                A(T("View on GitHub"), href=REPOSITORY, target="_blank", rel="noreferrer", cls="dev-btn"),
                cls="dev-actions",
            ),
            Div(
                Strong(T("Public preview access.") + " "),
                T("Synthetic clinical and aggregate GET endpoints require no authentication. Operational reads and all writes require FASTSME_API_TOKEN; they return 503 when it is not configured. Enabled clients send"),
                " ", Code("Authorization: Bearer <token>."),
                cls="dev-note",
            ),
            H3(T("Complete API surface")),
            *[
                Section(
                    Div(H3(T(title)), P(T(description)), cls="dev-capability-head"),
                    Div(*[
                        Div(
                            Div(*[Span(method, cls="dev-method-chip") for method in methods.split()], cls="dev-methods"),
                            Code(path),
                            Span(T(summary), cls="dev-op-desc"),
                            Span(T(access), cls="dev-access"),
                            cls="dev-op",
                        )
                        for methods, path, summary, access in operations
                    ], cls="dev-op-list"),
                    cls="dev-capability",
                )
                for title, description, operations in API_GROUPS
            ],
            H3(T("Clinical read resources")),
            Div(*cards, cls="dev-grid"),
            H3(T("Quick start")),
            Pre(Code(f"""# Public synthetic read
curl "{BASE_URL}/api/v1/{RESOURCES[0].slug}?limit=20"

# Token-authenticated, idempotent payment
curl -X POST "{BASE_URL}/api/v1/payments" \\
  -H "Authorization: Bearer $FASTSME_API_TOKEN" \\
  -H "Idempotency-Key: payment-your-stable-id" \\
  -H "Content-Type: application/json" \\
  -d '{{"invoice_id": 7001, "amount": 25.00, "method": "card"}}'"""), cls="dev-example"),
            P(T("DELETE is domain-aware: patients and notes are archived, appointments and reminders are cancelled, invoices are voided with reversing journals, and payments are refunded. Communication and ledger records remain immutable."), cls="dev-note"),
            P(T("Runtime OpenAPI: /api/openapi.json · Stable compatibility schema: /swagger.json · Interactive docs: /api/docs"), cls="dev-small"),
            cls="dev-wrap",
        ),
        cls="dev-docs",
    )


def developer_page(lang="en"):
    T = lambda text: t(text, lang)
    description = T("Build integrations with the public FastClinic API, OpenAPI schemas, examples, and token-gated writes.")
    return Html(
        Head(
            Title(T("FastClinic Developers · FastSME")),
            Meta(charset="utf-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Meta(name="description", content=T("Developer API documentation for FastClinic.")),
            *seo_meta(
                path="/developers",
                title=T("FastClinic Developer API · FastSME"),
                description=description,
            ),
            Link(rel="icon", type="image/svg+xml", href=FAVICON),
            Link(rel="preconnect", href="https://fonts.googleapis.com"),
            Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;750&display=swap"),
        ),
        Body(
            Nav(
                A(Span(cls="dev-diamond"), Span("FastClinic Developers"), href="/developers", cls="dev-brand"),
                Div(A(T("Compliance"), href="/compliance", cls="dev-btn"), language_switcher(lang, "/developers"), A(T("Back to product"), href="/", cls="dev-btn"), cls="dev-nav-actions"),
                cls="dev-public-nav dev-docs",
            ),
            developer_content(lang),
            Script(LANGUAGE_JS),
            style="margin:0;background:#fff",
        ),
        lang=lang,
    )
