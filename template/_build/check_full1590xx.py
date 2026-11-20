#!/usr/bin/env python3
"""Check a 1590XX template board against geometry.py: guide circles, key footprints, removed parts, outline,
clearance minima and (with a project dir) BP101's nets.  Stdlib only; reads the .kicad_pcb as text.

usage: check_full1590xx.py BOARD.kicad_pcb [PROJECT_DIR]     exit 1 on any failure
"""
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "boardgen"))
import geometry as G  # noqa: E402
import kisch  # noqa: E402

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
TOL, TOL_LED = 0.01, 0.05


def _items(text):
    out, i = [], 0
    while True:
        j = text.find("\n\t(", i)
        if j == -1:
            return out
        b = kisch._balanced(text, j + 2)
        out.append(b)
        i = j + 2 + len(b)


def _num(s):
    return [float(v) for v in s.split()]


def _footprints(items):
    fps = {}
    for b in items:
        if not b.startswith("(footprint"):
            continue
        ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
        at = _num(re.search(r'\n\t\t\(at ([-\d. ]+)\)', b).group(1))
        x, y, rot = at[0], at[1], at[2] if len(at) > 2 else 0.0
        layer = re.search(r'\(layer "([^"]+)"\)', b).group(1)
        pads = [(m.group(1), *_num(m.group(2))[:2]) for m in re.finditer(r'\(pad "([^"]*)" \w+ \w+\s*\(at ([-\d. ]+)\)', b)]
        fps[ref] = {"x": x, "y": y, "rot": rot, "layer": layer, "pads": pads}
    return fps


def pad_abs(fp, lx, ly):
    """KiCad's footprint-local to board transform; the same on both sides (memory kicad-file-format-facts)."""
    r = math.radians(fp["rot"])
    return (fp["x"] + lx * math.cos(r) + ly * math.sin(r), fp["y"] - lx * math.sin(r) + ly * math.cos(r))


def _graphics(items, layer):
    out = []
    for b in items:
        if b.startswith("(gr_") and f'(layer "{layer}")' in b:
            kind = b[1:].split(None, 1)[0]
            pts = {k: (float(x), float(y)) for k, x, y in re.findall(r'\((start|end|mid|center) ([-\d.]+) ([-\d.]+)\)', b)}
            out.append((kind, pts))
    return out


def _pt_box(p, box):
    x0, y0, x1, y1 = box
    dx = max(x0 - p[0], 0, p[0] - x1)
    dy = max(y0 - p[1], 0, p[1] - y1)
    return math.hypot(dx, dy)


def _box_box(a, b):
    dx = max(b[0] - a[2], 0, a[0] - b[2])
    dy = max(b[1] - a[3], 0, a[1] - b[3])
    return math.hypot(dx, dy)


def _item_box_dist(kind, pts, box):
    if kind == "gr_rect":
        (sx, sy), (ex, ey) = pts["start"], pts["end"]
        return _box_box((min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)), box)
    if kind == "gr_circle":
        c, e = pts["center"], pts["end"]
        return max(_pt_box(c, box) - math.dist(c, e), 0)
    return min(_pt_box(p, box) for p in pts.values())


def _netlist_pins(project_dir: Path):
    pro = next(project_dir.glob("*.kicad_pro"))
    sch = project_dir / f"{pro.stem}.kicad_sch"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "n.net"
        subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch)],
                       check=True, capture_output=True)
        t = out.read_text()
    pins = {}
    for m in re.finditer(r'\(net\s*\(code "?\d+"?\)\s*\(name "([^"]*)"\)(.*?)\n\t\t\)', t, re.S):
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', m.group(2)):
            pins[(ref, pin)] = m.group(1)
    return pins


def check(pcb_path, project_dir=None) -> list:
    fail = []
    items = _items(Path(pcb_path).read_text())
    fps = _footprints(items)

    # guides
    circles = [(pts["center"], math.dist(pts["center"], pts["end"])) for k, pts in _graphics(items, "User.2")
               if k == "gr_circle"]
    for label, x, y, d in G.GUIDES:
        if not any(math.dist(c, (x, y)) <= TOL and abs(r - d / 2) <= TOL for c, r in circles):
            fail.append(f"User.2 guide missing: {label} at ({x}, {y}) dia {d}")
    x0, y0, x1, y1 = G.DC_GUIDE
    rects = [(min(p["start"][0], p["end"][0]), min(p["start"][1], p["end"][1]),
              max(p["start"][0], p["end"][0]), max(p["start"][1], p["end"][1]))
             for k, p in _graphics(items, "User.2") if k == "gr_rect"]
    if not any(all(abs(a - b) <= TOL for a, b in zip(r, (x0, y0, x1, y1))) for r in rects):
        fail.append(f"User.2 DC jack guide missing: rect {G.DC_GUIDE}")

    # key footprints
    for ref, (x, y, rot, layer) in G.FOOTPRINTS.items():
        fp = fps.get(ref)
        if fp is None:
            fail.append(f"{ref} missing")
            continue
        if fp["layer"] != layer:
            fail.append(f"{ref} on {fp['layer']}, expected {layer}")
        if ref == "D102":
            pads = {n: pad_abs(fp, lx, ly) for n, lx, ly in fp["pads"]}
            if "1" in pads and "2" in pads:
                c = ((pads["1"][0] + pads["2"][0]) / 2, (pads["1"][1] + pads["2"][1]) / 2)
                if math.dist(c, (x, y)) > TOL_LED:
                    fail.append(f"D102 body centre at ({c[0]:.3f}, {c[1]:.3f}), expected ({x}, {y})")
            continue
        if math.dist((fp["x"], fp["y"]), (x, y)) > TOL or (fp["rot"] - rot) % 360:
            fail.append(f"{ref} position: ({fp['x']}, {fp['y']}) rot {fp['rot']:g}, expected ({x}, {y}) rot {rot}")
    j101 = fps.get("J101")
    if j101:
        pads = {n: pad_abs(j101, lx, ly) for n, lx, ly in j101["pads"]}
        if "1" in pads and "8" in pads and not pads["1"][0] < pads["8"][0]:
            fail.append("J101 pin 1 not west of pin 8")
    for ref in G.REMOVED:
        if ref in fps:
            fail.append(f"{ref} still present")

    # outline
    edge = _graphics(items, "Edge.Cuts")
    if not edge:
        fail.append("Edge.Cuts empty")
        bottom = None
    else:
        pts = [p for _k, d in edge for p in d.values()]
        bbox = (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
        if any(abs(a - b) > TOL for a, b in zip(bbox, G.OUTLINE_BBOX)):
            fail.append(f"Edge.Cuts bbox {tuple(round(v, 3) for v in bbox)}, expected {G.OUTLINE_BBOX}")
        bottom = bbox[3]

    # clearances
    # bottom pillar bosses: User.4 items lying wholly below y 150 (not the enclosure outline that spans the box)
    pillars = [(k, d) for k, d in _graphics(items, "User.4") if d and all(p[1] > 150 for p in d.values())]
    for sx in G.SWITCH_X:
        tb = (sx + G.TINY_BOX[0], G.SWITCH_Y + G.TINY_BOX[1], sx + G.TINY_BOX[2], G.SWITCH_Y + G.TINY_BOX[3])
        if not pillars:
            fail.append("no bottom pillar bosses on User.4")
            break
        d = min(_item_box_dist(k, p, tb) for k, p in pillars)
        if d < G.CLEAR["tiny_pillar"]:
            fail.append(f"Tiny at x {sx} is {d:.2f} mm from a pillar boss")
    if bottom is not None:
        d = (G.SWITCH_Y - G.SW_COURTYARD_Y) - bottom
        if d < G.CLEAR["courtyard_edge"]:
            fail.append(f"3PDT courtyard {d:.2f} mm from the bottom edge")
        if j101:
            worst = min(bottom - (pad_abs(j101, lx, ly)[1] + G.HEADER_PAD / 2) for _n, lx, ly in j101["pads"])
            if worst < G.CLEAR["pad_edge"]:
                fail.append(f"J101 pad {worst:.2f} mm from the bottom edge")
    h = G.HEADER_PAD / 2
    for i, sx in enumerate(G.SWITCH_X):
        if i == 0 and j101:
            pad_pts = [pad_abs(j101, lx, ly) for _n, lx, ly in j101["pads"]]
        else:
            px, py = G.header_pin1(sx)
            pad_pts = [(px + G.PITCH * k, py) for k in range(G.PINS)]
        led = (sx, G.LED_Y)
        d = min(_pt_box(led, (x - h, y - h, x + h, y + h)) for x, y in pad_pts) - G.LED_FLANGE_R
        if d < G.CLEAR["led_header"]:
            fail.append(f"LED at x {sx} flange {d:.2f} mm from header pads")
        for label, gx, gy, _d in G.GUIDES:
            if label.startswith("ROW 3"):
                tb = (gx + G.TOGGLE_BOX[0], gy + G.TOGGLE_BOX[1], gx + G.TOGGLE_BOX[2], gy + G.TOGGLE_BOX[3])
                d = _pt_box(led, tb) - G.LED_FLANGE_R
                if d < G.CLEAR["led_toggle"]:
                    fail.append(f"LED at x {sx} flange {d:.2f} mm from toggle {label}")

    # zone fills: a pour saved without a refill keeps its old board's fill
    ox0, ox1, oy0, oy1 = G.OUTLINE_BBOX
    for b in items:
        if b.startswith("(zone"):
            for fp in re.findall(r"\(filled_polygon(.*?)\n\t\t\)", b, re.S):
                pts = [(float(x), float(y)) for x, y in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", fp)]
                if any(not (ox0 - TOL <= x <= ox1 + TOL and oy0 - TOL <= y <= oy1 + TOL) for x, y in pts):
                    fail.append("zone fill outside the outline (saved without a refill?)")
                    break

    # nets
    if project_dir is not None:
        pins = _netlist_pins(Path(project_dir))
        for pin, net in (("P1", "+9V"), ("P4", "+9VA")):
            got = pins.get(("BP101", pin))
            if got is None:
                fail.append(f"BP101.{pin} not in netlist")
            elif got != net:
                fail.append(f"BP101.{pin} on {got}, expected {net}")
    return fail


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    fail = check(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    for f in fail:
        print("FAIL", f)
    print("check:", "FAIL" if fail else "PASS", f"({len(fail)} failures)")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
