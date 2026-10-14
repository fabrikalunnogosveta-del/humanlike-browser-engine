# humanlike-browser-engine

Human-like browser motion primitives for Python: lognormal latencies, Bezier cursor
paths with Fitts's-law targeting, inertial wheel scrolling with exact delta delivery,
and burst typing with keyboard-layout distance modeling.

Real people never move like machines: the hand arcs instead of drawing straight lines,
pauses follow a long-tailed distribution instead of uniform delays, and typing runs in
bursts shaped by muscle memory. This library turns raw Playwright-style input calls into
those natural patterns — useful for UI testing, accessibility automation, and any
workflow where input should look and feel human.

## Why

Constant-speed cursors and uniform delays are trivially distinguishable from real user
input by trajectory analysis (histograms of mousemove intervals, straight-line paths,
identical keystroke rhythm). This package implements the opposite: statistically
grounded motion models you can seed and reproduce.

## Features

| Module | What it does |
|---|---|
| `distribution_browser_engine` | Lognormal delay engine (60Hz-quantized), Bezier mouse moves + Fitts click offsets, inertial wheel scroll with decay-shaped step plan, burst typing (typos, flight/dwell times, bigram muscle memory, 5 keyboard layouts), 3-tier cookie-banner dismissal (CSS selectors → semantic DOM scan) |
| `bezier_mouse` | Cubic Bezier trajectories with overshoot/undershoot, physiological tremor (8-12Hz octaves), frame-quantized step delays, size-dependent speed (Fitts's law) |
| `cursor_state` | Shared cursor-position state, window-offset calibration |
| `humanization_engine` | Persona-driven behavior models: energy curve, cognitive pauses, reading loops, human-error primitives |

## Install

```bash
git clone <this repo>
cd humanlike-browser-engine
pip install -r requirements.txt
```

## Quickstart

```python
import random
from distribution_browser_engine import (
    _human_inertial_wheel, _human_burst_type, _human_mouse_to,
    set_fast_mode,
)

rng = random.Random(42)
# set_fast_mode(True)  # uncomment for fast/test runs

# Scroll exactly 600px with a decay-shaped human flick pattern
_human_inertial_wheel(page, 600, rng)

# Type text in bursts with realistic flight/dwell times
_human_burst_type(page, "hello world", rng, locale="en")
```

```python
from bezier_mouse import bezier_path
pts = bezier_path(0, 0, 400, 300, rng=random.Random(7),
                  profile={"mouse_deviation": 30})
# deterministic: same seed → same trajectory, ends exactly at target
```

## Testing

The suite (19 tests) proves the behavioral contracts, not just that code runs:

- inertial scroll steps **sum to the requested delta** (parametrized: 50–2000px),
  per-step cap respected, tiny deltas rejected (<5px)
- burst typing **preserves the text even when the typo engine fires**
  (forced 100%-typo regression test)
- click after auto-scroll uses a **fresh bounding box** (no stale-coordinate clicks)
- focus check returns **within a ~2s budget** and caches success for 3s
- Fitts offsets stay inside the element bounds; Bezier paths are seed-deterministic

```bash
pip install pytest
python -m pytest tests/ -q
```

CI runs the same suite on every push (badge below).

[![CI](https://github.com/fabrikalunnogosveta-del/humanlike-browser-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/fabrikalunnogosveta-del/humanlike-browser-engine/actions)

## Design notes

- **Seeded everything**: delays sample from the module's `rng`, so demos and tests are
  reproducible.
- **Fail-safe input paths**: focus checks are time-budgeted (no multi-second stalls),
  CDP-hung wheel calls drop their queue post-hoc, clicks abort if the target element
  disappears during auto-scroll.
- **No network, no accounts**: pure computation on top of the Playwright API surface
  you already use.

## License

MIT
