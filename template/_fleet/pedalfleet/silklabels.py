"""Put 2-pad passive/diode reference labels on one side of the part.

A horizontal part gets its label north (horizontal text), a vertical part gets it west
(text reading bottom-to-top), with the label's near edge GAP mm beyond the part's own pads
and front silk, whichever reaches further. That is how Andy packs them by hand (measured on
fx-Nashville, 2026-11-23: median 0.20 mm), and it lets a label sit inside its own part's
courtyard. Only 2-pad SMD R/C/D/L footprints on the front are touched; electrolytic cans,
ICs, LEDs, pots and switches are left to the designer.

A label that already sits on the right side (centred, its edge FIT_MIN-FIT_MAX mm off the
pads and silk) is kept, so hand-tuned gaps survive. A move that would land on another part's
pad, courtyard, label, silk text or silk graphic, or off the board, is not made and is
reported instead. Silk texts are checked here because the fleet DRC rules let silk overlap
pot and jack captions, so the DRC cross-check cannot see a label on "LEVEL". Only the
(at ...) of each moved Reference property is rewritten.

A cap Andy fits by hand also shows its Value on F.SilkS (0.8/0.15 mm), centred on the midpoint
of its two pad centres and reading along the part: 0 degrees for a horizontal part, 90 for a
vertical one. It is a build guide, so the part body may cover it once soldered. One already
shown within VALUE_FIT of the midpoint and clear of its pads is kept, so hand placements
(fx-Nashville's film caps sit 0.03-0.16 mm off centre) survive. Hand-fit means the footprint's
own (attr ...) carries dnp, exclude_from_bom or exclude_from_pos_files; the fleet uses them
inconsistently, so any one counts. A KiCad 10 (variant ...) block's (dnp yes) is
a per-variant choice and doesn't count, and a Value that says "DNP" marks a part left empty.
When the text can't clear its own pads by PAD_CLEARANCE (2.0-2.5 mm radial cans, 5-character
values on a 5 mm film pitch) it is reported, not printed over them. Only the Value property's
(at ...), layer, hide flag and font size/thickness are rewritten.

KiCad 10 storage facts this relies on: a footprint field's (at x y a) holds x, y in the
footprint's own frame and a as the board angle; board = fp + R(fp_rot)·local with
board x = fx + lx·cos r + ly·sin r, board y = fy − lx·sin r + ly·cos r (Y down).
"""
import math
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import kicadcli

GAP = 0.20          # mm from the part's own pads and silk to the label's near edge
FIT_MIN = -0.12     # a label whose edge sits from just over the part's own silk (hand-placed labels on
FIT_MAX = 0.80      # fx-BlueBlood/fx-Revolver touch it, -0.02..+0.02; DRC ignores a part's own silk)
                    # up to this far out, on the right side and centred, is kept
PAD_CLEARANCE = 0.15
LABEL_CLEARANCE = 0.10
EDGE_MARGIN = 0.30
CHAR_ADVANCE = 0.85  # stroke-font advance as a fraction of text height (on the generous side)
TARGET_PREFIXES = "RCDL"
HAND_FIT_FLAGS = {"dnp", "exclude_from_bom", "exclude_from_pos_files"}
VALUE_SIZE = 0.8
VALUE_THICKNESS = 0.15
AXIS_TOLERANCE = 0.01  # mm off a horizontal or vertical line between the pad centres
VALUE_FIT = 0.30       # a shown value this close to the midpoint (and clear of its pads) is kept, like a label
SILK_DRC_TYPES = ("silk_overlap", "silk_over_copper", "silk_edge_clearance")

_NUM = r"(-?[\d.]+)"
_AT = re.compile(r"\(at " + _NUM + " " + _NUM + r"(?: " + _NUM + r")?\)")


def spans(text: str, start_pattern: str):
    """Yield (start, end) of each balanced s-expression whose opening matches start_pattern."""
    for match in re.finditer(start_pattern, text):
        start = text.index("(", match.start())
        depth, pos, in_string = 0, start, False
        while pos < len(text):
            char = text[pos]
            if in_string:
                if char == "\\":
                    pos += 1
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        yield start, pos + 1


def to_board(fx, fy, frot, lx, ly):
    r = math.radians(frot)
    return fx + lx * math.cos(r) + ly * math.sin(r), fy - lx * math.sin(r) + ly * math.cos(r)


def to_local(fx, fy, frot, bx, by):
    r = math.radians(frot)
    dx, dy = bx - fx, by - fy
    return dx * math.cos(r) - dy * math.sin(r), dx * math.sin(r) + dy * math.cos(r)


@dataclass
class Pad:
    lx: float
    ly: float
    angle: float  # board angle
    w: float
    h: float
    smd: bool


@dataclass
class Footprint:
    ref: str
    lib: str
    layer: str
    fx: float
    fy: float
    frot: float
    pads: list = field(default_factory=list)
    courtyard: list = field(default_factory=list)  # local (x, y) points
    label: dict | None = None  # lx, ly, angle, layer, size, hidden, span (absolute in board text)
    value: dict | None = None  # the Value property, same keys as label plus text and width
    attrs: set = field(default_factory=set)  # the footprint's own (attr ...) tokens
    silk: list = field(default_factory=list)   # front silk graphics: (kind, local points, stroke width)
    texts: list = field(default_factory=list)  # visible front silk texts other than the Reference label

    def is_target(self) -> bool:
        return (self.label is not None and len(self.pads) == 2 and all(p.smd for p in self.pads)
                and self.ref[:1] in TARGET_PREFIXES and self.ref[1:2].isdigit()
                and not self.lib.split(":")[-1].startswith("CP_")
                and self.layer == "F.Cu" and self.label["layer"] == "F.SilkS" and not self.label["hidden"])

    def body(self):
        """Board-frame bounding box of the courtyard (pads when there is none)."""
        points = list(self.courtyard)
        if not points:
            for pad in self.pads:
                points += [(pad.lx + sx * pad.w / 2, pad.ly + sy * pad.h / 2) for sx in (-1, 1) for sy in (-1, 1)]
        board = [to_board(self.fx, self.fy, self.frot, x, y) for x, y in points]
        xs, ys = [p[0] for p in board], [p[1] for p in board]
        return min(xs), min(ys), max(xs), max(ys)

    def pad_boxes(self):
        boxes = []
        for pad in self.pads:
            r = math.radians(pad.angle)
            half_w = abs(pad.w / 2 * math.cos(r)) + abs(pad.h / 2 * math.sin(r))
            half_h = abs(pad.w / 2 * math.sin(r)) + abs(pad.h / 2 * math.cos(r))
            x, y = to_board(self.fx, self.fy, self.frot, pad.lx, pad.ly)
            boxes.append((x - half_w, y - half_h, x + half_w, y + half_h))
        return boxes

    def silk_boxes(self):
        """Board-frame boxes of the front silk graphics: one per line or outline edge; circles and arcs by extent."""
        boxes = []
        for kind, points, width in self.silk:
            board = [to_board(self.fx, self.fy, self.frot, x, y) for x, y in points]
            half = width / 2
            if kind == "circle" and len(board) == 2:
                (cx, cy), (ex, ey) = board
                r = math.hypot(ex - cx, ey - cy) + half
                boxes.append((cx - r, cy - r, cx + r, cy + r))
                continue
            if kind == "rect" and len(board) == 2:
                corners = [points[0], (points[1][0], points[0][1]), points[1], (points[0][0], points[1][1])]
                board = [to_board(self.fx, self.fy, self.frot, x, y) for x, y in corners]
            if kind in ("rect", "poly"):
                edges = list(zip(board, board[1:] + board[:1]))
            elif kind == "line" and len(board) == 2:
                edges = [(board[0], board[1])]
            else:  # arc: start, mid, end
                xs, ys = [p[0] for p in board], [p[1] for p in board]
                boxes.append((min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half))
                continue
            for (ax, ay), (bx, by) in edges:
                boxes.append((min(ax, bx) - half, min(ay, by) - half, max(ax, bx) + half, max(ay, by) + half))
        return boxes

    def envelope(self):
        """Board-frame box around the part's own pads and front silk: what its label is spaced from."""
        boxes = self.pad_boxes() + self.silk_boxes()
        if not boxes:
            return self.body()
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    def text_boxes(self, skip_value=False):
        boxes = []
        for text in self.texts:
            if skip_value and text["name"] == "Value":
                continue
            x, y = to_board(self.fx, self.fy, self.frot, text["lx"], text["ly"])
            boxes.append(label_box(x, y, text["text"], text["size"], text["thickness"], text["angle"] % 180 != 0))
        return boxes

    def label_position(self):
        x, y = to_board(self.fx, self.fy, self.frot, self.label["lx"], self.label["ly"])
        return x, y, self.label["angle"] % 180 != 0

    def is_value_target(self) -> bool:
        """A 2-pad front cap Andy solders himself (any hand-fit flag on its own attr)."""
        return (self.value is not None and len(self.pads) == 2 and self.layer == "F.Cu"
                and self.ref[:1] == "C" and self.ref[1:2].isdigit() and bool(self.attrs & HAND_FIT_FLAGS))

    def value_box(self):
        """The Value's current box when it shows on the front silk, else None."""
        value = self.value
        if value["layer"] != "F.SilkS" or value["hidden"]:
            return None
        x, y = to_board(self.fx, self.fy, self.frot, value["lx"], value["ly"])
        return label_box(x, y, value["text"], value["size"], value["thickness"], value["angle"] % 180 != 0)


def _field(prop: str, span: tuple) -> dict:
    """The parts of a footprint property (Reference, Value) the planner reads; span is absolute."""
    pat = _AT.search(prop)
    size = re.search(r"\(size " + _NUM + " " + _NUM + r"\)", prop)
    thickness = re.search(r"\(thickness " + _NUM + r"\)", prop)
    return dict(text=re.match(r'\(property "[^"]*" "([^"]*)"', prop).group(1),
                lx=float(pat.group(1)), ly=float(pat.group(2)), angle=float(pat.group(3) or 0),
                layer=re.search(r'\(layer "([^"]+)"\)', prop).group(1),
                width=float(size.group(1)) if size else 1.0, size=float(size.group(2)) if size else 1.0,
                thickness=float(thickness.group(1)) if thickness else 0.15,
                has_font=bool(size and thickness), hidden="(hide yes)" in prop, span=span)


def parse_footprints(text: str) -> list:
    footprints = []
    for start, end in spans(text, r"\n\t\(footprint \""):
        block = text[start:end]
        at = re.search(r"\n\t\t\(at " + _NUM + " " + _NUM + r"(?: " + _NUM + r")?\)", block)
        fp = Footprint(ref="", lib=re.match(r'\(footprint "([^"]*)"', block).group(1),
                       layer=re.search(r'\n\t\t\(layer "([^"]+)"\)', block).group(1),
                       fx=float(at.group(1)), fy=float(at.group(2)), frot=float(at.group(3) or 0))
        for ps, pe in spans(block, r'\n\t\t\(property "Reference"'):
            fp.label = _field(block[ps:pe], (start + ps, start + pe))
            fp.ref = fp.label["text"]
        for ps, pe in spans(block, r'\n\t\t\(property "Value"'):
            fp.value = _field(block[ps:pe], (start + ps, start + pe))
        attr = re.search(r"\n\t\t\(attr ([^)]*)\)", block)
        fp.attrs = set(attr.group(1).split()) if attr else set()
        for ps, pe in spans(block, r'\n\t\t\(pad "'):
            pad = block[ps:pe]
            pat = _AT.search(pad)
            size = re.search(r"\(size " + _NUM + " " + _NUM + r"\)", pad)
            fp.pads.append(Pad(float(pat.group(1)), float(pat.group(2)), float(pat.group(3) or 0),
                               float(size.group(1)), float(size.group(2)),
                               re.match(r'\(pad "[^"]*" (\w+)', pad).group(1) == "smd"))
        for gs, ge in spans(block, r"\n\t\t\(fp_(?:line|rect|poly|circle|arc)"):
            shape = block[gs:ge]
            points = [(float(x), float(y)) for x, y in
                      re.findall(r"\((?:start|end|xy|mid|center) " + _NUM + " " + _NUM + r"\)", shape)]
            if "CrtYd" in shape:
                fp.courtyard += points
            elif '(layer "F.SilkS")' in shape:
                kind = re.match(r"\(fp_(\w+)", shape).group(1)
                width = re.search(r"\(width " + _NUM + r"\)", shape)
                fp.silk.append((kind, points, float(width.group(1)) if width else 0.12))
        properties = {name.lower(): value for name, value in re.findall(r'\n\t\t\(property "([^"]+)" "([^"]*)"', block)}
        for ts, te in spans(block, r'\n\t\t\((?:property "(?!Reference")|fp_text )'):
            item = block[ts:te]
            if '(layer "F.SilkS")' not in item or "(hide yes)" in item:
                continue
            words = re.match(r'\((?:property "([^"]*)"|fp_text \w+) "([^"]*)"', item)
            pat = _AT.search(item)
            if not words or not pat:
                continue
            shown = re.sub(r"\$\{(\w+)\}", lambda m: properties.get(m.group(1).lower(), m.group(0)), words.group(2))
            if not shown.strip():
                continue
            size = re.search(r"\(size " + _NUM + " " + _NUM + r"\)", item)
            thickness = re.search(r"\(thickness " + _NUM + r"\)", item)
            fp.texts.append(dict(name=words.group(1) or "fp_text", text=shown,
                                 lx=float(pat.group(1)), ly=float(pat.group(2)),
                                 angle=float(pat.group(3) or 0), size=float(size.group(2)) if size else 1.0,
                                 thickness=float(thickness.group(1)) if thickness else 0.15))
        footprints.append(fp)
    return footprints


def board_outline(text: str):
    points = []
    for start, end in spans(text, r"\n\t\(gr_(?:line|arc|rect|poly|circle)"):
        shape = text[start:end]
        if '"Edge.Cuts"' in shape:
            points += [(float(x), float(y)) for x, y in
                       re.findall(r"\((?:start|end|mid|xy) " + _NUM + " " + _NUM + r"\)", shape)]
    if not points:
        return None
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def label_box(x, y, text, size, thickness, vertical):
    width, height = len(text) * CHAR_ADVANCE * size + thickness, size + thickness
    if vertical:
        width, height = height, width
    return x - width / 2, y - height / 2, x + width / 2, y + height / 2


def overlaps(a, b, clearance=0.0):
    return not (a[2] + clearance <= b[0] or b[2] + clearance <= a[0]
                or a[3] + clearance <= b[1] or b[3] + clearance <= a[1])


@dataclass
class Plan:
    action: str                    # keep | move | blocked | skip
    box: tuple                     # label box the other checks should see
    target: tuple | None = None    # (x, y, vertical) for a move, or the wanted spot when blocked
    reason: str = ""
    current_box: tuple | None = None
    text: str = ""                 # what the field shows (value plans)


def plan_labels(footprints, outline=None, gap=GAP, skip=(), blocked=None) -> dict:
    """Plan every target label. blocked maps ref -> reason for moves already known to be bad."""
    blocked = blocked or {}
    targets = [fp for fp in footprints if fp.is_target()]
    plans = {}
    for fp in targets:
        x0, y0, x1, y1 = fp.body()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        horizontal = (x1 - x0) >= (y1 - y0)
        ex0, ey0, _, _ = fp.envelope()
        lx, ly, vertical_now = fp.label_position()
        size, thick = fp.label["size"], fp.label["thickness"]
        half = (size + thick) / 2  # half the text height: the label's depth away from the part
        current = label_box(lx, ly, fp.ref, size, thick, vertical_now)
        if horizontal:
            fits = not vertical_now and abs(lx - cx) <= 0.3 and FIT_MIN <= ey0 - current[3] <= FIT_MAX
            target = (cx, ey0 - gap - half, False)
        else:
            fits = vertical_now and abs(ly - cy) <= 0.3 and FIT_MIN <= ex0 - current[2] <= FIT_MAX
            target = (ex0 - gap - half, cy, True)
        if fits:
            plans[fp.ref] = Plan("keep", current)
        elif fp.ref in skip:
            plans[fp.ref] = Plan("skip", current, reason="skipped by request")
        elif fp.ref in blocked:
            plans[fp.ref] = Plan("blocked", current, target, blocked[fp.ref])
        else:
            plans[fp.ref] = Plan("move", label_box(target[0], target[1], fp.ref, size, thick, target[2]),
                                 target, current_box=current)

    pads = [(fp.ref, box) for fp in footprints for box in fp.pad_boxes()]
    courtyards = [(fp.ref, fp.body()) for fp in footprints if fp.courtyard]
    texts = [(fp.ref, box) for fp in footprints for box in fp.text_boxes()]
    silk = [(fp.ref, box) for fp in footprints for box in fp.silk_boxes()]
    fixed_labels = []
    for fp in footprints:
        if fp.label and not fp.is_target() and fp.label["layer"] == "F.SilkS" and not fp.label["hidden"]:
            x, y, vertical = fp.label_position()
            fixed_labels.append((fp.ref, label_box(x, y, fp.ref, fp.label["size"], fp.label["thickness"], vertical)))

    changed = True
    while changed:  # a blocked move falls back to its old box, which can block another
        changed = False
        for ref, plan in plans.items():
            if plan.action != "move":
                continue
            reason = _collision(ref, plan.box, outline, pads, courtyards, fixed_labels, plans, texts, silk)
            if reason:
                plans[ref] = Plan("blocked", plan.current_box or plan.box, plan.target, reason)
                changed = True
    return plans


def plan_values(footprints, outline=None, label_plans=None, skip=(), blocked=None) -> dict:
    """Plan the Value of every hand-fit cap: centred between its pad centres, upright along the part.

    label_plans are the planned Reference labels, whose final boxes are in the way. blocked maps
    ref -> reason for placements already known to be bad (the DRC cross-check). Labels are planned
    first and don't see the values: a value sits between its own pads, where no label goes.
    """
    label_plans = label_plans or {}
    blocked = blocked or {}
    plans = {}
    for fp in footprints:
        if not fp.is_value_target():
            continue
        value, current = fp.value, fp.value_box()
        text = value["text"]
        if "DNP" in text.upper():
            plans[fp.ref] = Plan("skip", current, reason=f'value "{text}" marks it not fitted')
            continue
        if not text.strip() or text == "~":
            plans[fp.ref] = Plan("skip", current, reason="no value to show")
            continue
        (ax, ay), (bx, by) = (to_board(fp.fx, fp.fy, fp.frot, pad.lx, pad.ly) for pad in fp.pads)
        if abs(ay - by) <= AXIS_TOLERANCE < abs(ax - bx):
            vertical = False
        elif abs(ax - bx) <= AXIS_TOLERANCE < abs(ay - by):
            vertical = True
        else:
            plans[fp.ref] = Plan("blocked", current, reason="part sits at an angle: place it by hand")
            continue
        target = ((ax + bx) / 2, (ay + by) / 2, vertical)
        box = label_box(target[0], target[1], text, VALUE_SIZE, VALUE_THICKNESS, vertical)
        fits = (current is not None and value["angle"] % 360 == (90 if vertical else 0)
                and abs((current[0] + current[2]) / 2 - target[0]) <= VALUE_FIT
                and abs((current[1] + current[3]) / 2 - target[1]) <= VALUE_FIT
                and value["size"] == value["width"] == VALUE_SIZE and value["thickness"] == VALUE_THICKNESS
                and not any(overlaps(current, pad, PAD_CLEARANCE) for pad in fp.pad_boxes()))
        if fits:
            plans[fp.ref] = Plan("keep", box)
        elif fp.ref in skip:
            plans[fp.ref] = Plan("skip", current, reason="skipped by request")
        elif fp.ref in blocked:
            plans[fp.ref] = Plan("blocked", current, target, blocked[fp.ref])
        elif any(overlaps(box, pad, PAD_CLEARANCE) for pad in fp.pad_boxes()):
            axis = 1 if vertical else 0
            first, second = sorted(fp.pad_boxes(), key=lambda pad: pad[axis])
            room = second[axis] - first[axis + 2] - 2 * PAD_CLEARANCE
            plans[fp.ref] = Plan("blocked", current, target, f"too tight: {box[axis + 2] - box[axis]:.1f} mm "
                                 f"of text, {max(room, 0):.1f} mm free between the pads")
        elif not value["has_font"]:
            plans[fp.ref] = Plan("blocked", current, target, "Value has no font size/thickness: set it in KiCad")
        else:
            plans[fp.ref] = Plan("place", box, target, current_box=current)

    pads = [(fp.ref, box) for fp in footprints for box in fp.pad_boxes()]
    silk = [(fp.ref, box) for fp in footprints for box in fp.silk_boxes()]
    texts = [(fp.ref, box) for fp in footprints for box in fp.text_boxes(skip_value=fp.ref in plans)]
    labels = [(ref, plan.box) for ref, plan in label_plans.items()]
    for fp in footprints:
        if fp.label and fp.ref not in label_plans and fp.label["layer"] == "F.SilkS" and not fp.label["hidden"]:
            x, y, vertical = fp.label_position()
            labels.append((fp.ref, label_box(x, y, fp.ref, fp.label["size"], fp.label["thickness"], vertical)))

    changed = True
    while changed:  # a blocked value falls back to its old spot, which can block another
        changed = False
        for ref, plan in plans.items():
            if plan.action != "place":
                continue
            reason = _value_collision(ref, plan.box, outline, pads, labels, plans, texts, silk)
            if reason:
                plans[ref] = Plan("blocked", plan.current_box, plan.target, reason)
                changed = True
    shown = {fp.ref: fp.value["text"] for fp in footprints if fp.ref in plans}
    for ref, plan in plans.items():
        plan.text = shown[ref]
    return plans


def _value_collision(ref, box, outline, pads, labels, plans, texts, silk) -> str:
    """Why a value can't sit here. Its own pads were checked already; its own silk outline and
    courtyard don't count (it sits under its own body), but its own Reference label does."""
    if outline and not (box[0] >= outline[0] + EDGE_MARGIN and box[1] >= outline[1] + EDGE_MARGIN
                        and box[2] <= outline[2] - EDGE_MARGIN and box[3] <= outline[3] - EDGE_MARGIN):
        return "board edge"
    values = [(other, plan.box) for other, plan in plans.items() if plan.box]
    for kind, items, clearance, own in (("pad", pads, PAD_CLEARANCE, False), ("label", labels, LABEL_CLEARANCE, True),
                                        ("value", values, LABEL_CLEARANCE, False), ("text", texts, LABEL_CLEARANCE, True),
                                        ("silk", silk, LABEL_CLEARANCE, False)):
        hits = sorted({other for other, item in items if (own or other != ref) and overlaps(box, item, clearance)})
        if hits:
            return f"{kind} of " + ",".join(hits)
    return ""


def _collision(ref, box, outline, pads, courtyards, fixed_labels, plans, texts=(), silk=()) -> str:
    """Why a label box can't go here. The part's own pads, silk and courtyard don't count: the
    target already clears its pads and silk by the gap, and a label may sit in its own courtyard."""
    if outline and not (box[0] >= outline[0] + EDGE_MARGIN and box[1] >= outline[1] + EDGE_MARGIN
                        and box[2] <= outline[2] - EDGE_MARGIN and box[3] <= outline[3] - EDGE_MARGIN):
        return "board edge"
    hits = sorted({other for other, pad in pads if other != ref and overlaps(box, pad, PAD_CLEARANCE)})
    if hits:
        return "pad of " + ",".join(hits)
    hits = sorted({other for other, court in courtyards if other != ref and overlaps(box, court)})
    if hits:
        return "inside courtyard of " + ",".join(hits)
    hits = {other for other, label in fixed_labels if overlaps(box, label, LABEL_CLEARANCE)}
    hits |= {other for other, plan in plans.items() if other != ref and overlaps(box, plan.box, LABEL_CLEARANCE)}
    if hits:
        return "label of " + ",".join(sorted(hits))
    hits = sorted({other for other, text in texts if overlaps(box, text, LABEL_CLEARANCE)})
    if hits:
        return "text of " + ",".join(hits)
    hits = sorted({other for other, graphic in silk if other != ref and overlaps(box, graphic, LABEL_CLEARANCE)})
    if hits:
        return "silk of " + ",".join(hits)
    return ""


def _fmt(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def rewrite(text: str, footprints, plans, value_plans=None) -> str:
    """Return text with only the moved labels' (at ...) and the placed values' fields replaced."""
    edits = []
    for fp in footprints:
        plan = (value_plans or {}).get(fp.ref)
        if plan is None or plan.action != "place" or not fp.is_value_target():
            continue
        start, end = fp.value["span"]
        lx, ly = (fp.pads[0].lx + fp.pads[1].lx) / 2, (fp.pads[0].ly + fp.pads[1].ly) / 2
        prop, at = _AT.subn(f"(at {_fmt(lx)} {_fmt(ly)} {'90' if plan.target[2] else '0'})", text[start:end], count=1)
        prop, layer = re.subn(r'\(layer "[^"]+"\)', '(layer "F.SilkS")', prop, count=1)
        prop = re.sub(r"\n\t*\(hide yes\)", "", prop, count=1)
        prop, size = re.subn(r"\(size " + _NUM + " " + _NUM + r"\)", f"(size {_fmt(VALUE_SIZE)} {_fmt(VALUE_SIZE)})",
                             prop, count=1)
        prop, thickness = re.subn(r"\(thickness " + _NUM + r"\)", f"(thickness {_fmt(VALUE_THICKNESS)})", prop, count=1)
        if (at, layer, size, thickness) != (1, 1, 1, 1):
            raise RuntimeError(f"{fp.ref}: value field lacks (at), (layer), (size) or (thickness)")
        edits.append((start, end, prop))
    for fp in footprints:
        plan = plans.get(fp.ref)
        if plan is None or plan.action != "move" or not fp.is_target():
            continue
        x, y, vertical = plan.target
        lx, ly = to_local(fp.fx, fp.fy, fp.frot, x, y)
        start, end = fp.label["span"]
        prop, count = _AT.subn(f"(at {_fmt(lx)} {_fmt(ly)} {'90' if vertical else '0'})", text[start:end], count=1)
        if count != 1:
            raise RuntimeError(f"{fp.ref}: reference field has no (at ...)")
        edits.append((start, end, prop))
    for start, end, prop in sorted(edits, reverse=True):
        text = text[:start] + prop + text[end:]
    return text


@dataclass
class Result:
    plans: dict
    text: str                       # the board text to write (unchanged when nothing moved)
    drc_checked: bool = False
    silk_before: Counter = field(default_factory=Counter)
    silk_after: Counter = field(default_factory=Counter)
    new_violations: set = field(default_factory=set)
    values: dict = field(default_factory=dict)  # ref -> Plan for each hand-fit cap's Value

    def count(self, action: str) -> int:
        return sum(1 for plan in self.plans.values() if plan.action == action)

    def count_values(self, action: str) -> int:
        return sum(1 for plan in self.values.values() if plan.action == action)


def run(pcb: Path, pro: Path | None = None, gap: float = GAP, skip=(), kicad_cli: Path | None = None,
        drc=None, max_rounds: int = 3, values: bool = True) -> Result:
    """Plan and rewrite one board; with kicad_cli, put back any label move or placed value that
    adds a silk DRC violation. values=False leaves the hand-fit caps' values alone.

    drc(kicad_cli, pcb_path, out_json) -> report is injectable for tests. The default runs kicad-cli
    without --refill-zones: silk findings don't depend on zone fill, and the runs stay sequential
    (kicad-cli peaks around 1.6 GB on a pedal-sized board).
    """
    text = pcb.read_text(encoding="utf-8")
    footprints = parse_footprints(text)
    outline = board_outline(text)
    blocked, value_blocked = {}, {}

    def replan():
        labels = plan_labels(footprints, outline, gap, skip, blocked)
        placed = plan_values(footprints, outline, labels, skip, value_blocked) if values else {}
        return labels, placed, rewrite(text, footprints, labels, placed)

    plans, value_plans, new_text = replan()
    result = Result(plans, new_text, values=value_plans)
    if kicad_cli is None or new_text == text:
        return result
    drc = drc or (lambda cli, board, out: kicadcli.run_drc(cli, board, out, refill_zones=False))
    with tempfile.TemporaryDirectory() as tmp:
        before = _check(drc, kicad_cli, Path(tmp) / "before", pcb.name, pro, text)
        for _ in range(max_rounds):
            after = _check(drc, kicad_cli, Path(tmp) / "after", pcb.name, pro, new_text)
            moved = {ref for ref, plan in plans.items() if plan.action == "move"}
            placed = {f"{ref} value" for ref, plan in value_plans.items() if plan.action == "place"}
            culprits, value_culprits = {}, {}
            for kind, refs in after - before:
                for ref in refs:
                    others = ",".join(r for r in refs if r != ref) or ref
                    if ref in moved:
                        culprits[ref] = f"DRC {kind} with {others}"
                    elif ref in placed:
                        value_culprits[ref.removesuffix(" value")] = f"DRC {kind} with {others}"
            if not culprits and not value_culprits:
                break
            blocked.update(culprits)
            value_blocked.update(value_culprits)
            plans, value_plans, new_text = replan()
        result = Result(plans, new_text, True, Counter(kind for kind, _ in before),
                        Counter(kind for kind, _ in after), after - before, value_plans)
    return result


def _check(drc, kicad_cli, directory: Path, name: str, pro: Path | None, text: str) -> set:
    directory.mkdir(parents=True, exist_ok=True)
    board = directory / name
    board.write_text(text, encoding="utf-8")
    if pro is not None and pro.exists():
        shutil.copy(pro, board.with_suffix(".kicad_pro"))
    return silk_violations(drc(kicad_cli, board, directory / "drc.json"))


def silk_violations(report: dict) -> set:
    """{(type, (refA, refB…))} for the silkscreen violations in a kicad-cli DRC JSON report.

    A Value field shows as "C12 value" ("Value field of C12 (330nF)"), so a value is told apart
    from its part's Reference label; an item no part owns keeps its description, so a report can
    name the board text or edge a label or value ran into.
    """
    found = set()
    for violation in report.get("violations", []):
        if violation.get("type") in SILK_DRC_TYPES and not violation.get("excluded"):
            refs = []
            for item in violation.get("items", []):
                description = item.get("description", "")
                value = re.match(r"Value field of (\S+)", description)
                match = re.search(r" of (\S+?)(?: on |$)", description)
                if value:
                    refs.append(value.group(1) + " value")
                elif match:
                    refs.append(match.group(1))
                elif description:  # a board item such as "PCB text '2 x 2.2u Film' on F.Silkscreen"
                    refs.append(" ".join(description.split()))
            found.add((violation["type"], tuple(sorted(refs))))
    return found
