"""Put 2-pad passive/diode reference labels on one side of the part.

A horizontal part gets its label north (horizontal text), a vertical part gets it west
(text reading bottom-to-top), with the text centre GAP mm beyond the courtyard edge, the
spacing KiCad's own libraries use. Only 2-pad SMD R/C/D/L footprints on the front are
touched; electrolytic cans, ICs, LEDs, pots and switches are left to the designer.

A label that already sits on the right side (centred, 0.1-1.0 mm out) is kept, so
hand-tuned gaps survive. A move that would land on a pad, inside another part's
courtyard, on another label or off the board is not made and is reported instead.
Only the (at ...) of each moved Reference property is rewritten.

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

GAP = 0.70          # mm from courtyard edge to text centre
PAD_CLEARANCE = 0.15
LABEL_CLEARANCE = 0.10
EDGE_MARGIN = 0.30
CHAR_ADVANCE = 0.85  # stroke-font advance as a fraction of text height (on the generous side)
TARGET_PREFIXES = "RCDL"
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

    def label_position(self):
        x, y = to_board(self.fx, self.fy, self.frot, self.label["lx"], self.label["ly"])
        return x, y, self.label["angle"] % 180 != 0


def parse_footprints(text: str) -> list:
    footprints = []
    for start, end in spans(text, r"\n\t\(footprint \""):
        block = text[start:end]
        at = re.search(r"\n\t\t\(at " + _NUM + " " + _NUM + r"(?: " + _NUM + r")?\)", block)
        fp = Footprint(ref="", lib=re.match(r'\(footprint "([^"]*)"', block).group(1),
                       layer=re.search(r'\n\t\t\(layer "([^"]+)"\)', block).group(1),
                       fx=float(at.group(1)), fy=float(at.group(2)), frot=float(at.group(3) or 0))
        for ps, pe in spans(block, r'\n\t\t\(property "Reference"'):
            prop = block[ps:pe]
            pat = _AT.search(prop)
            size = re.search(r"\(size " + _NUM + " " + _NUM + r"\)", prop)
            thickness = re.search(r"\(thickness " + _NUM + r"\)", prop)
            fp.ref = re.match(r'\(property "Reference" "([^"]*)"', prop).group(1)
            fp.label = dict(lx=float(pat.group(1)), ly=float(pat.group(2)), angle=float(pat.group(3) or 0),
                            layer=re.search(r'\(layer "([^"]+)"\)', prop).group(1),
                            size=float(size.group(2)) if size else 1.0,
                            thickness=float(thickness.group(1)) if thickness else 0.15,
                            hidden="(hide yes)" in prop, span=(start + ps, start + pe))
        for ps, pe in spans(block, r'\n\t\t\(pad "'):
            pad = block[ps:pe]
            pat = _AT.search(pad)
            size = re.search(r"\(size " + _NUM + " " + _NUM + r"\)", pad)
            fp.pads.append(Pad(float(pat.group(1)), float(pat.group(2)), float(pat.group(3) or 0),
                               float(size.group(1)), float(size.group(2)),
                               re.match(r'\(pad "[^"]*" (\w+)', pad).group(1) == "smd"))
        for gs, ge in spans(block, r"\n\t\t\(fp_(?:line|rect|poly|circle|arc)"):
            shape = block[gs:ge]
            if "CrtYd" in shape:
                fp.courtyard += [(float(x), float(y)) for x, y in
                                 re.findall(r"\((?:start|end|xy|mid|center) " + _NUM + " " + _NUM + r"\)", shape)]
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


def plan_labels(footprints, outline=None, gap=GAP, skip=(), blocked=None) -> dict:
    """Plan every target label. blocked maps ref -> reason for moves already known to be bad."""
    blocked = blocked or {}
    targets = [fp for fp in footprints if fp.is_target()]
    plans = {}
    for fp in targets:
        x0, y0, x1, y1 = fp.body()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        horizontal = (x1 - x0) >= (y1 - y0)
        lx, ly, vertical_now = fp.label_position()
        size, thick = fp.label["size"], fp.label["thickness"]
        current = label_box(lx, ly, fp.ref, size, thick, vertical_now)
        if horizontal:
            fits = not vertical_now and abs(lx - cx) <= 0.3 and 0.1 <= y0 - ly <= 1.0
            target = (cx, y0 - gap, False)
        else:
            fits = vertical_now and abs(ly - cy) <= 0.3 and 0.1 <= x0 - lx <= 1.0
            target = (x0 - gap, cy, True)
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
            reason = _collision(ref, plan.box, outline, pads, courtyards, fixed_labels, plans)
            if reason:
                plans[ref] = Plan("blocked", plan.current_box or plan.box, plan.target, reason)
                changed = True
    return plans


def _collision(ref, box, outline, pads, courtyards, fixed_labels, plans) -> str:
    if outline and not (box[0] >= outline[0] + EDGE_MARGIN and box[1] >= outline[1] + EDGE_MARGIN
                        and box[2] <= outline[2] - EDGE_MARGIN and box[3] <= outline[3] - EDGE_MARGIN):
        return "board edge"
    hits = sorted({other for other, pad in pads if overlaps(box, pad, PAD_CLEARANCE)})
    if hits:
        return "pad of " + ",".join(hits)
    hits = sorted({other for other, court in courtyards if other != ref and overlaps(box, court)})
    if hits:
        return "inside courtyard of " + ",".join(hits)
    hits = {other for other, label in fixed_labels if overlaps(box, label, LABEL_CLEARANCE)}
    hits |= {other for other, plan in plans.items() if other != ref and overlaps(box, plan.box, LABEL_CLEARANCE)}
    if hits:
        return "label of " + ",".join(sorted(hits))
    return ""


def _fmt(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def rewrite(text: str, footprints, plans) -> str:
    """Return text with only the moved labels' (at ...) replaced."""
    edits = []
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

    def count(self, action: str) -> int:
        return sum(1 for plan in self.plans.values() if plan.action == action)


def run(pcb: Path, pro: Path | None = None, gap: float = GAP, skip=(), kicad_cli: Path | None = None,
        drc=None, max_rounds: int = 3) -> Result:
    """Plan and rewrite one board; with kicad_cli, put back any move that adds a silk DRC violation.

    drc(kicad_cli, pcb_path, out_json) -> report is injectable for tests. The default runs kicad-cli
    without --refill-zones: silk findings don't depend on zone fill, and the runs stay sequential
    (kicad-cli peaks around 1.6 GB on a pedal-sized board).
    """
    text = pcb.read_text(encoding="utf-8")
    footprints = parse_footprints(text)
    outline = board_outline(text)
    blocked = {}
    plans = plan_labels(footprints, outline, gap, skip, blocked)
    new_text = rewrite(text, footprints, plans)
    result = Result(plans, new_text)
    if kicad_cli is None or new_text == text:
        return result
    drc = drc or (lambda cli, board, out: kicadcli.run_drc(cli, board, out, refill_zones=False))
    with tempfile.TemporaryDirectory() as tmp:
        before = _check(drc, kicad_cli, Path(tmp) / "before", pcb.name, pro, text)
        for _ in range(max_rounds):
            after = _check(drc, kicad_cli, Path(tmp) / "after", pcb.name, pro, new_text)
            moved = {ref for ref, plan in plans.items() if plan.action == "move"}
            culprits = {}
            for kind, refs in after - before:
                for ref in refs:
                    if ref in moved:
                        others = ",".join(r for r in refs if r != ref) or ref
                        culprits[ref] = f"DRC {kind} with {others}"
            if not culprits:
                break
            blocked.update(culprits)
            plans = plan_labels(footprints, outline, gap, skip, blocked)
            new_text = rewrite(text, footprints, plans)
        result = Result(plans, new_text, True, Counter(kind for kind, _ in before),
                        Counter(kind for kind, _ in after), after - before)
    return result


def _check(drc, kicad_cli, directory: Path, name: str, pro: Path | None, text: str) -> set:
    directory.mkdir(parents=True, exist_ok=True)
    board = directory / name
    board.write_text(text, encoding="utf-8")
    if pro is not None and pro.exists():
        shutil.copy(pro, board.with_suffix(".kicad_pro"))
    return silk_violations(drc(kicad_cli, board, directory / "drc.json"))


def silk_violations(report: dict) -> set:
    """{(type, (refA, refB…))} for the silkscreen violations in a kicad-cli DRC JSON report."""
    found = set()
    for violation in report.get("violations", []):
        if violation.get("type") in SILK_DRC_TYPES and not violation.get("excluded"):
            refs = []
            for item in violation.get("items", []):
                match = re.search(r" of (\S+?)(?: on |$)", item.get("description", ""))
                if match:
                    refs.append(match.group(1))
            found.add((violation["type"], tuple(sorted(refs))))
    return found
