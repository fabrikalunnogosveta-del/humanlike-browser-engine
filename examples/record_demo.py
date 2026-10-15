"""Record a REAL engine run to docs/demo.gif (dev-only tool, not a runtime dep).

    python examples/record_demo.py

Launches a headed Chromium, drives the REAL OS cursor (Bezier move -> Fitts
click -> inertial scroll -> burst typing) while an mss thread captures
EXACTLY the browser window rect (screenX/Y * devicePixelRatio) — the desktop
and other windows are never in frame. Keep your hands off the mouse while it
runs. Needs: playwright, mss, pillow.
"""
import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from distribution_browser_engine import (
    _human_scroll,
    human_click_box,
    human_input_manager,
)

FPS = 10
OUT_W = 700
OUT = Path(__file__).resolve().parents[1] / "docs" / "demo.gif"

_PARA = (
    "Latency is sampled from a lognormal distribution, quantized to the 60Hz "
    "frame, so no two runs feel robotic. The cursor follows a Bezier path with "
    "a deceleration phase, like a real hand settling on a target."
)
_SECTIONS = "\n".join(
    f"<h2>{i:02d}. Motion principle</h2><p>{_PARA}</p>" for i in range(1, 13)
)
PAGE = f"""<!doctype html><html><head><meta charset="utf-8"><style>
:root {{ color-scheme: dark; }}
body {{ margin:0; background:#0d1117; color:#c9d1d9;
  font:16px/1.6 system-ui,Segoe UI,sans-serif; }}
#banner {{ background:#161b22; border-bottom:1px solid #30363d; padding:10px 18px;
  font-weight:600; color:#58a6ff; }}
#bar {{ position:sticky; top:0; display:flex; gap:10px; padding:14px 18px;
  background:#0d1117e6; border-bottom:1px solid #21262d; backdrop-filter:blur(4px); }}
#q {{ flex:1; padding:12px 16px; border-radius:8px; border:1px solid #30363d;
  background:#0d1117; color:#c9d1d9; font-size:16px; outline:none; }}
#go {{ padding:12px 22px; border-radius:8px; border:0; font-size:15px; font-weight:600;
  background:#238636; color:#fff; cursor:pointer; }}
#go.done {{ background:#1a7f37; }}
main {{ max-width:760px; margin:24px auto 90px; padding:0 20px; }}
h1 {{ color:#f0f6fc; }} h2 {{ color:#f0f6fc; margin-top:2.2em; }}
#foot {{ position:fixed; bottom:0; left:0; right:0; padding:10px 18px;
  background:#161b22; border-top:1px solid #30363d; color:#8b949e; font-size:13px; }}
</style></head><body>
<div id="banner">&#9654; humanlike-browser-engine &mdash; live run (real OS cursor)</div>
<div id="bar"><input id="q" value="" placeholder="search motion principles">
<button id="go">Run demo</button></div>
<main><h1>Human-like browser motion</h1><p>Scroll &middot; type &middot; click &mdash; exactly like a person.</p>
{_SECTIONS}</main>
<div id="foot">Bezier + Fitts &middot; lognormal latency &middot; inertial scroll &middot; burst typing &middot; MIT</div>
<script>
document.getElementById('go').addEventListener('click', function () {{
  this.textContent = 'Done - run complete';
  this.classList.add('done');
}});
</script></body></html>"""


class Recorder(threading.Thread):
    """Capture the given screen region (browser window only) at FPS."""

    def __init__(self, region):
        super().__init__(daemon=True)
        self.region = region  # {left, top, width, height} in physical px
        self.frames = []
        self.stop_evt = threading.Event()

    def run(self):
        import mss

        period = 1.0 / FPS
        with mss.MSS() as sct:
            while not self.stop_evt.is_set():
                t0 = time.perf_counter()
                shot = sct.grab(self.region)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                h = max(1, int(OUT_W * shot.size[1] / shot.size[0]))
                self.frames.append(img.resize((OUT_W, h), Image.LANCZOS))
                time.sleep(max(0.0, period - (time.perf_counter() - t0)))


def _box(page, selector):
    b = page.locator(selector).bounding_box()
    return [b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]]


def main():
    rng = random.Random(11)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_page()
        page.set_content(PAGE)
        page.bring_to_front()
        time.sleep(0.8)

        # capture ONLY the browser window: CSS rect * devicePixelRatio = px
        left, top, w, h = page.evaluate(
            "() => { const d = window.devicePixelRatio || 1;"
            " return [Math.max(0, Math.round(window.screenX * d)),"
            " Math.max(0, Math.round(window.screenY * d)),"
            " Math.round(window.outerWidth * d),"
            " Math.round(window.outerHeight * d)]; }"
        )
        rec = Recorder({"left": left, "top": top,
                        "width": w, "height": h})
        rec.start()
        time.sleep(0.3)
        try:
            # 1) Fitts click into the search field (real cursor flies over)
            human_click_box(page, _box(page, "#q"), rng)
            # 2) burst typing, locale-aware, with natural inter-key delays
            human_input_manager(page, page.locator("#q"),
                                "bezier cursor paths", rng, wpm=58)
            # 3) hand first, then inertial scroll down the article
            _human_scroll(page, rng, count=2, px_range=(350, 550))
            # 4) Fitts click on the primary button
            human_click_box(page, _box(page, "#go"), rng)
            time.sleep(1.0)
        finally:
            rec.stop_evt.set()
            rec.join(timeout=15)
            browser.close()

    if not rec.frames:
        raise SystemExit("no frames captured")
    # 10fps -> 5fps + 64-color palette: keeps the README GIF a few MB
    final = [f.quantize(colors=64, dither=Image.Dither.NONE)
             for f in rec.frames[::2]]
    OUT.parent.mkdir(exist_ok=True)
    final[0].save(
        OUT, save_all=True, append_images=final[1:],
        duration=200, loop=0, optimize=True, disposal=2,
    )
    print(f"OK: {len(final)} frames -> {OUT} "
          f"({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
