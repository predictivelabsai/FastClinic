You are a local-SEO specialist auditing **{{site_url}}** (a private GP clinic).

FastClinic serves **UK patients** seeking fast primary care across its clinic sites in
cities like **London, Manchester, Bristol, Leeds, Sheffield**. List **20 high-intent
local keyword opportunities** combining UK city/region targeting with GP service intent.

For each keyword:
- `location`: a UK city or region the clinic serves
- `intent_type`: commercial / transactional / comparison
- `monthly_volume_est`: low (<100) / medium (100-1k) / high (>1k)  — estimate
- `competition`: low / medium / high
- `priority`: 1-5 (1 = highest, rank top 5 priorities first)

Prefer queries a real patient types: `"private GP london"`,
`"same-day doctor appointment manchester"`,
`"flu jab near me bristol"`, `"health check leeds"`.

**Return CSV only** — header:

```
keyword,location,intent_type,monthly_volume_est,competition,priority
```

---

## SITE CONTEXT

{{site_content}}
