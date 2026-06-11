"""3-pane cockpit layout, CSS, and shared components."""
from __future__ import annotations

from fasthtml.common import (
    Div, H1, H2, H3, H4, P, Span, A, Button, Form, Input, Label,
    Script, Style, Link, Table, Thead, Tbody, Tr, Th, Td, Title,
    NotStr, Nav, Aside, Main, Section, Ul, Li, Strong,
)


# ---------- palette ----------
LAYOUT_CSS = """
:root {
  --bg: #f4f8f8;
  --surface: #ffffff;
  --surface-2: #eef4f4;
  --border: #dbe6e6;
  --text: #1b2733;
  --text-dim: #525a61;
  --text-mute: #93a1a1;
  --accent: #1e6fb8;          /* FastClinic primary blue */
  --accent-hover: #185a96;
  --accent-light: #dceaf6;
  --warn: #1f9d72;            /* FastClinic accent green */
  --danger: #dc2626;
  --ok: #1f9d72;
}
* { box-sizing: border-box; }
html, body { margin:0; padding:0; height:100%; background:var(--bg); color:var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; font-size:14px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

.app {
  display: grid;
  grid-template-columns: 240px 1fr var(--rail, 340px);
  grid-template-rows: 52px 1fr;
  grid-template-areas: "top top top" "left center right";
  height: 100vh; overflow: hidden;
  transition: grid-template-columns .18s ease;
}
.app.right-expanded { --rail: clamp(420px, 42vw, 720px); }
.app.right-collapsed { --rail: 0px; }
.app.right-collapsed .right-pane { display: none; }
#copilot-reopen {
  position: fixed; right: 0; bottom: 26px; display: none;
  align-items: center; gap: 6px; cursor: pointer; z-index: 60;
  background: var(--accent); color: #fff; font-size: 13px; font-weight: 600;
  padding: 9px 14px; border-radius: 8px 0 0 8px; box-shadow: 0 2px 10px rgba(0,0,0,.18);
}
.app.right-collapsed #copilot-reopen { display: inline-flex; }
.copilot-min, .copilot-exp {
  cursor: pointer; border: 1px solid var(--border); background: var(--surface);
  border-radius: 6px; padding: 4px 9px; font-size: 13px; line-height: 1; color: var(--text-mute);
}
.copilot-min:hover, .copilot-exp:hover { background: var(--surface-2); color: var(--accent); }

/* top bar */
.topbar {
  grid-area: top;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; background: var(--surface); border-bottom: 1px solid var(--border);
}
.brand { font-weight: 700; letter-spacing: 0.3px; display: flex; align-items: center; gap: 8px; }
.brand-dot { width: 10px; height: 10px; background: var(--accent); border-radius: 50%; display: inline-block; }
.topbar .env-pill {
  background: var(--accent-light); color: var(--accent-hover);
  padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.topbar .actions { display: flex; gap: 10px; align-items: center; }

/* left nav */
.left-pane {
  grid-area: left;
  background: var(--surface); border-right: 1px solid var(--border);
  padding: 12px 0; overflow-y: auto;
}
.nav-section { margin-bottom: 14px; }
.nav-section h4 {
  margin: 6px 16px 4px; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.8px; color: var(--text-mute); font-weight: 700;
}
.nav-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 16px; color: var(--text-dim); cursor: pointer;
  border-left: 3px solid transparent;
}
.nav-item:hover { background: var(--surface-2); color: var(--text); text-decoration: none; }
.nav-item.active { background: var(--accent-light); color: var(--accent-hover);
  border-left-color: var(--accent); font-weight: 600; }
.nav-icon { width: 18px; display: inline-block; text-align: center; }

/* center */
.center-pane {
  grid-area: center; overflow-y: auto; padding: 20px 24px;
}
.page-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title h1 { margin: 0; font-size: 22px; font-weight: 700; }
.page-title .sub { color: var(--text-mute); font-size: 13px; margin-top: 3px; }

/* cards */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.kpi {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 16px; position: relative; overflow: hidden;
}
.kpi .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px;
  color: var(--text-mute); font-weight: 600; }
.kpi .value { font-size: 26px; font-weight: 700; margin-top: 4px; color: var(--text); }
.kpi .trend { font-size: 12px; color: var(--ok); margin-top: 2px; }
.kpi .trend.neg { color: var(--danger); }
.kpi::after {
  content: ''; position: absolute; top: 0; right: 0; bottom: 0; width: 4px;
  background: var(--accent);
}
.kpi.warn::after { background: var(--warn); }
.kpi.neutral::after { background: var(--text-mute); }

.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px 18px; margin-bottom: 16px;
}
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-header h3 { margin: 0; font-size: 15px; font-weight: 700; }

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

/* tables */
table.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
table.tbl th { text-align: left; padding: 8px 10px; background: var(--surface-2);
  color: var(--text-dim); font-weight: 600; border-bottom: 1px solid var(--border); }
table.tbl td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
table.tbl tr:last-child td { border-bottom: 0; }
table.tbl tr:hover td { background: var(--surface-2); }
.status-pill {
  display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600;
  background: var(--surface-2); color: var(--text-dim);
}
.status-pill.new { background: #dbeafe; color: #1d4ed8; }
.status-pill.initial-paid, .status-pill.diag-submitted { background: #fef3c7; color: #92400e; }
.status-pill.diag-approved, .status-pill.final-paid { background: #d1fae5; color: #065f46; }
.status-pill.completed { background: var(--accent-light); color: var(--accent-hover); }
.status-pill.cancelled, .status-pill.expired { background: #fee2e2; color: #991b1b; }
.status-pill.neutral { background: #eef2f2; color: #5a6a6a; }
.callout {
  background: #f1f7f7; border: 1px solid #cfe5e5; border-left: 4px solid var(--accent);
  color: #2c4a4a; padding: 12px 16px; border-radius: 8px; margin-bottom: 18px;
  font-size: 13px; line-height: 1.55;
}
.status-pill.pending { background: #fef3c7; color: #92400e; }
.status-pill.contacted { background: #dbeafe; color: #1d4ed8; }
.status-pill.overdue { background: #fee2e2; color: #991b1b; }
.status-pill.due-soon { background: #ffedd5; color: #9a3412; }
.status-pill.lapsed { background: #fee2e2; color: #991b1b; }
.status-pill.ok, .status-pill.active { background: var(--accent-light); color: var(--accent-hover); }
.status-pill.vaccine { background: #dbeafe; color: #1d4ed8; }
.status-pill.health_plan { background: #dcfce7; color: #166534; }
.status-pill.repeat_prescription { background: #f3e8ff; color: #6b21a8; }

/* activation list rows */
.act-row { display:grid; grid-template-columns: 1fr auto; gap:8px; align-items:center;
  padding:10px 12px; border:1px solid var(--border); border-radius:8px; margin-bottom:8px; background:var(--surface); }
.act-row .muted { color: var(--text-mute); font-size:12px; }
.msg-draft { background: var(--surface-2); border:1px dashed var(--border); border-radius:8px;
  padding:10px 12px; font-size:13px; line-height:1.5; white-space:pre-wrap; margin-top:6px; }
.seg { display:inline-flex; gap:6px; margin-bottom:14px; flex-wrap:wrap; }
.seg a { padding:6px 12px; border:1px solid var(--border); border-radius:8px; color:var(--text-dim);
  background:var(--surface); font-size:13px; }
.seg a.active { background:var(--accent); color:#fff; border-color:var(--accent); }

/* right pane */
.right-pane {
  grid-area: right; background: var(--surface); border-left: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.right-header {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.right-header h3 { margin: 0; font-size: 14px; font-weight: 700; }
.right-header .tabs { display: flex; gap: 6px; }
.tab-btn {
  padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface);
}
.tab-btn.active { background: var(--accent); color: white; border-color: var(--accent); }

/* chat */
.chat-body {
  flex: 1; overflow-y: auto; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 12px;
}
.msg { max-width: 88%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.55;
  overflow-wrap: anywhere; word-break: break-word; }
.msg.user { background: var(--accent); color: white; align-self: flex-end; border-bottom-right-radius: 3px; white-space: pre-wrap; }
.msg.assistant { background: var(--surface); border: 1px solid var(--border); color: var(--text); align-self: flex-start; border-bottom-left-radius: 3px; max-width: 94%; }
.msg.system { background: #fef3c7; color: #92400e; align-self: stretch; font-style: italic; font-size: 12px; }
.msg .md > :first-child { margin-top: 0; }
.msg .md > :last-child { margin-bottom: 0; }
.msg code { background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; overflow-wrap: anywhere; }
.msg pre { background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-size: 12px; margin: 4px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.msg pre code { background: none; }
.msg strong { color: var(--accent-hover); }
.msg h1, .msg h2, .msg h3 { margin: 8px 0 3px; font-weight: 600; }
.msg h2 { font-size: 15px; } .msg h3 { font-size: 14px; }
.msg p { margin: 4px 0; }
.msg ul, .msg ol { margin: 4px 0; padding-left: 20px; }
/* chat tables: wrap into the rail width, never scroll horizontally */
.msg table { width: 100%; table-layout: fixed; font-size: 11.5px; border-collapse: collapse;
  border: 1px solid var(--border); border-radius: 6px; margin: 6px 0; }
.msg table th { background: var(--text); color: white; font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.02em; }
.msg table th, .msg table td { text-align: left; padding: 5px 7px; border: 1px solid var(--border);
  overflow-wrap: anywhere; word-break: break-word; vertical-align: top; }
.msg table tbody tr:nth-child(even) td { background: var(--surface-2); }
.msg table tbody tr:hover td { background: var(--accent-light); }

.chat-input {
  border-top: 1px solid var(--border); padding: 10px; background: var(--surface);
}
.chat-input-row { display: flex; gap: 8px; align-items: stretch; }
.chat-input-row input { flex: 1; min-width: 0; padding: 10px 12px; border: 1px solid var(--border);
  border-radius: 8px; font-size: 13px; outline: none; }
.chat-input-row input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }
.chat-send-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--accent);
  color: #fff; border: none; border-radius: 8px; padding: 0 16px; font-weight: 600; font-size: 13px;
  cursor: pointer; white-space: nowrap; }
.chat-send-btn:hover { background: var(--accent-hover); }
.chat-send-btn:disabled { background: var(--text-mute); cursor: not-allowed; }
.chat-empty-hint { color: var(--text-mute); font-size: 12.5px; line-height: 1.5; text-align: center;
  padding: 18px 14px; }
/* streaming thinking indicator + tool trace */
.thinking-indicator { display: flex; align-items: center; gap: 8px; padding: 6px 14px;
  font-size: 12.5px; color: var(--text-mute); align-self: flex-start; }
.thinking-indicator .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent);
  animation: pulse 1.2s ease-in-out infinite; }
.thinking-indicator .secs { opacity: .65; }
@keyframes pulse { 0%,100% { opacity:.35; transform:scale(.85); } 50% { opacity:1; transform:scale(1.1); } }
.tool-trace { display: flex; flex-wrap: wrap; gap: 6px; align-self: flex-start; margin: 0 0 2px; padding: 0 4px; }
.tool-chip { font-size: 11px; color: var(--accent-hover); background: var(--accent-light);
  border: 1px solid var(--border); border-radius: 999px; padding: 2px 9px; }
.chat-input textarea {
  width: 100%; resize: none; border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; font-family: inherit; font-size: 13px; outline: none; min-height: 52px;
}
.chat-input textarea:focus { border-color: var(--accent); }
.chat-hint { font-size: 11px; color: var(--text-mute); margin-top: 4px; }
.chat-hint code { background: var(--surface-2); padding: 1px 5px; border-radius: 3px; }

/* buttons */
.btn {
  padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); cursor: pointer; font-size: 13px;
}
.btn:hover { background: var(--surface-2); }
.btn.primary { background: var(--accent); color: white; border-color: var(--accent); }
.btn.primary:hover { background: var(--accent-hover); }

/* login */
.login-wrap {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #e8f1fa 0%, #dceaf6 100%);
}
.login-card {
  background: white; padding: 36px 40px; border-radius: 14px; width: 360px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
}
.login-card h1 { margin: 0 0 4px; font-size: 22px; }
.login-card p { margin: 0 0 20px; color: var(--text-mute); font-size: 13px; }
.login-card input {
  width: 100%; padding: 10px 12px; border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: 10px; font-size: 14px;
}
.login-card button { width: 100%; padding: 10px; font-weight: 600; }
.login-card .error { color: var(--danger); font-size: 12px; margin: 6px 0; }

/* command palette (chat hints) */
.cmd-chip {
  display: inline-block; padding: 3px 10px; margin: 2px; font-size: 11px;
  background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
  cursor: pointer; color: var(--text-dim);
  font-family: ui-monospace, 'SFMono-Regular', monospace; transition: all .15s;
}
.cmd-chip:hover { background: var(--accent-light); color: var(--accent-hover); border-color: var(--accent); }

/* sample cards (pehero-style prompt chips below chat input) */
.sample-cards { padding: .5rem 1rem .8rem; background: var(--surface); border-top: 1px solid var(--border); }
.sample-cards-label { display: inline-block; font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .12em; color: var(--text-mute); margin-bottom: 6px; }
.sample-cards-row { display: flex; flex-direction: column; gap: 6px; }
.sample-card {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg); border: 1px solid var(--border);
  padding: 9px 12px; border-radius: 10px; font-size: 12.5px;
  font-family: inherit; cursor: pointer; color: var(--text-dim);
  width: 100%; text-align: left; line-height: 1.35; transition: all .15s;
}
.sample-card::before { content: "💬"; font-size: 13px; flex-shrink: 0; }
.sample-card:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
.shortcut-hint { margin-top: 8px; text-align: center; }
.shortcut-hint-btn {
  background: none; border: none; color: var(--text-mute); font-size: 11px; cursor: pointer;
  padding: 2px 4px; text-decoration: underline dotted;
}
.shortcut-hint-btn:hover { color: var(--accent); }

/* chat action buttons (copy, share) */
.chat-action-btn {
  padding: 4px 10px; background: transparent; border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-dim); font-size: 12px; cursor: pointer;
  transition: all .15s;
}
.chat-action-btn:hover { border-color: var(--accent); color: var(--accent); }

/* welcome hero (empty-state suggestions) */
.welcome-hero { text-align: center; padding: 24px 16px 16px; }
.welcome-head { margin-bottom: 16px; }
.welcome-title { font-size: 16px; font-weight: 700; margin: 0 0 4px; }
.welcome-sub { font-size: 12px; color: var(--text-mute); margin: 0; }
.suggestions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
.suggestion-chip {
  display: flex; align-items: center; gap: 6px;
  background: var(--surface-2); border: 1px solid var(--border);
  padding: 6px 12px; border-radius: 10px; font-size: 12px;
  cursor: pointer; color: var(--text-dim); font-family: inherit;
  max-width: 260px; text-align: left;
}
.suggestion-chip:hover { border-color: var(--accent); color: var(--accent-hover); background: var(--accent-light); }
.sugg-icon { font-size: 14px; flex-shrink: 0; }
.sugg-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* table toolbar (CSV copy/download) */
.table-toolbar { display: flex; gap: .35rem; justify-content: flex-end; margin-bottom: .25rem; }
.table-action-btn {
  padding: 2px 8px; font-size: 11px; color: var(--accent);
  background: var(--accent-light); border: 1px solid var(--border);
  border-radius: 4px; cursor: pointer; font-family: inherit;
}
.table-action-btn:hover { background: var(--accent); color: white; border-color: var(--accent); }

/* plotly */
.plot { width: 100%; height: 280px; }
.spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* treatment calculator */
.calc-form { display:flex; flex-direction:column; gap:14px; padding:16px; }
.calc-form label { display:block; font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:.5px; color:var(--text-mute); margin-bottom:4px; }
.calc-form select {
  width:100%; padding:10px 12px; border:1px solid var(--border); border-radius:8px;
  font-size:14px; background:var(--surface); color:var(--text); cursor:pointer;
  appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23475569' fill='none' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat:no-repeat; background-position:right 12px center;
}
.calc-form select:focus { border-color:var(--accent); outline:none; box-shadow:0 0 0 3px var(--accent-light); }
.calc-form select:disabled { background:var(--surface-2); color:var(--text-mute); cursor:not-allowed; }

.calc-result { margin-top:16px; }
.calc-result .kpi-grid { grid-template-columns:repeat(4,1fr); }
.calc-saving {
  background:var(--accent-light); border:2px solid var(--accent); border-radius:10px;
  padding:20px; text-align:center; margin-top:16px;
}
.calc-saving .pct { font-size:36px; font-weight:800; color:var(--accent-hover); }
.calc-saving .lbl { font-size:13px; color:var(--text-dim); margin-top:4px; }
.calc-cta {
  display:block; width:100%; text-align:center; padding:12px 0;
  background:var(--accent); color:white; border-radius:8px;
  font-weight:600; font-size:14px; margin-top:16px; border:none; cursor:pointer;
  text-decoration:none;
}
.calc-cta:hover { background:var(--accent-hover); color:white; }
.calc-note { font-size:12px; color:var(--text-mute); margin-top:8px; line-height:1.5; }

@media (max-width:900px) { .calc-result .kpi-grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width:640px) { .calc-result .kpi-grid { grid-template-columns:1fr; } }

/* sms broadcaster */
.sms-form { display:flex; flex-direction:column; gap:14px; padding:16px; max-width:560px; }
.sms-form label { display:block; font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:.5px; color:var(--text-mute); margin-bottom:4px; }
.sms-form input, .sms-form textarea, .sms-form select {
  width:100%; padding:10px 12px; border:1px solid var(--border); border-radius:8px;
  font-size:14px; background:var(--surface); color:var(--text); font-family:inherit;
}
.sms-form textarea { min-height:100px; resize:vertical; }
.sms-form input:focus, .sms-form textarea:focus, .sms-form select:focus {
  border-color:var(--accent); outline:none; box-shadow:0 0 0 3px var(--accent-light);
}
.sms-form select {
  appearance:none; cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23475569' fill='none' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat:no-repeat; background-position:right 12px center;
}
.sms-send { display:inline-flex; align-items:center; gap:6px; padding:10px 24px;
  background:var(--accent); color:white; border:none; border-radius:8px;
  font-weight:600; font-size:14px; cursor:pointer; }
.sms-send:hover { background:var(--accent-hover); }
.sms-send:disabled { background:var(--text-mute); cursor:not-allowed; }
.sms-result { margin-top:12px; padding:12px 16px; border-radius:8px; font-size:13px; }
.sms-result.success { background:#d1fae5; color:#065f46; border:1px solid #a7f3d0; }
.sms-result.error { background:#fee2e2; color:#991b1b; border:1px solid #fecaca; }
.sms-char-count { font-size:11px; color:var(--text-mute); text-align:right; margin-top:2px; }

/* web user guide (markdown rendered to HTML) */
.guide-doc { max-width: 860px; line-height: 1.6; color: var(--text); }
.guide-doc h1 { color: var(--accent); font-size: 26px; margin: 4px 0 2px; }
.guide-doc h2 { color: var(--text); font-size: 19px; margin: 26px 0 8px;
  border-bottom: 2px solid var(--accent-light); padding-bottom: 4px; }
.guide-doc h3 { font-size: 15px; margin: 18px 0 6px; }
.guide-doc p { margin: 8px 0; }
.guide-doc img { max-width: 100%; height: auto; border: 1px solid var(--border);
  border-radius: 8px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.guide-doc hr { border: 0; border-top: 1px dashed var(--border); margin: 28px 0; }
.guide-doc blockquote { margin: 12px 0; padding: 8px 14px; border-left: 4px solid var(--accent);
  background: var(--surface-2); color: var(--text-dim); border-radius: 0 8px 8px 0; }
.guide-doc ul, .guide-doc ol { padding-left: 22px; }
.guide-doc li { margin: 4px 0; }
.guide-doc code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
.guide-doc table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin: 10px 0; }
.guide-doc th { background: var(--surface-2); text-align: left; padding: 6px 9px; border: 1px solid var(--border); }
.guide-doc td { padding: 6px 9px; border: 1px solid var(--border); vertical-align: top; }
"""


def _read_version() -> str:
    from pathlib import Path
    p = Path(__file__).parent.parent / "VERSION"
    try:
        return p.read_text().strip()
    except Exception:
        return ""


def topbar(env: str, user_email: str | None):
    ver = _read_version()
    right = Div(
        Button(NotStr("&laquo; Chat"), id="copilot-topbar-toggle", cls="btn copilot-toggle",
               onclick="toggleCopilot()", title="Show / hide the AI assistant") if user_email else None,
        Span(env, cls="env-pill"),
        Span(user_email or "", style="color:var(--text-mute); font-size:12px;") if user_email else None,
        A("Logout", href="/logout", cls="btn") if user_email else None,
        cls="actions",
    )
    return Div(
        Div(Span(cls="brand-dot"),
            Span("Fast", style="font-weight:800;"),
            Span("Clinic", style="color:var(--accent); font-weight:700; letter-spacing:1px; margin-left:2px;"),
            Span(ver, style="color:var(--text-mute); font-size:10px; font-family:ui-monospace,monospace; margin-left:6px;") if ver else None,
            cls="brand"),
        right,
        cls="topbar",
    )


NAV_ITEMS = [
    ("OVERVIEW", [
        ("dashboard", "Overview", "📊", "/"),
        ("chat-full", "AI Assistant", "🤖", "/ai"),
    ]),
    ("ACTIVATION", [
        ("act-reminders", "Immunisation & Plan Due", "💉", "/activation/reminders"),
        ("act-lapsed", "Lapsed Reactivation", "🔁", "/activation/lapsed"),
        ("act-followup", "Post-Visit Follow-up", "📨", "/activation/followup"),
    ]),
    ("CLINIC", [
        ("patients", "Patients", "🧑‍⚕️", "/patients"),
        ("clinical", "Clinical", "🩺", "/clinical"),
        ("revenue", "Revenue", "💶", "/revenue"),
    ]),
    ("MARKETING", [
        ("sms", "SMS Broadcaster", "📱", "/ops/sms"),
        ("email", "Email Broadcaster", "✉️", "/ops/email"),
        ("seo", "SEO Audit", "🔍", "/seo"),
    ]),
    ("HELP", [
        ("help-shortcuts", "Shortcuts", "⌨️", "/help/shortcuts"),
        ("help-guide", "User Guide", "📖", "/help/guide"),
    ]),
    ("ADMIN", [
        ("data-admin", "Data & Import", "🗂️", "/admin/data"),
        ("prompt", "System Prompt", "📝", "/ai/prompt"),
    ]),
]


def _seo_subnav() -> list[tuple[str, str, str, str]]:
    """Append SEO component drilldowns dynamically so layout stays decoupled."""
    try:
        from web.seo_views import nav_items
        return nav_items()
    except Exception:
        return []


def left_pane(active: str):
    sections = []
    for section_name, items in NAV_ITEMS:
        links = [
            A(
                Span(icon, cls="nav-icon"), Span(label),
                href=href,
                cls=f"nav-item {'active' if active == key else ''}",
            )
            for key, label, icon, href in items
        ]
        # Append SEO drilldowns under the SEO AUDIT section
        if section_name == "SEO AUDIT":
            for key, label, icon, href in _seo_subnav():
                links.append(A(
                    Span(icon, cls="nav-icon"),
                    Span(label, style="font-size:12px;"),
                    href=href,
                    cls=f"nav-item {'active' if active == key else ''}",
                    style="padding-left:26px;",  # indent drilldowns
                ))
        sections.append(Div(H4(section_name), *links, cls="nav-section"))
    return Div(*sections, cls="left-pane")


# Conversational starters shown below the chat — most people start by chatting.
SAMPLE_QUESTIONS = [
    "Which patients are overdue for immunisations?",
    "Who should we win back this month?",
    "How is the clinic performing?",
]


def _sample_cards():
    """Free-form example questions below the chat input. Shortcuts live in /help."""
    cards = [
        Button(
            Span(q, cls="sample-card-text"),
            cls="sample-card",
            onclick=f"fillChat({q!r}); sendMessage(null);",
            title=q,
        )
        for q in SAMPLE_QUESTIONS
    ]
    return Div(
        Div(Span("Try asking:", cls="sample-cards-label"), id="sample-cards-label"),
        Div(*cards, id="sample-cards-row", cls="sample-cards-row"),
        Div(
            A("⌘ Shortcuts for power users", href="/help/shortcuts", cls="shortcut-hint-btn",
              title="Open the shortcuts guide"),
            cls="shortcut-hint",
        ),
        id="sample-cards",
        cls="sample-cards",
    )


def right_pane_chat(thread_id: str):
    """Always-visible chat cockpit in the right rail."""
    return Div(
        Div(
            H3("AI Assistant"),
            Div(
                Button("New", cls="btn", hx_get=f"/chat/new", hx_target="#chat-body",
                       hx_swap="innerHTML", title="Start new thread"),
                Button(NotStr("&laquo;"), id="copilot-exp-btn", cls="copilot-exp",
                       onclick="toggleExpand()", title="Expand / shrink assistant"),
                Button(NotStr("&rsaquo;"), cls="copilot-min", onclick="toggleCopilot()",
                       title="Minimise assistant"),
                cls="tabs",
            ),
            cls="right-header",
        ),
        Div(
            Div(
                P("Ask about patients, immunisations due, revenue — or tap a question below.",
                  cls="chat-empty-hint"),
                id="chat-body", cls="chat-body",
            ),
            Form(
                Input(type="hidden", name="thread_id", value=thread_id, id="thread-id"),
                Div(
                    Input(
                        type="text", name="message", id="chat-input",
                        placeholder="Ask a question or type /due /lapsed /help …",
                        autocomplete="off",
                    ),
                    Button("Send", type="submit", cls="chat-send-btn", id="chat-send-btn"),
                    cls="chat-input-row",
                ),
                onsubmit="return streamChat(event)",
                cls="chat-input",
            ),
            _sample_cards(),
            style="display:flex; flex-direction:column; flex:1; overflow:hidden;",
        ),
        cls="right-pane",
    )


def right_pane_reference():
    """Static reference panel for the AI Assistant page (replaces chat in the right rail)."""
    return Div(
        Div(
            H3("How to Use"),
            cls="right-header",
        ),
        Div(
            Div(
                Div(H3("Getting Started"), cls="card-header"),
                P("The AI Assistant can help you in two primary ways:"),
                NotStr(
                    "<ul style='margin:6px 0 12px; padding-left:20px; font-size:13px; line-height:1.6;'>"
                    "<li><strong>Ask free-form questions</strong> — ask about patients, immunisations, "
                    "diagnoses, revenue, or activation opportunities in plain language.</li>"
                    "<li><strong>Shortcut commands</strong> — type a slash command for instant cockpit "
                    "data pulled straight from the clinic database.</li>"
                    "</ul>"
                ),
                cls="card", style="margin:0 12px 12px;",
            ),
            Div(
                Div(H3("Example Questions"), cls="card-header"),
                NotStr(
                    "<ul style='margin:4px 0; padding-left:20px; font-size:13px; line-height:1.7; color:var(--text-dim);'>"
                    "<li>Which patients are overdue for their flu immunisation?</li>"
                    "<li>Who hasn't visited in over 12 months?</li>"
                    "<li>What was revenue last quarter by category?</li>"
                    "<li>Show the visit history for patient 117753</li>"
                    "<li>How many patients are on an annual care plan?</li>"
                    "</ul>"
                ),
                cls="card", style="margin:0 12px 12px;",
            ),
            Div(
                Div(H3("Shortcuts"), cls="card-header"),
                NotStr("""
<table class='tbl' style='font-size:12px;'>
<thead><tr><th>Command</th><th>Effect</th></tr></thead>
<tbody>
<tr><td><code>/kpi</code></td><td>Clinic KPIs</td></tr>
<tr><td><code>/due</code></td><td>Immunisations &amp; plans due / overdue</td></tr>
<tr><td><code>/lapsed [months]</code></td><td>Lapsed clients to win back</td></tr>
<tr><td><code>/followup [days]</code></td><td>Recent visits to follow up</td></tr>
<tr><td><code>/revenue</code></td><td>Revenue by category</td></tr>
<tr><td><code>/patients [search]</code></td><td>Find patients</td></tr>
<tr><td><code>/patient ID</code></td><td>Patient summary</td></tr>
<tr><td><code>/help</code></td><td>Show command list</td></tr>
</tbody></table>"""),
                cls="card", style="margin:0 12px;",
            ),
            style="overflow-y:auto; flex:1; padding-top:12px;",
        ),
        cls="right-pane",
    )


LAYOUT_JS = """
function _syncCopilotBtns(){
  var app=document.querySelector('.app'); if(!app) return;
  var ex=app.classList.contains('right-expanded');
  var collapsed=app.classList.contains('right-collapsed');
  var eb=document.getElementById('copilot-exp-btn');
  if(eb){ eb.innerHTML = ex ? '\\u00BB' : '\\u00AB'; eb.title = ex ? 'Shrink assistant' : 'Expand assistant'; }
  var tb=document.getElementById('copilot-topbar-toggle');
  if(tb){ tb.innerHTML = collapsed ? '\\u00AB Chat' : 'Chat \\u203A';
          tb.title = collapsed ? 'Show the AI assistant' : 'Hide the AI assistant'; }
}
var _syncExpandBtn=_syncCopilotBtns;  // back-compat alias
function toggleCopilot(){
  var app=document.querySelector('.app');
  if(!app) return;
  app.classList.toggle('right-collapsed');
  if(app.classList.contains('right-collapsed')) app.classList.remove('right-expanded');
  try{ localStorage.setItem('copilotCollapsed', app.classList.contains('right-collapsed')?'1':'0'); }catch(e){}
  _syncExpandBtn();
}
function toggleExpand(){
  var app=document.querySelector('.app');
  if(!app) return;
  app.classList.remove('right-collapsed');           // expanding implies visible
  app.classList.toggle('right-expanded');
  try{
    localStorage.setItem('copilotExpanded', app.classList.contains('right-expanded')?'1':'0');
    localStorage.setItem('copilotCollapsed','0');
  }catch(e){}
  _syncExpandBtn();
}
(function(){
  try{
    var app=document.querySelector('.app'); if(!app) return;
    if(localStorage.getItem('copilotCollapsed')==='1') app.classList.add('right-collapsed');
    else if(localStorage.getItem('copilotExpanded')==='1') app.classList.add('right-expanded');
  }catch(e){}
})();
document.addEventListener('DOMContentLoaded', _syncCopilotBtns);
function insertCmd(c){
  var el=document.getElementById('chat-input'); el.value=c+' '; el.focus();
}
function fillChat(text){
  var el=document.getElementById('chat-input');
  if(el){ el.value=text; el.focus(); }
}

// ---- streaming chat (SSE: token / tool_start / tool_end / done / error) ----
var TOOL_LABELS = {
  clinic_kpis: 'Reading clinic KPIs',
  services_due: "Checking what's due",
  lapsed_clients: 'Finding lapsed clients',
  recent_visits: 'Reviewing recent visits',
  revenue_breakdown: 'Breaking down revenue',
  find_patients: 'Searching patients',
  patient_summary: 'Pulling patient history'
};
var _streaming=false, _thinker=null;
function _esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function _md(t){ try{ return marked.parse(t); }catch(e){ return _esc(t); } }
function _chatScroll(){ var cb=document.getElementById('chat-body'); if(cb) cb.scrollTop=cb.scrollHeight; }
function addBubble(role, html){
  var cb=document.getElementById('chat-body'); if(!cb) return null;
  var h=cb.querySelector('.chat-empty-hint'); if(h) h.style.display='none';
  var d=document.createElement('div'); d.className='msg '+role; d.innerHTML=html||'';
  cb.appendChild(d); _chatScroll(); return d;
}
function showThinking(){
  var cb=document.getElementById('chat-body'); if(!cb) return;
  _thinker={started:Date.now(), tool:null, el:document.createElement('div')};
  _thinker.el.className='thinking-indicator';
  _thinker.el.innerHTML='<span class="dot"></span><span class="tlabel">Thinking…</span> <span class="secs">0s</span>';
  cb.appendChild(_thinker.el); _chatScroll();
  _thinker.timer=setInterval(_updThinking, 400);
}
function _updThinking(){
  if(!_thinker) return;
  var s=Math.floor((Date.now()-_thinker.started)/1000);
  var lbl=_thinker.tool ? (TOOL_LABELS[_thinker.tool]||_thinker.tool) : 'Thinking…';
  var L=_thinker.el.querySelector('.tlabel'); if(L) L.textContent=lbl;
  var S=_thinker.el.querySelector('.secs'); if(S) S.textContent=s+'s';
}
function setThinkingTool(name){ if(_thinker){ _thinker.tool=name; _updThinking(); } }
function hideThinking(){ if(_thinker){ clearInterval(_thinker.timer);
  if(_thinker.el.parentNode) _thinker.el.parentNode.removeChild(_thinker.el); _thinker=null; } }
function addToolChip(trace, name){
  if(!trace) return; var c=document.createElement('span'); c.className='tool-chip';
  c.innerHTML='🔧 '+_esc(TOOL_LABELS[name]||name); trace.appendChild(c); _chatScroll();
}
// Sample cards / suggestion chips call this.
function sendMessage(ev){ return streamChat(ev); }

async function streamChat(ev){
  if(ev && ev.preventDefault) ev.preventDefault();
  if(_streaming) return false;
  var input=document.getElementById('chat-input');
  var msg=input ? input.value.trim() : '';
  if(!msg) return false;
  _streaming=true;
  var sendBtn=document.getElementById('chat-send-btn'); if(sendBtn) sendBtn.disabled=true;
  var hero=document.getElementById('welcome-hero'); if(hero) hero.style.display='none';
  addBubble('user', _esc(msg));
  input.value='';
  var tid=(document.getElementById('thread-id')||{}).value||'';
  var trace=null, bubble=null, acc='';
  showThinking();
  try{
    var resp=await fetch('/chat/stream', {method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({message:msg, thread_id:tid})});
    if(!resp.ok){ hideThinking(); addBubble('assistant','Error: '+resp.status);
      _streaming=false; if(sendBtn) sendBtn.disabled=false; return false; }
    var reader=resp.body.getReader(), dec=new TextDecoder(), buf='';
    while(true){
      var r=await reader.read(); if(r.done) break;
      buf+=dec.decode(r.value, {stream:true});
      var idx;
      while((idx=buf.indexOf('\\n\\n'))!==-1){
        var rawev=buf.slice(0,idx); buf=buf.slice(idx+2);
        var type=null, data='';
        rawev.split('\\n').forEach(function(line){
          if(line.indexOf('event: ')===0) type=line.slice(7).trim();
          else if(line.indexOf('data: ')===0) data+=line.slice(6);
        });
        if(!type) continue;
        var payload={}; try{ payload=data?JSON.parse(data):{}; }catch(e){}
        if(type==='token'){
          if(acc===''){ hideThinking(); bubble=addBubble('assistant',''); }
          acc+=payload.text||''; bubble.innerHTML=_md(acc); _chatScroll();
        } else if(type==='tool_start'){
          if(!trace){ trace=document.createElement('div'); trace.className='tool-trace';
            document.getElementById('chat-body').appendChild(trace); }
          setThinkingTool(payload.name); addToolChip(trace, payload.name);
        } else if(type==='error'){
          hideThinking(); if(!bubble) bubble=addBubble('assistant','');
          bubble.innerHTML=_md('⚠ '+(payload.message||'error'));
        } else if(type==='done'){
          hideThinking(); if(bubble) enhanceTables(bubble);
        }
      }
    }
  }catch(e){ hideThinking(); addBubble('assistant','⚠ '+e); }
  hideThinking();
  _streaming=false; if(sendBtn) sendBtn.disabled=false;
  return false;
}
// Auto-scroll + enhance tables after HTMX swaps (e.g. New-chat reset)
document.body.addEventListener('htmx:afterSwap', function(e){
  var cb=document.getElementById('chat-body');
  if(cb){ cb.scrollTop=cb.scrollHeight; enhanceTables(cb); }
});
// CSV copy/download for tables (pehero-style)
function tableToCSV(table){
  var rows=[];
  table.querySelectorAll('tr').forEach(function(tr){
    var cells=[];
    tr.querySelectorAll('th, td').forEach(function(td){
      cells.push('"'+td.textContent.trim().replace(/"/g,'""')+'"');
    });
    rows.push(cells.join(','));
  });
  return rows.join('\\n');
}
function _download(content, mime, name){
  var blob=new Blob([content],{type:mime});
  var a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download=name; a.click();
  URL.revokeObjectURL(a.href);
}
function enhanceTables(container){
  if(!container) return;
  container.querySelectorAll('table').forEach(function(table){
    if(table.dataset.enhanced) return;
    table.dataset.enhanced='1';
    var toolbar=document.createElement('div');
    toolbar.className='table-toolbar';
    var copyBtn=document.createElement('button');
    copyBtn.textContent='Copy CSV';
    copyBtn.className='table-action-btn';
    copyBtn.onclick=function(){
      navigator.clipboard.writeText(tableToCSV(table)).then(function(){
        copyBtn.textContent='Copied!';
        setTimeout(function(){copyBtn.textContent='Copy CSV';},1500);
      });
    };
    var dlBtn=document.createElement('button');
    dlBtn.textContent='Download CSV';
    dlBtn.className='table-action-btn';
    dlBtn.onclick=function(){
      _download(tableToCSV(table),'text/csv','fastclinic-data.csv');
    };
    var xlsBtn=document.createElement('button');
    xlsBtn.textContent='Download XLS';
    xlsBtn.className='table-action-btn';
    xlsBtn.onclick=function(){
      // Excel opens an HTML table served with the xls MIME type.
      var html='<html xmlns:x="urn:schemas-microsoft-com:office:excel"><head>'
        +'<meta charset="utf-8"></head><body>'
        +table.outerHTML.replace(/<(button|div class="table-toolbar")[\\s\\S]*?<\\/\\1>/g,'')
        +'</body></html>';
      _download(html,'application/vnd.ms-excel','fastclinic-data.xls');
    };
    toolbar.appendChild(copyBtn);
    toolbar.appendChild(dlBtn);
    toolbar.appendChild(xlsBtn);
    table.parentNode.insertBefore(toolbar,table);
  });
}
// Copy chat conversation to clipboard
function copyChat(){
  var cb=document.getElementById('chat-body');
  if(!cb) return;
  var msgs=cb.querySelectorAll('.msg');
  var lines=[];
  msgs.forEach(function(m){
    var role=m.classList.contains('user')?'You':m.classList.contains('system')?'System':'Assistant';
    lines.push(role+': '+m.textContent.trim());
  });
  var text=lines.join('\\n\\n');
  navigator.clipboard.writeText(text).then(function(){
    var btn=document.getElementById('copy-chat-btn');
    if(btn){btn.textContent='Copied!'; setTimeout(function(){btn.textContent='Copy Chat';},1500);}
  });
}
// Share chat — copy current URL with thread_id to clipboard
function shareChat(){
  var tid=document.getElementById('thread-id');
  var url=window.location.origin+'/ai'+(tid?'?thread='+tid.value:'');
  navigator.clipboard.writeText(url).then(function(){
    var btn=document.getElementById('share-chat-btn');
    if(btn){btn.textContent='Link copied!'; setTimeout(function(){btn.textContent='Share';},1500);}
  });
}
// SMS character counter
function updateCharCount(el){
  var n=el.value.length, parts=Math.ceil(n/160)||1;
  var lbl=n+' / 160 chars ('+parts+' SMS'+(parts>1?'es':'')+')';
  var c=document.getElementById('sms-chars'); if(c) c.textContent=lbl;
}
"""


def page(active: str, env: str, user_email: str, thread_id: str, *content, right_override=None):
    right = right_override if right_override is not None else right_pane_chat(thread_id)
    return (
        Title("FastClinic Cockpit"),
        Link(rel="icon", type="image/svg+xml", href="/favicon.svg"),
        # htmx is already provided by fast_app's default headers — don't double-load it.
        Script(src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"),
        Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js"),
        Style(LAYOUT_CSS),
        Div(
            topbar(env, user_email),
            left_pane(active),
            Div(*content, cls="center-pane"),
            right,
            Div(NotStr("&lsaquo; AI Assistant"), id="copilot-reopen", onclick="toggleCopilot()",
                title="Show assistant"),
            cls="app",
        ),
        Script(LAYOUT_JS),
    )


def kpi_card(label: str, value, trend: str = "", warn: bool = False, neutral: bool = False):
    cls = "kpi"
    if warn: cls += " warn"
    if neutral: cls += " neutral"
    return Div(
        Div(label, cls="label"),
        Div(f"{value:,}" if isinstance(value, (int, float)) else str(value), cls="value"),
        Div(trend, cls="trend") if trend else None,
        cls=cls,
    )


def plot_div(div_id: str, spec_json: str):
    """Inline plotly plot. spec_json is a JSON string with {data, layout}."""
    return (
        Div(id=div_id, cls="plot"),
        Script(NotStr(f"""
(function(){{
  var spec = {spec_json};
  Plotly.newPlot('{div_id}', spec.data, spec.layout,
    {{displayModeBar:false, responsive:true}});
}})();
""")),
    )
