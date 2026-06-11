# FastHTML audit — FastClinic cockpit

Audited against `fasthtml.md` (best-practices reference, copied into the repo).
Status reflects the copilot/chat improvement pass.

## Fixed in this pass

1. **Double htmx load (correctness bug).** `fast_app` already injects htmx 2.0.7
   + `fasthtml.js`, but `page()` also loaded htmx **1.9.12** from unpkg — two
   versions on every authenticated page, the older silently winning. Removed the
   manual tag; the app now runs on FastHTML's bundled htmx 2.0.7 (chat verified,
   0 console errors).
2. **Copilot chat tables overflowed the rail** with horizontal scrollbars.
   Tables now use `table-layout: fixed` + `overflow-wrap: anywhere` so cells wrap
   to the rail width; code blocks wrap too. No nested scrollbars.
3. **Expandable copilot.** Right rail now has three states — minimised (`›`),
   normal, and expanded (`«` / `»`, clamps to `42vw`) — so wide answers get room.
   State persists in `localStorage`.
4. **Reopen after minimise.** Added an always-present **"Chat"** toggle in the
   top bar (every page) plus the existing bottom-right tab, so a minimised
   copilot can always be brought back.
5. **Send button** added to both the rail copilot and the full `/ai` chat (Enter
   still works).
6. **Stale upstream remnants removed:** dead `right_pane_calculator()` deleted;
   CSV download filename normalised to `fastclinic-data.csv`.

## Recommendations (not yet applied)

- **Prefer Python/declarative over inline JS** (`fasthtml.md`: "Prefer Python
  whenever possible over JS"). `LAYOUT_JS` is large. Highest-value refactor:
  client-side markdown. Today each chat reply injects a per-message
  `<script>marked.parse(...)</script>`; the idiomatic approach is FastHTML's
  `MarkdownJS()` helper + rendering content into `Div(raw_md, cls="marked")` and
  letting one processor handle it on `htmx:load`. Removes per-message scripts.
- **Vendor front-end deps** (htmx is bundled; marked.js + Plotly are CDN). For an
  offline/locked-down deploy, serve them from the app's static dir.
- **Move repeated inline `style=`** (chips, cards, list markup built via `NotStr`)
  into CSS classes / FT components for consistency and easier theming.
- **Accessibility:** icon-only buttons (`«`, `›`, copy/share) have `title`s; add
  `aria-label`s and a visible focus ring for keyboard users.
- **Dead CSS:** `.calc-*`, `.welcome-hero`, `.suggestion-chip`, `.cmd-chip`
  rules are now unused (treatment calc + chat hero removed) — safe to prune.
- **`hx_on` consistency:** the inline `hx_on_htmx_after_request` JS works; longer
  term, prefer small named handlers or HTMX events over inline strings.

## Already idiomatic (no change needed)

- Function-name routing (`@rt` with no path), tuple/`FT` responses, `NotStr` for
  trusted HTML, session-based auth guard, server-rendered FastHTML over client
  state (Plotly used only for charts), CSV/exports via real Starlette responses.
