#!/usr/bin/env python3
"""Playwright walkthrough of the FastClinic cockpit → animated GIF.

Logs into the (deployed or local) cockpit, clicks through the key screens,
captures a screenshot of each, and stitches them into an animated GIF at
`docs/demo/fastclinic-walkthrough.gif`.

Usage:
    # against the live deploy (default)
    python scripts/demo_walkthrough.py

    # against a local dev server
    DEMO_BASE_URL=http://localhost:5005 python scripts/demo_walkthrough.py

Env:
    DEMO_BASE_URL              base URL (default: https://fastclinic.predictivelabs.ai)
    FASTCLINIC_ADMIN_EMAIL     login email   (default: admin@fastclinic.example)
    FASTCLINIC_ADMIN_PASSWORD  login password (default: FastClinic2026$)

Install deps first (or just run scripts/build_demo_gif.sh):
    pip install playwright pillow && python -m playwright install chromium
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_URL = os.getenv("DEMO_BASE_URL", "https://fastclinic.predictivelabs.ai").rstrip("/")
EMAIL = os.getenv("FASTCLINIC_ADMIN_EMAIL", "admin@fastclinic.example")
PASSWORD = os.getenv("FASTCLINIC_ADMIN_PASSWORD", "FastClinic2026$")

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "demo"
FRAME_DIR = OUT_DIR / "frames"
GIF_PATH = OUT_DIR / "fastclinic-walkthrough.gif"

VIEWPORT = {"width": 1440, "height": 900}
FRAME_WIDTH = 1000          # downscale screenshots for a lighter GIF
FRAME_MS = 1900             # ms per frame

# (caption, path) — the key screens of the cockpit, in tour order.
SCREENS = [
    ("Business Overview", "/"),
    ("Patients", "/patients"),
    ("Patient profile", "/patients/1206"),
    ("Clinical — diagnoses & clinician activity", "/clinical"),
    ("Revenue by category", "/revenue"),
    ("Activation — Immunisations & checks due", "/activation/reminders"),
    ("Activation — Lapsed reactivation", "/activation/lapsed"),
    ("Activation — Post-visit follow-up", "/activation/followup"),
    ("AI assistant", "/ai"),
    ("SMS broadcaster", "/ops/sms"),
    ("SEO audit suite", "/seo"),
    ("Data & import", "/admin/data"),
]


def login(page) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=45000)
    page.fill('input[name="email"]', EMAIL)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=45000)


def capture(page) -> list[tuple[str, Path]]:
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    shots: list[tuple[str, Path]] = []
    for i, (label, path) in enumerate(SCREENS):
        url = f"{BASE_URL}{path}"
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:  # noqa: BLE001 — keep the tour going
            print(f"  ! {path}: {e}")
        page.wait_for_timeout(1400)        # let Plotly charts finish rendering
        out = FRAME_DIR / f"{i:02d}.png"
        page.screenshot(path=str(out))     # viewport-only → uniform frame size
        shots.append((label, out))
        print(f"  captured {path} -> {out.name}")
    return shots


def build_gif(shots: list[tuple[str, Path]]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    def _font(size: int):
        for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:  # noqa: BLE001
                continue
        return ImageFont.load_default()

    font = _font(18)
    frames = []
    for label, png in shots:
        img = Image.open(png).convert("RGB")
        w, h = img.size
        img = img.resize((FRAME_WIDTH, round(h * FRAME_WIDTH / w)), Image.LANCZOS)
        draw = ImageDraw.Draw(img)
        bar_h = 36
        y0 = img.height - bar_h
        draw.rectangle([0, y0, img.width, img.height], fill=(27, 39, 51))   # #1b2733
        draw.rectangle([0, y0, 6, img.height], fill=(30, 111, 184))          # accent #1e6fb8
        draw.text((16, y0 + 8), f"FastClinic · {label}", fill=(255, 255, 255), font=font)
        frames.append(img)

    if not frames:
        sys.exit("No frames captured — nothing to stitch.")
    GIF_PATH.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        GIF_PATH, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True,
    )
    kb = GIF_PATH.stat().st_size // 1024
    print(f"\nGIF written: {GIF_PATH.relative_to(ROOT)}  ({len(frames)} frames, {kb} KB)")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright not installed. Run scripts/build_demo_gif.sh or:\n"
                 "  pip install playwright pillow && python -m playwright install chromium")
    print(f"Walkthrough of {BASE_URL} as {EMAIL}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()
        login(page)
        shots = capture(page)
        browser.close()
    build_gif(shots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
