#!/usr/bin/env bash
# Build the FastClinic user guide PDF (landscape slide deck) from markdown.
#
#   bash scripts/build_user_guide.sh
#
# Pipeline: pandoc (markdown -> standalone HTML linking docs/assets/guide.css)
#           -> WeasyPrint (HTML -> PDF, A4 landscape, one slide per "---").
# Each run stamps the current version (from VERSION) + generation date into the
# guide's title slide and the PDF page footer, so the document is always dated.
# Requires: pandoc, weasyprint. Run from the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docs"

SRC="fastclinic_user_guide.md"
HTML="fastclinic_user_guide.html"
PDF="fastclinic_user_guide.pdf"

VERSION="$(awk '{print $1; exit}' "$ROOT/VERSION")"
GEN_DATE="$(date +%Y-%m-%d)"
echo "→ stamping version $VERSION · generated $GEN_DATE"

# Stamp the title-slide line (in-place; the web guide reads the same file).
sed -i -E "s|^Version .* Runs at \*\*fastclinic\.example\*\*|Version ${VERSION} · Generated ${GEN_DATE} · Runs at **fastclinic.example**|" "$SRC"

# Stamp the PDF page footer (right-hand @page content in guide.css).
sed -i -E "s|content: \"[^\"]*fastclinic\.example\"|content: \"v${VERSION} · ${GEN_DATE} · fastclinic.example\"|" assets/guide.css

echo "→ pandoc: $SRC -> $HTML"
pandoc "$SRC" -s -o "$HTML" \
  --from=markdown-implicit_figures \
  --css "assets/guide.css" \
  --metadata pagetitle="FastClinic — User Guide (v${VERSION}, ${GEN_DATE})"

echo "→ weasyprint: $HTML -> $PDF"
# base dir = docs/, so assets/ and img/ resolve relatively
weasyprint "$HTML" "$PDF"

echo "✓ Built docs/$PDF (v${VERSION}, ${GEN_DATE}, $(du -h "$PDF" | cut -f1))"
