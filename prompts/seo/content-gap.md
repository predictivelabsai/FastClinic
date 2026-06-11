You are an SEO content strategist auditing **{{site_url}}** (a private GP / general-practice
clinic helping patients access fast primary care, health checks, and repeat prescriptions).

From the site content below, identify the **15 most valuable content topics** where
there is a gap — either the topic is completely missing, thin, or outdated compared
to what private GP and primary-care clinics typically cover.

Focus on topics that map to real patient search intent: symptom guides, health-check
explainers, immunisation guides, repeat-prescription information, private vs NHS
comparisons, cost breakdowns, insurance / self-pay, same-day appointment access.

For each topic:
- `covered_by_site`: yes / partial / no
- `covered_by_competitors`: yes / no / unclear
- `opportunity_level`: high / medium / low (rank by intersection of value + gap)
- `recommended_action`: one concrete next step (e.g. "Publish 1,500-word guide on X")

**Return CSV only** — no preamble, no prose, no code fences. Header row:

```
topic,covered_by_site,covered_by_competitors,opportunity_level,recommended_action
```

Quote any cell containing a comma.

---

## SITE CONTEXT

{{site_content}}
