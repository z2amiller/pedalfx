#!/usr/bin/env python3
"""Check a 1590XX faceplate (.kicad_pcb text) against faceplate.py: pot holes, the glow-through LED trefoils, no
125B leftovers on the guide layers, a current copper fill and, for a built faceplate, its labels and frames.
Stdlib only.

usage: check_face1590xx.py FACEPLATE.kicad_pcb            (template positions)   exit 1 on any failure
"""
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import faceplate as F  # noqa: E402
from check_full1590xx import _items  # noqa: E402

HOLE_R, TOL = 4.0, 0.01
_XY = re.compile(r'\((?:xy|start|end|center|mid|at) (-?[\d.]+) (-?[\d.]+)')


def _layer(item):
    m = re.search(r'\(layers? "([^"]+)"', item)
    return m.group(1) if m else None


def _circle(item):
    c = re.search(r'\(center (-?[\d.]+) (-?[\d.]+)\)', item)
    e = re.search(r'\(end (-?[\d.]+) (-?[\d.]+)\)', item)
    cx, cy, ex, ey = float(c.group(1)), float(c.group(2)), float(e.group(1)), float(e.group(2))
    return cx, cy, math.hypot(ex - cx, ey - cy)


def _pts(block):
    """Outline points; an arc segment (the trefoil's round centre keepout) contributes its start, mid and end."""
    return [(float(x), float(y)) for x, y in re.findall(r'\((?:xy|start|mid|end) (-?[\d.]+) (-?[\d.]+)\)', block)]


def _centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _inside(p, poly):
    x, y, c = p[0], p[1], False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _near(p, q, d):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= d


def check_face(text, holes, leds, labels=None, frames=None):
    """Return failure messages (empty = pass). holes: face (x, y) of every r 4.0 Edge.Cuts hole; leds: trefoil
    centres. labels: optional (text, x, y) the silkscreen must carry; frames: optional F.Mask frame polygons."""
    items = _items(text)
    msgs = []
    circles = [(i.split()[0][1:], _layer(i), _circle(i)) for i in items if i.startswith("(gr_circle")]
    found = [(x, y) for _k, lay, (x, y, r) in circles if lay == "Edge.Cuts" and abs(r - HOLE_R) < 0.05]
    for h in holes:
        if not any(_near(h, f, TOL) for f in found):
            msgs.append(f"hole missing at ({h[0]:.2f}, {h[1]:.2f})")
    for f in found:
        if not any(_near(h, f, TOL) for h in holes):
            msgs.append(f"hole at ({f[0]:.2f}, {f[1]:.2f}) is not a planned hole")

    keepouts = [_centroid(_pts(i.split("(filled_polygon")[0])) for i in items
                if i.startswith("(zone") and "(keepout" in i and _layer(i) == "F.Cu"]
    polys = [_centroid(_pts(i)) for i in items if i.startswith("(gr_poly") and _layer(i) == "F.Mask"]
    dots = [(x, y) for _k, lay, (x, y, r) in circles if lay == "F.Mask" and abs(r - 0.75) < 0.05]
    windows = [(x, y) for _k, lay, (x, y, r) in circles if lay == "B.Mask" and abs(r - 3.5) < 0.05]
    for led in leds:
        got = (sum(_near(led, k, 4.0) for k in keepouts), sum(_near(led, p, 4.0) for p in polys),
               sum(_near(led, d, 0.05) for d in dots), sum(_near(led, w, 0.05) for w in windows))
        if got != (4, 3, 1, 1):
            msgs.append(f"trefoil at ({led[0]:.2f}, {led[1]:.2f}): keepouts/polys/dot/window = {got}, want (4, 3, 1, 1)")
    if (len(keepouts), len(polys), len(dots), len(windows)) != (4 * len(leds), 3 * len(leds), len(leds), len(leds)):
        msgs.append(f"trefoil parts on the board: {len(keepouts)}/{len(polys)}/{len(dots)}/{len(windows)}")

    if "125B" in text:
        msgs.append("125B text left on the board")
    u4 = [(float(x), float(y)) for i in items if _layer(i) == "User.4" for x, y in _XY.findall(i)]
    if u4:
        w = max(p[0] for p in u4) - min(p[0] for p in u4)
        h = max(p[1] for p in u4) - min(p[1] for p in u4)
        if w <= h:
            msgs.append(f"User.4 enclosure drawing is portrait ({w:.1f} x {h:.1f}), not the 1590XX")

    fills = [_pts(b) for i in items if i.startswith("(zone") and "(keepout" not in i and _layer(i) == "F.Cu"
             for b in re.findall(r'\(filled_polygon\s*\(layer "F.Cu"\)\s*(?:\(island\)\s*)?\(pts(.*?)\)\s*\)', i, re.S)]
    for led in leds:
        if any(_inside(led, poly) for poly in fills):
            msgs.append(f"copper fill covers the LED trefoil at ({led[0]:.2f}, {led[1]:.2f}): refill zones")
    if F.TREFOIL_SRC not in [tuple(led) for led in leds] and fills and not any(_inside(F.TREFOIL_SRC, p) for p in fills):
        msgs.append("copper fill is still open at the template's old trefoil spot (110, 127.75): refill zones")

    if labels is not None:
        msgs += _check_labels(items, labels, frames or [])
    return msgs


def _check_labels(items, labels, frames):
    """Placeholder for Task 3: label text, frame containment and hole clearance."""
    return []


def main():
    text = Path(sys.argv[1]).read_text()
    msgs = check_face(text, F.TEMPLATE_HOLES, F.LED_FACE)
    for m in msgs:
        print("FAIL", m)
    print("PASS" if not msgs else f"{len(msgs)} failure(s)")
    sys.exit(1 if msgs else 0)


if __name__ == "__main__":
    main()
