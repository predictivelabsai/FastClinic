# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**FastClinic** — an open-source FastHTML **GP / general-practice marketing &
activation cockpit**. It turns a primary-care clinic's own visit history into
prioritised patient-outreach lists. Goal: **maximise patient activation** — bring
patients back for immunisations, annual health-check renewals, lapsed-patient
win-backs, and post-visit follow-ups.

Clinical palette: primary blue `#1e6fb8`, dark `#1b2733`, accent green `#1f9d72`.
Tagline *"Modern primary care, made personal."* Port **5005**.

The FastHTML shell (auth, 3-pane layout, AI chat, SEO module, SMS) is reused
across the portfolio; the domain layer here is general practice. **All data is
synthetic — there is no real patient data (PHI) anywhere in the repo.**

## Commands

```bash
# Create a virtualenv and install deps
python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt

.venv/bin/python -m pms.synth             # write data/synthetic_fastclinic.xlsx (default 1000 patients)
.venv/bin/python -m pms.importer          # build fastclinic.sqlite from newest data/*.xlsx
.venv/bin/python -m pms.importer data/synthetic_fastclinic.xlsx fastclinic.sqlite   # explicit
.venv/bin/python web_app.py               # cockpit on :5005
# Login: admin@fastclinic.example / FastClinic2026$  (override via FASTCLINIC_ADMIN_* env)

.venv/bin/python -m evals.run_eval        # regression smoke test (see Testing)
.venv/bin/python -m evals.run_eval --quiet
bash scripts/build_user_guide.sh          # rebuild docs/fastclinic_user_guide.pdf (pandoc + weasyprint)

docker compose up -d                      # containerised (mounts /data volume)
```

No linter/formatter configured. `fasthtml.md` (repo root) is the FastHTML
best-practices reference; `docs/FASTHTML_AUDIT.md` records audit findings.

## Architecture

### Data layer — synthetic PMS export → local SQLite (`pms/`, `web/db.py`)

- **`pms/synth.py`** — generates `data/synthetic_fastclinic.xlsx`, a fully
  synthetic, structurally realistic GP PMS export (people, consultations,
  diagnoses, notes, billable line items). No real PHI.
- The PMS export is a multi-sheet `.xlsx`: **patient**, **diagnosis**, **note**,
  **item** (billable lines), plus an optional **client** contacts sheet, linked
  by `consultation_id` / `patient_id` / `client_id`.
- **`pms/xlsx.py`** — dependency-free OOXML reader (stdlib `zipfile` +
  `ElementTree`). Cells are keyed by their `r=` reference (e.g. `C2`) — empty
  cells are omitted, so never index positionally.
- **`pms/catalog.py`** — keyword rules that classify each line item
  (`vaccine` → "Immunisation", `health_plan` → "Health check / care plan",
  `repeat_prescription`, `consultation`, `lab`, `imaging`, `procedure`,
  `medication`, `referral`) and define recurring re-visit intervals in days
  (vaccine / health_plan 365, repeat_prescription 60). Edit here to extend the
  catalogue.
- **`pms/importer.py`** — builds `fastclinic.sqlite`: tables `patient`,
  `diagnosis`, `note`, `item`, plus derived `consultation` (one row per visit:
  date, revenue, is_visit) and `client` (one row per patient's contact record).
  Column mapping is **declarative** (`(col, xlsx_key, sql_type, converter)`
  tuples) so raw tables are a 1:1 replica of the export; `evals` asserts 100%
  field coverage. The model column for the supervising clinician is
  `clinician_id` (xlsx key `supervising_clinician_id`). Idempotent — re-run to
  refresh.
- **`web/db.py`** — **read-only** SQLite access (`query`, `query_one`,
  `scalar`). `reference_date()` is "today" for due/lapsed maths (latest activity
  date, or `FASTCLINIC_TODAY`). DB path is `FASTCLINIC_DB` or `./fastclinic.sqlite`.

The person is modelled as a single entity: `patient` is the person, `client` is
the same person's 1:1 contact record (`patient.client_id`). Human demographic
fields only (gender, date of birth, NHS number, blood group, insurance).

### Cockpit (`web_app.py`, `web/`)

- **`web_app.py`** — routes + session auth (single shared admin login via env).
  `_ensure_db()` auto-builds the DB on boot if missing and a `data/*.xlsx` is
  present. Most route handlers are named `get`/`post` — FastHTML registers them
  by the `@rt("/path")` decorator, not the function name.
- **`web/layout.py`** — 3-pane grid, `LAYOUT_CSS` (FastClinic palette),
  `NAV_ITEMS` (Overview · Activation · Clinic · Marketing · Help · Admin), and
  the right-rail **Copilot** (chat). The copilot can minimise / expand; a small
  amount of `LAYOUT_JS` drives this. **fast_app already bundles htmx** — don't
  add a second `<script src=htmx>` in `page()`.
- **`web/clinic_queries.py`** — read-only dashboard queries (overview KPIs,
  trends, patients, clinical). Includes `clinician_activity()` and
  `demographics_mix()` (gender distribution: keys `label`, `n`).
- **`web/dashboards.py`** — server-rendered FastHTML views (Plotly for charts
  only): Overview, Patients + drilldown, Clinical, Revenue, Data & Import,
  SMS + Email broadcasters, AI page, System Prompt.
- **`web/activation.py`** — **the core.** Three engines + English message drafts
  + CSV export, no auto-send: `reminders` (due/overdue recurring services),
  `lapsed` (no visit in N months), `followup` (recent visits). Lists include
  name/phone for the SMS/Email broadcasters; `campaign_csv()` backs
  `/activation/{engine}/csv`.
- **`web/commands.py`** — slash-command dispatcher for the chat (`/kpi /due
  /lapsed /followup /revenue /patients /patient ID /help`, also `cmd:` colon
  syntax). Natural-language help phrases short-circuit here without an LLM call.
  Non-command messages fall through to the AI assistant.
- **`web/help_views.py`** — Help section: `/help/shortcuts` (the slash-command
  reference, `SHORTCUTS` is the single source of truth) and `/help/guide` (web
  render of `docs/fastclinic_user_guide.md`; images + PDF served statically from
  `docs/`).
- **`web/seo.py`** + **`web/seo_views.py`** — LLM SEO/GEO-audit suite, targeted at
  `FASTCLINIC_SEO_SITE`. Prompts in `prompts/seo/`, outputs `data/seo/`.
- **`web/exports.py`**, **`web/sse.py`** — CSV exports and server-sent-event
  streaming helpers.

### AI assistant (`graph/clinic_assistant.py`)

- Free-form chat (non-slash) calls `clinic_assistant.answer()`: a **LangGraph
  ReAct agent** over read-only clinic-data tools, with a configurable model
  provider — `MODEL_PROVIDER` (xai | openai | anthropic | google), `MODEL_NAME`.
  xAI/Grok runs through `langchain-openai` against the x.ai base URL. With no
  provider/key it falls back to a slash-command nudge (so evals/offline still
  work). System prompt: `prompts/system_prompt.md`.

### Accounting agent (`scripts/accounting_agent.py`)

- A clinic-bookkeeping demonstrator that processes **synthetic** supplier
  invoices. No real financial data, no live provider logins.

## Environment

All config in `.env` (see `.env.sample`). Core:
`FASTCLINIC_ADMIN_EMAIL/PASSWORD`, `FASTCLINIC_SECRET`, `FASTCLINIC_PORT`,
`FASTCLINIC_DB`, `FASTCLINIC_TODAY`, `FASTCLINIC_SEO_SITE`. AI assistant:
`MODEL_PROVIDER` (xai|openai|anthropic|google), `MODEL_NAME`, and the matching
key (`XAI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`).
SMS: `TWILIO_*`, `VOODOO_SMS_*`. Email: `POSTMARK_API_TOKEN`, `POSTMARK_FROM`,
`EMAIL_REPLY_TO`. Load via python-dotenv (values with spaces break naive
`source .env`).

## Deployment

- `Dockerfile` (python:3.12-slim, port 5005). `.dockerignore` excludes ad-hoc
  exports but **keeps `data/synthetic_fastclinic.xlsx`** so the deployed image
  ships demo data; `_ensure_db()` builds the SQLite on first boot.
- `docker-compose.yml` mounts a `fastclinic-data` volume at `/data` with
  `FASTCLINIC_DB=/data/fastclinic.sqlite` so the database lives outside the image
  (build it in-container with
  `python -m pms.importer /data/export.xlsx /data/fastclinic.sqlite`).
- The cockpit shows a graceful "No data loaded" screen until a DB exists.

## Testing

- **Eval pack** (`evals/run_eval.py`, ground truth in `evals/ground-truth/*.csv`)
  is the regression gate: builds a fresh DB from `synthetic_fastclinic.xlsx`,
  then runs shortcut/chat/route suites + a field-coverage check. It runs
  **offline** — the AI chat suite only checks for a non-empty answer, so the
  no-key fallback passes. Writes JSON to `eval-results/`.
- **UI**: drive with Playwright MCP (`browser_navigate`, `browser_take_screenshot`).
  Prefer server-rendered FastHTML over client JS.
