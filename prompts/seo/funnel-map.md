You are an SEO strategist mapping **{{site_url}}** to a full-funnel keyword strategy.

Build a keyword map of **24 keywords** across the patient journey:

- **TOFU** (awareness — "what does a private GP do", "how to see a doctor quickly",
  "do I need a flu jab")
- **MOFU** (consideration — "private GP vs NHS", "is a private health check worth it",
  "same-day GP appointment options")
- **BOFU** (decision — "private GP appointment near me", "book health check london",
  "flu jab near me")

Aim for roughly 8 keywords per stage.

Per keyword:
- `funnel_stage`: tofu / mofu / bofu
- `intent`: short phrase describing what the searcher wants
- `target_page_type`: blog / pillar / landing / booking-form / comparison / faq
- `priority`: 1-5

**Return CSV only** — header:

```
keyword,funnel_stage,intent,target_page_type,priority
```

---

## SITE CONTEXT

{{site_content}}
