You are auditing the **llms.txt** file for **{{site_url}}** — the emerging
standard for describing a site to AI systems. The file, if present, is shown
in the SITE CONTEXT under `## /llms.txt`.

If `/llms.txt` returned **HTTP 404** or is empty: still emit the 8 rows below
but mark every `status` as `missing` and every `score` as `0`, with the
`finding` explaining "File not present" and the `recommendation` suggesting
what to add.

Otherwise, evaluate the 8 structural checks:

| # | Check |
|---|---|
| 1 | H1 Title — present, matches business name |
| 2 | Blockquote Description — present, < 200 chars |
| 3 | H2 Sections — at least one category section |
| 4 | Page Entries — at least 5 properly formatted |
| 5 | Absolute URLs — all `https://` fully-qualified |
| 6 | URL Validity — pages are discoverable (cross-check against crawled pages shown in SITE CONTEXT) |
| 7 | Entry Descriptions — each entry has explanatory text |
| 8 | Key Facts & Contact — contact info present |

Per row:
- `status`: `pass` / `partial` / `fail` / `missing`
- `score`: integer 0-100 for this dimension
- `finding`: one sentence describing what you observed
- `recommendation`: one concrete fix (or "No action needed" if `pass`)

**Return CSV only** — no preamble, no code fences. Header:

```
check,status,score,finding,recommendation
```

Quote cells with commas.

---

## SITE CONTEXT (includes /llms.txt + sitemap + pages)

{{site_content}}
