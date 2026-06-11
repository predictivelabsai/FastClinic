You are producing a **pre-publish SEO checklist** for new content on
**{{site_url}}** (private GP / primary-care vertical).

Generate a **20-item quality gate** the content team must clear before pressing
"Publish". Tailor items to medical content: YMYL (Your Money Your Life) standards,
E-E-A-T (clinician reviewer byline, last-medically-reviewed date, citations),
GDPR / patient-privacy, clinical-accuracy disclaimers, and standard on-page SEO.

Per item:
- `required`: yes (blocking) / no (nice-to-have)
- `status`: template-default should be `pending` — the template user fills in per
  article
- `guidance`: one-sentence "how to verify this is done"

Be prescriptive and concrete. Prefer "Verify the page's meta description is
140-160 characters" over "Check meta description".

**Return CSV only** — header:

```
check,required,status,guidance
```

Quote cells with commas.

---

## SITE CONTEXT

{{site_content}}
