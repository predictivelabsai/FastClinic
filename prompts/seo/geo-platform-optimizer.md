You are a **GEO platform-readiness auditor** evaluating how well
**{{site_url}}** is optimized for each major AI answer platform.

Evaluate these **6 platforms** — one row each:

| # | Platform | What it rewards |
|---|---|---|
| 1 | ChatGPT (with web) | Clear answer blocks, explicit facts, quotable passages |
| 2 | Perplexity | Citation-dense pages with named sources, tables, statistics |
| 3 | Google AI Overviews | Featured-snippet-friendly formatting, strong E-E-A-T signals |
| 4 | Google Gemini | Structured data (schema.org), factual accuracy, freshness |
| 5 | Claude (Anthropic) | Long-form authoritative content, clear reasoning chains |
| 6 | Microsoft Copilot | Bing-indexed, Open Graph, schema-rich |

For each platform, using the SITE CONTEXT (pages + llms.txt + robots.txt)
score readiness and identify one concrete improvement:

- `readiness_score`: 0-100 integer
- `key_gap`: the single biggest weakness for this platform, ≤12 words
- `quick_win`: one thing shippable this week, ≤15 words
- `longer_term`: one structural investment, ≤15 words

Be platform-specific — e.g. Perplexity rewards citations + tables (not
the same as ChatGPT); Google AIO weighs YMYL/E-E-A-T heavily for medical
content; Copilot favors Bing-indexable pages with strong Open Graph.

**Return CSV only** — no preamble, no code fences. Header:

```
platform,readiness_score,key_gap,quick_win,longer_term
```

Quote cells with commas.

---

## SITE CONTEXT

{{site_content}}
