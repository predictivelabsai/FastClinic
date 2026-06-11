#!/usr/bin/env bash
# Generate the FastClinic walkthrough GIF.
#
# Installs Playwright + Pillow, drives the cockpit through its key screens with
# a headless browser, and writes docs/demo/fastclinic-walkthrough.gif.
#
#   ./scripts/build_demo_gif.sh                       # against the live deploy
#   DEMO_BASE_URL=http://localhost:5005 ./scripts/build_demo_gif.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"

echo "==> Installing Playwright + Pillow"
"$PY" -m pip install --quiet --upgrade playwright pillow
"$PY" -m playwright install --with-deps chromium

echo "==> Running walkthrough"
DEMO_BASE_URL="${DEMO_BASE_URL:-https://fastclinic.predictivelabs.ai}" \
  "$PY" scripts/demo_walkthrough.py
