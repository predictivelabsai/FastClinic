#!/usr/bin/env bash
# Build the FastClinic user guide as a landscape slide deck — PDF + PPTX.
#
#   bash scripts/build_user_guide.sh                       # newest dated guide
#   bash scripts/build_user_guide.sh docs/fastclinic_user_guide_2026-07-20.md
#
# Pipeline:
#   PDF  — pandoc (md -> standalone HTML + assets/guide.css) -> WeasyPrint
#          (A4 landscape, one slide per "---", screenshot floated per page).
#   PPTX — python-pptx (md -> 16:9 deck with a branded cover, native tables,
#          and one screenshot per slide), kept visually in sync with the PDF.
# Screenshots come from docs/img/ — refresh them with:
#   DEMO_BASE_URL=http://localhost:5005 python scripts/capture_guide_screenshots.py
#
# Requires: pandoc, weasyprint, python-pptx. Run from the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
cd "$ROOT/docs"

# Guide source: explicit arg, else the canonical undated source. Both rendered
# formats consume the same dated snapshot so their page/slide structure cannot
# drift apart.
if [ "${1:-}" != "" ]; then
  SRC="$(basename "$1")"
else
  SRC="fastclinic_user_guide.md"
fi
[ -n "${SRC:-}" ] && [ -f "$SRC" ] || { echo "⚠ guide markdown not found: docs/$SRC"; exit 1; }

GEN_DATE="$(date +%Y-%m-%d)"
GEN_DATE_LONG="$(date '+%-d %B %Y')"
BASE="fastclinic_user_guide_${GEN_DATE}"
SNAPSHOT="${BASE}.md"
HTML="${BASE}.html"
PDF="${BASE}.pdf"
PPTX="${BASE}.pptx"
TITLE="FastClinic — User Guide"

VERSION="$(awk '{print $1; exit}' "$ROOT/VERSION" 2>/dev/null || echo 0.1.0)"
echo "→ building ${SRC} · v${VERSION} · ${GEN_DATE}"

# Materialise a dated, reviewable source snapshot from the canonical template.
sed -e "s/{{GUIDE_VERSION}}/${VERSION}/g" \
    -e "s/{{GUIDE_DATE_LONG}}/${GEN_DATE_LONG}/g" \
    -e "s/{{GUIDE_DATE}}/${GEN_DATE}/g" \
    "$SRC" > "$SNAPSHOT"

# Stamp a temporary PDF stylesheet without dirtying the committed source CSS.
TMP_CSS="$(mktemp "$ROOT/docs/.guide.XXXXXX.css")"
trap 'rm -f "$TMP_CSS" "$HTML"' EXIT
sed -E "s|content: \"v[^\"]* · fastclinic\.dev · \" counter\(page\)|content: \"v${VERSION} · ${GEN_DATE} · fastclinic.dev · \" counter(page)|" \
  assets/guide.css > "$TMP_CSS"

# PDF
pandoc "$SNAPSHOT" -s -o "$HTML" \
  --from=markdown-implicit_figures \
  --css "$TMP_CSS" \
  --metadata pagetitle="${TITLE} (v${VERSION}, ${GEN_DATE})"
weasyprint "$HTML" "$PDF"           # base dir = docs/, so assets/ + img/ resolve
echo "✓ PDF  docs/$PDF ($(du -h "$PDF" | cut -f1))"

# PPTX
GUIDE_VERSION="$VERSION" GUIDE_DATE="$GEN_DATE" \
  "$PY" "$ROOT/scripts/build_pptx.py" "$SNAPSHOT" "$PPTX" "$TITLE"
echo "✓ PPTX docs/$PPTX ($(du -h "$PPTX" | cut -f1))"

PDF_PAGES="$(pdfinfo "$PDF" | awk '/^Pages:/ {print $2}')"
PPTX_SLIDES="$("$PY" - "$PPTX" <<'PY'
import sys
from pptx import Presentation
print(len(Presentation(sys.argv[1]).slides))
PY
)"
[ "$PDF_PAGES" = "$PPTX_SLIDES" ] || {
  echo "✗ PDF/PPTX structure mismatch: ${PDF_PAGES} pages vs ${PPTX_SLIDES} slides"
  exit 1
}
echo "✓ Structure parity: ${PDF_PAGES} PDF pages = ${PPTX_SLIDES} PPTX slides"

echo "✓ FastClinic user guide built (v${VERSION}, ${GEN_DATE}): PDF + PPTX."
