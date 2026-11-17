"""Check and heal a KiCad board outline (Edge.Cuts) at the micrometre level.

KiCad's DRC chains Edge.Cuts ends that lie within its own tolerance, so a 10 um gap or
a 20 um stub left by stretching or filleting an edge passes DRC and then breaks stricter
consumers (the kicad-live tidy planner, fab CAM, STEP export). This module reads every
board-level Edge.Cuts gr_line, gr_arc, gr_rect, gr_circle, gr_poly and gr_curve, plus
footprint Edge.Cuts as read-only context, compares coordinates as integer nanometres
(KiCad's own unit) and plans a deterministic heal:

1. a line or arc no longer than the tolerance is a stub: it is dropped;
2. two ends within the tolerance but not identical are a gap: they are snapped onto one
   point. A line end moves onto an arc, curve or footprint end, never the reverse
   (moving an arc end changes its radius and centre); between two lines the end on the
   coarser grid stays;
3. two lines that meet end to end on one straight line are merged into one;
4. an end with no partner within the tolerance is a real open outline: it is reported,
   never healed.

Only the (start ...)/(end ...) tokens that change are rewritten and only dropped shapes
are removed, so git diff stays minimal. A healed outline must close exactly, at zero
tolerance, into one board polygon plus cutouts that neither cross nor nest.
"""
import bisect
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .silklabels import spans, to_board

TOL = 0.05            # mm: default heal tolerance
NM = 1_000_000        # nm per mm
COLLINEAR_NM = 1_000  # a joint within 1 um of the merged chord counts as collinear
# Grid pitches, coarsest first (mm and mil grids), for "keep the end on the coarser grid".
GRID_STEPS_NM = (2_540_000, 1_270_000, 1_000_000, 635_000, 500_000, 254_000, 250_000, 127_000,
                 100_000, 50_000, 25_400, 25_000, 10_000, 5_000, 2_540, 1_000, 100, 10, 1)
OPEN_KINDS = ("line", "arc", "curve")
ARC_STEP = math.radians(5)   # polygonisation step for arcs and circles
CROSS_EPS = 1e-9             # mm^2: cross products below this count as zero

_NUM = r"(-?[\d.]+)"
_POINT = re.compile(r"\((start|mid|end|center) " + _NUM + " " + _NUM + r"\)")
_PTS_ITEM = re.compile(r"\(xy " + _NUM + " " + _NUM + r"\)|\(arc\s*\(start " + _NUM + " " + _NUM
                       + r"\)\s*\(mid " + _NUM + " " + _NUM + r"\)\s*\(end " + _NUM + " " + _NUM + r"\)\s*\)")
_UUID = re.compile(r'\((?:uuid|tstamp) "?([^")\s]+)"?\)')
_EDGE = '(layer "Edge.Cuts")'


def to_nm(value: str) -> int:
    return int((Decimal(value) * NM).to_integral_value())


def fmt_nm(nm: int) -> str:
    """KiCad's own number format: mm, up to six decimals, no trailing zeros."""
    whole, frac = divmod(abs(nm), NM)
    text = f"{whole}.{frac:06d}".rstrip("0").rstrip(".") if frac else str(whole)
    return "-" + text if nm < 0 else text


def fmt_point(point) -> str:
    return f"({fmt_nm(point[0])}, {fmt_nm(point[1])})"


def fmt_mm(nm: float) -> str:
    return f"{nm / NM:.4f}"


@dataclass
class Shape:
    kind: str                 # line | arc | curve | rect | circle | poly
    pts: dict                 # role -> (x_nm, y_nm): start/end (+mid) or center/end
    where: str                # "gr_line at line 11131" or "fp_line in J1"
    footprint: str = ""       # owning footprint reference; "" for a board shape
    ctrl: list = field(default_factory=list)   # curve control points (nm)
    ring: list = field(default_factory=list)   # poly outline (mm floats, arcs expanded)
    radius: int = 0           # rect corner radius (nm)
    span: tuple | None = None  # (start, end) of the block, from its leading newline (board shapes)
    tokens: dict = field(default_factory=dict)  # role -> (start, end, x text, y text) in the board text
    uuid: str = ""

    @property
    def editable(self) -> bool:
        return not self.footprint

    @property
    def is_open(self) -> bool:
        return self.kind in OPEN_KINDS


# ---------------------------------------------------------------- parsing

def _transform(point, place):
    if place is None:
        return point
    fx, fy, rot = place
    x, y = to_board(fx, fy, rot, point[0] / NM, point[1] / NM)
    return round(x * NM), round(y * NM)


def _shape(block: str, kind: str, where: str, place=None, offset: int = 0) -> Shape:
    shape = Shape(kind, {}, where)
    uuid = _UUID.search(block)
    shape.uuid = uuid.group(1) if uuid else ""
    if kind in ("poly", "curve"):
        pts = re.search(r"\(pts\b", block)
        items = [] if pts is None else list(_PTS_ITEM.finditer(block, pts.start()))
        if kind == "curve":
            corners = [_transform((to_nm(m.group(1)), to_nm(m.group(2))), place) for m in items if m.group(1)]
            if len(corners) != 4:
                raise ValueError(f"{where}: expected 4 bezier points, found {len(corners)}")
            shape.pts = {"start": corners[0], "end": corners[3]}
            shape.ctrl = corners[1:3]
            return shape
        for m in items:
            if m.group(1) is not None:
                shape.ring.append(_mm(_transform((to_nm(m.group(1)), to_nm(m.group(2))), place)))
            else:
                s, mid, e = (_mm(_transform((to_nm(m.group(k)), to_nm(m.group(k + 1))), place)) for k in (3, 5, 7))
                shape.ring.extend(_arc_path(s, mid, e))
        shape.ring = _dedupe(shape.ring)
        return shape
    for m in _POINT.finditer(block):
        role = m.group(1)
        if role in shape.pts:
            continue  # only the shape's own first start/mid/end/center
        shape.pts[role] = _transform((to_nm(m.group(2)), to_nm(m.group(3))), place)
        shape.tokens[role] = (offset + m.start(), offset + m.end(), m.group(2), m.group(3))
    radius = re.search(r"\n\t+\(radius " + _NUM + r"\)", block)
    if kind == "rect" and radius:
        shape.radius = to_nm(radius.group(1))
    need = {"line": ("start", "end"), "arc": ("start", "mid", "end"), "rect": ("start", "end"),
            "circle": ("center", "end")}[kind]
    missing = [role for role in need if role not in shape.pts]
    if missing:
        raise ValueError(f"{where}: no ({missing[0]} ...)")
    return shape


def parse(text: str) -> list:
    """Every Edge.Cuts shape on the board: board shapes first (in file order), then footprint ones."""
    newlines = [m.start() for m in re.finditer("\n", text)]
    shapes = []
    for start, end in spans(text, r"\n\t\(gr_(?:line|arc|rect|circle|poly|curve)\b"):
        block = text[start:end]
        if _EDGE not in block:
            continue
        kind = block[4:].split(None, 1)[0]  # "(gr_line ..." -> "line"
        line = bisect.bisect_left(newlines, start) + 1
        shape = _shape(block, kind, f"gr_{kind} at line {line}", offset=start)
        shape.span = (start - 2, end)  # from the newline before "\t(gr_"
        shapes.append(shape)
    for start, end in spans(text, r"\n\t\(footprint \""):
        block = text[start:end]
        if _EDGE not in block:
            continue
        at = re.search(r"\n\t\t\(at " + _NUM + " " + _NUM + r"(?: " + _NUM + r")?\)", block)
        ref = re.search(r'\(property "Reference" "([^"]*)"', block)
        name = ref.group(1) if ref else block.split('"', 2)[1]
        if at is None:
            raise ValueError(f"footprint {name}: no (at ...)")
        place = (float(at.group(1)), float(at.group(2)), float(at.group(3) or 0))
        for fs, fe in spans(block, r"\n\t\t\(fp_(?:line|arc|rect|circle|poly|curve)\b"):
            child = block[fs:fe]
            if _EDGE in child:
                kind = child[4:].split(None, 1)[0]  # "(fp_line ..." -> "line"
                shape = _shape(child, kind, f"fp_{kind} in {name}", place)
                shape.footprint = name
                shape.tokens = {}
                shapes.append(shape)
    return shapes


# ---------------------------------------------------------------- geometry (mm floats)

def _mm(point):
    return point[0] / NM, point[1] / NM


def _circumcentre(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    sa, sb, sc = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
    return ((sa * (b[1] - c[1]) + sb * (c[1] - a[1]) + sc * (a[1] - b[1])) / d,
            (sa * (c[0] - b[0]) + sb * (a[0] - c[0]) + sc * (b[0] - a[0])) / d)


def _arc_sweep(s, m, e):
    """(centre, radius, start angle, signed sweep) of the arc from s through m to e, or None if straight."""
    centre = _circumcentre(s, m, e)
    if centre is None:
        return None
    a0 = math.atan2(s[1] - centre[1], s[0] - centre[0])
    am = math.atan2(m[1] - centre[1], m[0] - centre[0])
    a1 = math.atan2(e[1] - centre[1], e[0] - centre[0])
    full = 2 * math.pi
    to_end, to_mid = (a1 - a0) % full, (am - a0) % full
    sweep = to_end if to_mid < to_end else to_end - full
    if sweep == 0:
        sweep = full  # start == end: a full circle drawn as an arc
    return centre, math.dist(centre, s), a0, sweep


def _arc_path(s, m, e):
    arc = _arc_sweep(s, m, e)
    if arc is None:
        return [s, e]
    centre, r, a0, sweep = arc
    n = max(2, math.ceil(abs(sweep) / ARC_STEP))
    inner = [(centre[0] + r * math.cos(a0 + sweep * k / n), centre[1] + r * math.sin(a0 + sweep * k / n))
             for k in range(1, n)]
    return [s] + inner + [e]


def _bezier_path(p0, p1, p2, p3, n=24):
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    out[0], out[-1] = p0, p3
    return out


def path(shape: Shape, reverse=False) -> list:
    """An open shape as a polyline in mm from its start to its end (or reversed)."""
    s, e = _mm(shape.pts["start"]), _mm(shape.pts["end"])
    if shape.kind == "line":
        out = [s, e]
    elif shape.kind == "arc":
        out = _arc_path(s, _mm(shape.pts["mid"]), e)
    else:
        out = _bezier_path(s, _mm(shape.ctrl[0]), _mm(shape.ctrl[1]), e)
    return out[::-1] if reverse else out


def ring(shape: Shape) -> list:
    """A closed shape as a polygon in mm (first vertex not repeated)."""
    if shape.kind == "poly":
        return list(shape.ring)
    if shape.kind == "circle":
        c, e = _mm(shape.pts["center"]), _mm(shape.pts["end"])
        r = math.dist(c, e)
        n = math.ceil(2 * math.pi / ARC_STEP)
        return [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    (x0, y0), (x1, y1) = _mm(shape.pts["start"]), _mm(shape.pts["end"])
    x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    r = min(shape.radius / NM, (x1 - x0) / 2, (y1 - y0) / 2)
    if r <= 0:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    out = []
    for cx, cy, a in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        n = max(2, math.ceil(math.radians(90) / ARC_STEP))
        out += [(cx + r * math.cos(math.radians(a + 90 * k / n)), cy + r * math.sin(math.radians(a + 90 * k / n)))
                for k in range(n + 1)]
    return out


def _dedupe(polygon) -> list:
    """Drop repeated consecutive vertices, including a last vertex that repeats the first."""
    out = [p for k, p in enumerate(polygon) if k == 0 or p != polygon[k - 1]]
    while len(out) > 1 and out[-1] == out[0]:
        out.pop()
    return out


def length_nm(shape: Shape) -> float:
    """Length of an open shape along its path, in nm."""
    if shape.kind == "arc":
        arc = _arc_sweep(_mm(shape.pts["start"]), _mm(shape.pts["mid"]), _mm(shape.pts["end"]))
        if arc is not None:
            return arc[1] * abs(arc[3]) * NM
    points = path(shape)
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False)) * NM


def grid_pitch(value: int) -> int:
    """The coarsest grid pitch (nm) a coordinate sits on."""
    for step in GRID_STEPS_NM:
        if value % step == 0:
            return step
    return 1


# ---------------------------------------------------------------- planning

@dataclass
class Finding:
    kind: str        # stub | gap | collinear | fold-back | open | junction
    text: str
    fixable: bool


@dataclass
class Plan:
    findings: list = field(default_factory=list)
    moves: dict = field(default_factory=dict)   # (shape index, "start"|"end") -> new point (nm)
    drops: set = field(default_factory=set)     # shape indices to delete
    stuck: set = field(default_factory=set)     # stubs whose removal leaves a gap nothing may close

    @property
    def changes(self) -> bool:
        return bool(self.moves or self.drops)


def _other(role: str) -> str:
    return "end" if role == "start" else "start"


def _dist2(a, b) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _clusters(ends, at, tol_nm: int) -> list:
    """Group ends whose points chain together at distances under tol_nm (union-find over a spatial hash)."""
    parent = list(range(len(ends)))

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    cell = max(tol_nm, 1)
    grid = defaultdict(list)
    for k, end in enumerate(ends):
        x, y = at(end)
        grid[(x // cell, y // cell)].append(k)
    limit = tol_nm * tol_nm
    for (cx, cy), members in grid.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in members:
                    for j in grid.get((cx + dx, cy + dy), ()):
                        if j > k and (_dist2(at(ends[k]), at(ends[j])) < limit or at(ends[k]) == at(ends[j])):
                            parent[find(k)] = find(j)
    groups = defaultdict(list)
    for k, end in enumerate(ends):
        groups[find(k)].append(end)
    return sorted(groups.values(), key=lambda group: min(group))


def heal_plan(shapes: list, tol_nm: int) -> Plan:
    """Plan the heal; a stub whose removal would leave a gap nothing may close is kept and reported."""
    keep = set()
    while True:
        result = plan_heal(shapes, tol_nm, keep)
        if not result.stuck - keep:
            return result
        keep |= result.stuck


def _is_stub(shape: Shape, tol_nm: int) -> bool:
    if shape.kind == "line":
        return _dist2(shape.pts["start"], shape.pts["end"]) < tol_nm * tol_nm or shape.pts["start"] == shape.pts["end"]
    return length_nm(shape) < tol_nm


def plan_heal(shapes: list, tol_nm: int, keep: set | frozenset = frozenset()) -> Plan:
    plan = Plan()

    def at(end):
        return plan.moves.get(end, shapes[end[0]].pts[end[1]])

    def describe(end):
        return f"{shapes[end[0]].where} {end[1]} {fmt_point(at(end))}"

    # 1. stubs: lines and arcs shorter than the tolerance
    for i, shape in enumerate(shapes):
        if shape.is_open and _is_stub(shape, tol_nm):
            text = (f"stub: {shape.where} is {fmt_mm(length_nm(shape))} mm long, "
                    f"{fmt_point(shape.pts['start'])} -> {fmt_point(shape.pts['end'])}")
            if not shape.editable:
                plan.findings.append(Finding("stub", text + "; in a footprint, fix it in the footprint", False))
            elif i in keep:
                plan.findings.append(Finding("stub", text + "; kept: without it the ends either side could not "
                                             "be joined (neither is a board line)", False))
            else:
                plan.findings.append(Finding("stub", text + "; drop it", True))
                plan.drops.add(i)

    # 2. gaps, open ends and tangles among the remaining ends
    live = [(i, role) for i, shape in enumerate(shapes) if shape.is_open and i not in plan.drops
            for role in ("start", "end")]
    stub_at = {shapes[i].pts[role]: i for i in plan.drops for role in ("start", "end")}
    for group in _clusters(live, at, tol_nm):
        by_point = defaultdict(list)
        for end in group:
            by_point[at(end)].append(end)
        loose = [ends[0] for ends in by_point.values() if len(ends) == 1]
        crowded = any(len(ends) > 2 for ends in by_point.values())
        if not loose and not crowded:
            continue  # every end already meets exactly one other (a kept stub can bring two such points close)
        if len(loose) == 1 and not crowded:
            end = loose[0]
            others = [math.sqrt(_dist2(at(end), at(o))) for o in live if at(o) != at(end)]
            nearest = f"; nearest other end {fmt_mm(min(others))} mm away" if others else ""
            plan.findings.append(Finding("open", f"open end: {describe(end)} has no partner closer than "
                                         f"{fmt_mm(tol_nm)} mm{nearest}", False))
        elif len(loose) == 2 and not crowded and _dist2(at(loose[0]), at(loose[1])) < tol_nm * tol_nm:
            first, second = loose
            gap = math.sqrt(_dist2(at(first), at(second)))
            stubs = {stub_at[at(end)] for end in loose if at(end) in stub_at}
            bridged = " (left by the stub)" if stubs else ""
            anchor, mover, reason = _choose(shapes, first, second, at)
            text = f"gap {fmt_mm(gap)} mm{bridged}: {describe(first)} / {describe(second)}"
            if mover is None:
                plan.findings.append(Finding("gap", f"{text}; not healed: {reason}", False))
                plan.stuck |= stubs
            else:
                plan.findings.append(Finding("gap", f"{text}; {reason}", True))
                plan.moves[mover] = at(anchor)
        else:
            points = set(by_point)
            what = "meet at" if len(points) == 1 else "lie within " + fmt_mm(tol_nm) + " mm of"
            plan.findings.append(Finding("junction", f"{len(group)} ends {what} {fmt_point(min(points))} "
                                         f"(overlap or branch, fix by hand): "
                                         + ", ".join(shapes[i].where for i, _ in group), False))

    # 3. lines that double back over a collinear neighbour
    folded = {}
    for point, pair in sorted(_joints(shapes, plan, at).items()):
        (i, ri), (j, rj) = pair
        if shapes[i].kind == shapes[j].kind == "line":
            far_i, far_j = at((i, _other(ri))), at((j, _other(rj)))
            if _folds(far_i, point, far_j):
                short = i if _dist2(point, far_i) <= _dist2(point, far_j) else j
                folded.setdefault(short, point)
    for short, point in folded.items():
        length = math.sqrt(_dist2(at((short, "start")), at((short, "end"))))
        hint = math.floor(length / NM * 100) / 100 + 0.01
        plan.findings.append(Finding("fold-back", f"fold-back: {shapes[short].where} ({fmt_mm(length)} mm) doubles "
                                     f"back over its neighbour at {fmt_point(point)}; fix by hand, or heal it as a "
                                     f"stub with --tol {hint:.2f}", False))

    # 4. collinear lines meeting end to end
    while True:
        for point, pair in sorted(_joints(shapes, plan, at).items()):
            (i, ri), (j, rj) = pair
            if not all(shapes[k].kind == "line" and shapes[k].editable for k in (i, j)):
                continue
            far_i, far_j = at((i, _other(ri))), at((j, _other(rj)))
            if not _collinear(far_i, point, far_j):
                continue
            keep_i = _dist2(point, far_i) >= _dist2(point, far_j)
            survivor, survivor_role, victim, victim_far = (i, ri, j, far_j) if keep_i else (j, rj, i, far_i)
            plan.findings.append(Finding("collinear", f"collinear: {shapes[survivor].where} and "
                                         f"{shapes[victim].where} meet end to end at {fmt_point(point)}; "
                                         "merge them", True))
            plan.moves[(survivor, survivor_role)] = victim_far
            plan.drops.add(victim)
            break
        else:
            break
    plan.moves = {end: point for end, point in plan.moves.items()
                  if end[0] not in plan.drops and point != shapes[end[0]].pts[end[1]]}
    return plan


def _joints(shapes, plan, at) -> dict:
    """point -> the two ends meeting exactly there, for points where exactly two shapes meet."""
    nodes = defaultdict(list)
    for i, shape in enumerate(shapes):
        if shape.is_open and i not in plan.drops:
            for role in ("start", "end"):
                nodes[at((i, role))].append((i, role))
    return {point: ends for point, ends in nodes.items() if len(ends) == 2 and ends[0][0] != ends[1][0]}


def _choose(shapes, first, second, at):
    """(anchor, mover, reason) for a gap; mover None when neither end may move."""
    def movable(end):
        shape = shapes[end[0]]
        return shape.editable and shape.kind == "line"

    a, b = movable(first), movable(second)
    if not a and not b:
        kinds = {("footprint " if shapes[e[0]].footprint else "") + shapes[e[0]].kind for e in (first, second)}
        return None, None, "neither end is a board line (" + " / ".join(sorted(kinds)) + "); fix by hand"
    if a != b:
        anchor, mover = (second, first) if a else (first, second)
        owner = shapes[anchor[0]].footprint
        if owner:
            return anchor, mover, f"move the board line's end onto footprint {owner}'s"
        return anchor, mover, f"move the line end onto the {shapes[anchor[0]].kind} end"
    # Two lines: keep the end whose differing coordinates sit on the coarser grid.
    p, q = at(first), at(second)
    differ = [k for k in (0, 1) if p[k] != q[k]]
    pitch_a, pitch_b = min(grid_pitch(p[k]) for k in differ), min(grid_pitch(q[k]) for k in differ)
    if pitch_a != pitch_b:
        anchor, mover = (first, second) if pitch_a > pitch_b else (second, first)
        return anchor, mover, f"keep the end on the {fmt_nm(max(pitch_a, pitch_b))} mm grid"
    # Same grid: move the longer line's end, which turns it the least; then file order.
    len_a = _dist2(p, at((first[0], _other(first[1]))))
    len_b = _dist2(q, at((second[0], _other(second[1]))))
    if len_a != len_b:
        anchor, mover = (second, first) if len_a > len_b else (first, second)
    else:
        anchor, mover = (first, second) if first < second else (second, first)
    return anchor, mover, "move the longer line's end (both ends on one grid)"


def _folds(a, joint, b) -> bool:
    """True if a and b lie on the same side of joint, on one straight line through it."""
    if (a[0] - joint[0]) * (b[0] - joint[0]) + (a[1] - joint[1]) * (b[1] - joint[1]) <= 0:
        return False
    cross = (a[0] - joint[0]) * (b[1] - joint[1]) - (a[1] - joint[1]) * (b[0] - joint[0])
    return cross * cross <= COLLINEAR_NM * COLLINEAR_NM * max(_dist2(a, joint), _dist2(b, joint))


def _collinear(a, joint, b) -> bool:
    """True if joint lies between a and b, within COLLINEAR_NM of the chord a-b."""
    if (a[0] - joint[0]) * (b[0] - joint[0]) + (a[1] - joint[1]) * (b[1] - joint[1]) >= 0:
        return False
    cross = (b[0] - a[0]) * (joint[1] - a[1]) - (b[1] - a[1]) * (joint[0] - a[0])
    return cross * cross <= COLLINEAR_NM * COLLINEAR_NM * _dist2(a, b)


# ---------------------------------------------------------------- exact closure

@dataclass
class Closure:
    outlines: int = 0
    cutouts: int = 0
    problems: list = field(default_factory=list)   # the shapes do not chain into clean loops
    layout: list = field(default_factory=list)     # clean loops, but not one board plus cutouts

    @property
    def closed(self) -> bool:
        """Every shape chains exactly into loops that neither cross nor touch."""
        return not self.problems

    @property
    def ok(self) -> bool:
        return not self.problems and not self.layout

    def summary(self) -> str:
        if self.ok:
            return f"closes exactly: 1 board outline, {self.cutouts} cutout(s)"
        if self.closed:
            return "closes exactly, but " + "; ".join(self.layout)
        return "does NOT close exactly: " + "; ".join(self.problems)


def closure(shapes: list) -> Closure:
    """Chain open shapes at zero tolerance and check the loops form one board polygon plus cutouts."""
    result = Closure()
    if not shapes:
        result.problems.append("no Edge.Cuts shapes")
        return result
    nodes = defaultdict(list)
    for i, shape in enumerate(shapes):
        if shape.is_open:
            for role in ("start", "end"):
                nodes[shape.pts[role]].append((i, role))
    dangling = sorted(point for point, ends in nodes.items() if len(ends) == 1)
    branches = sorted(point for point, ends in nodes.items() if len(ends) > 2)
    if dangling:
        result.problems.append(f"{len(dangling)} unmatched end(s), first at {fmt_point(dangling[0])}")
    if branches:
        result.problems.append(f"{len(branches)} point(s) where 3+ ends meet, first at {fmt_point(branches[0])}")
    if result.problems:
        return result

    loops, seen = [], set()
    for i, shape in enumerate(shapes):
        if not shape.is_open or i in seen:
            continue
        first = (i, "start")
        current, polygon = first, []
        while True:
            j, role_in = current
            seen.add(j)
            polygon.extend(path(shapes[j], reverse=role_in == "end")[:-1])
            role_out = _other(role_in)
            point = shapes[j].pts[role_out]
            current = next(end for end in nodes[point] if end != (j, role_out))
            if current == first:
                break
        loops.append(_dedupe(polygon))
    loops += [_dedupe(ring(shape)) for shape in shapes if not shape.is_open]

    for k, polygon in enumerate(loops):
        if len(polygon) < 3 or abs(_area(polygon)) < CROSS_EPS:
            result.problems.append(f"loop {k + 1} has no area")
    crossing = _first_crossing(loops)
    if crossing:
        result.problems.append(crossing)
    if result.problems:
        return result

    depth = [sum(1 for j, other in enumerate(loops) if j != k and _inside(polygon[0], other))
             for k, polygon in enumerate(loops)]
    result.outlines = depth.count(0)
    result.cutouts = sum(1 for d in depth if d == 1)
    if result.outlines != 1:
        result.layout.append(f"{result.outlines} separate board outlines")
    nested = sum(1 for d in depth if d > 1)
    if nested:
        result.layout.append(f"{nested} loop(s) nested inside a cutout")
    return result


def _area(polygon) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True)) / 2


def _inside(point, polygon) -> bool:
    x, y = point
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _contact(p1, p2, p3, p4):
    """A point where segments p1-p2 and p3-p4 cross or touch, or None."""
    d1, d2 = _cross(p3, p4, p1), _cross(p3, p4, p2)
    d3, d4 = _cross(p1, p2, p3), _cross(p1, p2, p4)
    if ((d1 > CROSS_EPS and d2 < -CROSS_EPS) or (d1 < -CROSS_EPS and d2 > CROSS_EPS)) and \
            ((d3 > CROSS_EPS and d4 < -CROSS_EPS) or (d3 < -CROSS_EPS and d4 > CROSS_EPS)):
        t = d1 / (d1 - d2)
        return p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])

    def on(a, b, p, d):
        return abs(d) <= CROSS_EPS and min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9 \
            and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9

    for a, b, p, d in ((p3, p4, p1, d1), (p3, p4, p2, d2), (p1, p2, p3, d3), (p1, p2, p4, d4)):
        if on(a, b, p, d):
            return p
    return None


def _first_crossing(loops) -> str:
    """Describe the first place two non-adjacent outline segments cross or touch, or ''."""
    segments = []
    for k, polygon in enumerate(loops):
        n = len(polygon)
        for s in range(n):
            a, b = polygon[s], polygon[(s + 1) % n]
            segments.append((min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]), k, s, n, a, b))
    segments.sort()
    active = []
    for seg in segments:
        x0, _x1, y0, y1, k, s, n, a, b = seg
        active = [other for other in active if other[1] >= x0 - 1e-9]
        for other in active:
            _ox0, _ox1, oy0, oy1, ok, os_, _on, oa, ob = other
            if oy1 < y0 - 1e-9 or y1 < oy0 - 1e-9:
                continue
            if ok == k and (abs(os_ - s) == 1 or abs(os_ - s) == n - 1):
                continue  # neighbours share a vertex
            point = _contact(a, b, oa, ob)
            if point is not None:
                where = f"at ({point[0]:.4f}, {point[1]:.4f})"
                return (f"outline crosses or overlaps itself {where}" if ok == k
                        else f"loops {ok + 1} and {k + 1} cross or touch {where}")
        active.append(seg)
    return ""


# ---------------------------------------------------------------- rewriting

def rewrite(text: str, shapes: list, plan: Plan) -> str:
    """Return text with only the moved ends rewritten and the dropped shapes removed."""
    edits = []
    for (i, role), point in plan.moves.items():
        shape = shapes[i]
        if not shape.editable or i in plan.drops:
            continue
        start, end, x_text, y_text = shape.tokens[role]
        old = shape.pts[role]
        x_text = x_text if point[0] == old[0] else fmt_nm(point[0])
        y_text = y_text if point[1] == old[1] else fmt_nm(point[1])
        edits.append((start, end, f"({role} {x_text} {y_text})"))
    dropped_uuids = []
    for i in plan.drops:
        if not shapes[i].editable:
            continue
        start, end = shapes[i].span
        edits.append((start, end, ""))
        if shapes[i].uuid:
            dropped_uuids.append(shapes[i].uuid)
    if dropped_uuids:  # a dropped shape may be a group member
        for start, end in spans(text, r"\(members\b"):
            members = text[start:end]
            kept = members
            for uuid in dropped_uuids:
                kept = re.sub(r'\s*"' + re.escape(uuid) + '"', "", kept)
            if kept != members:
                edits.append((start, end, kept))
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    return text


# ---------------------------------------------------------------- one board

@dataclass
class Result:
    shapes: list
    plan: Plan
    closure: Closure                # the board as it is
    text: str                       # healed text (the input when nothing changes)
    healed: Closure | None = None   # closure of the healed text
    leftover: list = field(default_factory=list)  # findings a second pass still makes on the healed text

    @property
    def empty(self) -> bool:
        return not self.shapes

    @property
    def board_shapes(self) -> int:
        return sum(1 for shape in self.shapes if shape.editable)

    @property
    def clean(self) -> bool:
        return self.empty or (not self.plan.findings and self.closure.ok)

    @property
    def heals(self) -> bool:
        """True when the planned edits leave shapes that chain exactly into clean loops (safe to write).

        Findings the plan cannot heal, such as a stub kept between two arcs, may remain in leftover,
        and layout questions (several board outlines) are reported but do not block the write.
        """
        return bool(self.plan.changes) and self.healed is not None and self.healed.closed

    def defects(self) -> list:
        """Geometry problems worth failing a fleet check on: everything except collinear splits
        and the layout questions (no outline yet, several board outlines)."""
        found = [f.text for f in self.plan.findings if f.kind != "collinear"]
        if not found and not self.empty:
            found += self.closure.problems
        return found


def analyse(text: str, tol: float = TOL) -> Result:
    tol_nm = round(tol * NM)
    shapes = parse(text)
    plan = heal_plan(shapes, tol_nm)
    result = Result(shapes, plan, closure(shapes), text)
    if plan.changes:
        result.text = rewrite(text, shapes, plan)
        healed = parse(result.text)
        result.healed = closure(healed)
        result.leftover = heal_plan(healed, tol_nm).findings
    return result
