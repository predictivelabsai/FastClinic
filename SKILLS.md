# Skills

Capabilities of the FastClinic cockpit and its supporting automation.

## User Guide (slide deck)

User-facing guide on using the cockpit to grow & activate clinic patients —
authored as a landscape **slide deck** (FastClinic branded) with screenshots of
each cockpit screen.

| File | Purpose |
|---|---|
| `docs/fastclinic_user_guide.md` | Source — one slide per `---`, business-focused (grow / activate / sell) |
| `docs/fastclinic_user_guide.pdf` | Built deck — A4 landscape slides |
| `docs/assets/guide.css` | Slide styling (`@page` landscape, blue `#1e6fb8` titles, screenshot float) |
| `docs/img/01..11-*.png` | Per-screen screenshots captured from the cockpit |
| `scripts/build_user_guide.sh` | Rebuild: pandoc (md→HTML) → WeasyPrint (HTML→PDF) |

```bash
bash scripts/build_user_guide.sh      # regenerate docs/fastclinic_user_guide.pdf
```

To refresh screenshots, re-capture the screens via Playwright MCP (login
`admin@fastclinic.example` / `FastClinic2026$`) into `docs/img/`, then rebuild.

## Eval Pack (regression smoke test)

Command-line eval that builds a fresh DB from the committed synthetic export and
runs cases against the command dispatcher, activation engines, AI fallback, and
HTTP routes — to catch regressions with no external services.

| File | Purpose |
|---|---|
| `evals/run_eval.py` | Runner — `python -m evals.run_eval` (writes `eval-results/`) |
| `evals/ground-truth/*.csv` | Ground-truth cases: slash/colon shortcuts, free-form chat, and HTTP route + CSV-export checks |
| `eval-results/latest.json` | Latest run report (per-case pass/fail + summary) |

```bash
python -m evals.run_eval          # full report + failures, exit 1 on any fail
python -m evals.run_eval --quiet  # summary only
```

Shortcuts must resolve locally (no agent fallthrough) and contain expected text;
free-form questions must route to the agent and return a non-empty answer; routes
must return 200 with expected content and no error/`No data loaded` markers.

## Cockpit Dashboard

**Entry:** `.venv/bin/python web_app.py` (port 5005, login: admin@fastclinic.example / FastClinic2026$)

3-pane FastHTML business dashboard: left nav, centre view, right chat/info panel.

### Overview & Analytics

| View | Route | What it shows |
|---|---|---|
| Overview | `/` | KPI cards (active/total patients, visits, revenue, clients), visit & revenue trends, revenue by category, recent activity |
| Patients | `/patients` | Searchable patient register with per-patient drilldown (consultations, diagnoses, spend) |
| Clinical | `/clinical` | Diagnosis patterns (ICD-10-style) and clinician activity |
| Revenue | `/revenue` | Revenue by month and by service category, top services |
| Data & Import | `/admin/data` | SQLite DB status, table row counts, rebuild instructions |

### Activation Engines

**Routes:** `/activation/reminders`, `/activation/lapsed`, `/activation/followup`

The core. Three engines that turn clinic history into outreach lists:
immunisation / health-check reminders (due / overdue), lapsed-patient
reactivation, and post-visit follow-up. Each produces a reviewable list, an
English message draft, and a CSV export (`/activation/{engine}/csv`). No
auto-send.

### SMS Broadcaster

**Route:** `/ops/sms`

SMS interface supporting Twilio and VoodooSMS. Provider selection, phone input,
message textarea with character count. Configured via env vars (`TWILIO_*`,
`VOODOO_SMS_*`).

### Email Broadcaster

**Route:** `/ops/email`

Postmark-backed email sender (`POSTMARK_*`, `EMAIL_REPLY_TO`).

## AI Assistant

### Chat Interface

**Routes:** `/ai` (full page), `/chat/send` (message endpoint), right-rail copilot
on every page.

LangGraph ReAct agent (`graph/clinic_assistant.py`) over read-only clinic-data
tools, with a **configurable model provider** — `MODEL_PROVIDER` =
xai | openai | anthropic | google, `MODEL_NAME` (e.g. `grok-4-1-fast-reasoning`).
xAI/Grok runs through `langchain-openai` against the x.ai base URL. Without a
provider/key it falls back to a slash-command nudge so the cockpit works offline.
System prompt from `prompts/system_prompt.md`.

### Agent Tools

Wrap the cockpit's read-only command functions: `clinic_kpis`, `services_due`,
`lapsed_patients`, `recent_visits`, `revenue_breakdown`, `find_patients`,
`patient_summary`.

### Chat Commands

Typed in the chat panel. Both `/slash` and `colon:` syntax supported.

| Command | Output |
|---|---|
| `/kpi` | Clinic KPIs (active/total patients, visits, revenue, clients) |
| `/due [vaccine\|health_plan\|repeat_prescription]` | Patients due / overdue for a recurring service |
| `/lapsed [months]` | Lapsed patients to win back (default 12) |
| `/followup [days]` | Recent visits to follow up (default 14) |
| `/revenue` | Revenue by category |
| `/patients [search]` | Find patients |
| `/patient ID` | Patient profile + history |
| `/help` | All available commands |

## SEO Audit Module

**Route:** `/seo` (overview), `/seo/{slug}` (component view)

10 core + 5 GEO (Generative Engine Optimization) audit components, each with an editable LLM prompt template (`prompts/seo/<slug>.md`), CSV output (`data/seo/seo_audit_<slug>_YYYY-MM-DD.csv`), and a multi-page crawler that fetches home + up to 7 same-domain pages.

### Core Components

| Component | What it audits |
|---|---|
| Competitive Landscape | Competitor domains, market position, content strength |
| Content Gap Analysis | Topic coverage vs competitors, opportunity level |
| Keyword Reverse-Engineering | Current rankings, difficulty, search intent |
| Local Keywords | High-intent local terms by location |
| Full-Funnel Keyword Map | Keywords by funnel stage and intent |
| Technical Audit | Site health checks (speed, mobile, crawlability) |
| Schema Markup Audit | Structured data presence and quality |
| Internal Linking Audit | Link graph health, orphan pages |
| Page-Level SEO Audit | Title tags, meta descriptions, H1s, image alts |
| Pre-Publish Checklist | Launch readiness checks |

### GEO Components

| Component | What it audits |
|---|---|
| AI Citability | How well pages can be cited by AI search engines |
| AI Crawler Access | Crawler directives and access tiers |
| llms.txt Audit | llms.txt file compliance |
| Brand Mentions | External brand visibility across platforms |
| Platform Readiness | Optimization score per AI platform |

## Accounting Agent

**Script:** `scripts/accounting_agent.py`

A clinic-bookkeeping demonstrator that processes **synthetic** supplier invoices
into a tidy ledger — no real financial data and no live provider logins. Use it
to show how a clinic's back-office bookkeeping could be automated end to end.

## Open-Source Replication

FastClinic is part of the Predictive Labs open-source portfolio. Each repo is an
open demonstrator that exists because a substantive bid used it as capability
evidence; reuse it freely on future tenders of the same shape.

GitHub org: [`github.com/predictivelabsai`](https://github.com/predictivelabsai).

| # | Repo | Licence | Status | Primary capability | Originating context | Re-citable in |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `open-od-toolkit` | MIT | Published | Origin-destination synthesis (gravity + Furness IPF); evidence for mobility / transport-data bids | Devon CC Traffic Journey Time (UK, CP2783-26) | Any UK / EU transport-data, traffic-demand, mobility-modelling tender. |
| 2 | `traffic-data-analysis` | MIT | Published | Floating-car-data / journey-time analytics, anomaly detection on traffic signals | Devon CC; Helsinki Situation Picture (F3) | UK local-authority, Finnish urban-analytics, Nordic transport tenders. |
| 3 | `data-quality-toolkit` | MIT | Published | Profiling + rules-based validation + anomaly detection for DQM | Aarhus DPS (D1), Fintraffic DQM (F2) | Any public-sector DQM / data-governance tender (UK, DK, FI, NL, EE). |
| 4 | `rwd-synth-toolkit` | MIT | Published | Real-world-data cohort construction, survival analysis, IPTW effect estimation, report rendering | Medicinrådet RWD Cancer Plan (D2) | Nordic health RWE / HTA tenders; any EU health-analytics bid mentioning RWD. |
| 5 | `teleradiology-toolkit` | MIT | Published | E027-va serialise/parse, DICOM study-UID + viewer launch, FHIR R4 DiagnosticReport, XAdES-BES signing, ONNX chest X-ray runner | Kauno Klinikos Teleradiology IS (LT) | Any Baltic / Nordic / CE teleradiology or radiology-AI tender. |
| 6 | `openhr` | MIT | Published | Open HR platform — employees, org chart, leave, attendance, payroll, expenses, onboarding. Pure Python FastHTML + HTMX + SQLAlchemy, low-JS footprint | Nye Veier HR-system (NO), Doffin 2026-106565 | Any Nordic / EU public-sector HR tender where auditability and low-JS footprint matter. |
| 7 | `FastClinic` | MIT | Published | Open-source GP-clinic marketing & activation cockpit (FastHTML); patient activation, SEO, broadcasters | Clinic marketing department demonstrator | Primary-care / clinic / patient-engagement / health-marketing tenders. |

### How to cite

In a bid response:

> We maintain `predictivelabsai/<repo>` — an MIT-licensed demonstrator of the
> capabilities required by [section X]. The code, tests, and a worked example are
> publicly hosted on GitHub; the evaluator is welcome to audit.

Three working principles:

1. **Publish before you claim.** A repo that exists before the submission stamps
   is cite-able evidence; a repo we promise to write isn't.
2. **Keep it small and accurate.** 200–500 lines + 10–30 tests beats a
   vapour-large repo.
3. **Apache / MIT only.** Closed-source "demonstrations" defeat the point.

### Maintainer

Predictive Labs Ltd (UK, Companies House 14857334) — `julian@predictivelabs.co.uk`.
