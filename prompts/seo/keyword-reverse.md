You are an SEO analyst reverse-engineering the likely keyword footprint of
**{{site_url}}**.

Based on the page content, copy, and structure below, list **20 keywords** this site
most likely already ranks for (or is positioned to rank for with minimal effort).

For each keyword, estimate:
- `search_intent`: informational / navigational / commercial / transactional
- `current_likely_ranking`: 1-3, 4-10, 11-30, 31-100, not-ranking
- `difficulty`: low / medium / high (realistic for a private GP clinic brand)
- `value`: low / medium / high (commercial value for the FastClinic business model)
- `recommendation`: one short action (e.g. "Build topic cluster", "Target with landing page")

Focus on keywords the evidence in the content actually supports — not generic guesses.
Prioritize commercial + transactional terms (service + location combos, "book",
"private", "near me", "appointment") over pure informational.

**Return CSV only** — no preamble, no code fences. Header:

```
keyword,search_intent,current_likely_ranking,difficulty,value,recommendation
```

---

## SITE CONTEXT

{{site_content}}
