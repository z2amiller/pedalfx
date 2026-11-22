"""Faceplate geometry for 1590XX panels (stdlib; KiCad's bundled python imports it too).

Spec: ~/Claude/docs/superpowers/specs/2026-11-21-revolver-faceplate-design.md. The faceplate board shares the main
board's y and mirrors its x, because the parts face into the box and the player sees the F side from behind:
face x = 298.0 - board x, so the enclosure centre (board x 147.5) sits at face x 150.5. Tayda face A takes
X = board y - 100.75 (towards the footswitches) and Y = 147.5 - board x (the player's right). Every position here
derives from geometry.GUIDES, so the board template and the faceplate template cannot drift apart.
"""
import math

import geometry

FACE_MIRROR = 298.0
LABEL_DY = 12.25                        # label centre below the hole centre (the template's CONTROL rows)
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 10.0, 8.75, 4.0
FRAME_R, FRAME_W = 2.0, 0.5
TREFOIL_SRC = (110.0, 127.75)           # the template's one glow-through LED trefoil
POT_HOLE, SWITCH_HOLE, LED_HOLE = 8.2, 12.4, 5.2
# Side C (jacks and DC) of L7's Tayda file, as copied by ~/Claude/meridian-v3-placement/panel_v3.py
SIDE_C = ['C\t12.8\t-5.5\t-38.0', 'C\t12.8\t-5.5\t38.0',
          'C\t0\t-9.3\t5.0\t2.9\t5.0', 'C\t0\t-9.3\t-5.0\t-9.3\t5.0', 'C\t0\t2.9\t-5.0\t2.9\t5.0', 'C\t0\t-9.3\t-5.0\t2.9\t-5.0']


def face_x(board_x: float) -> float:
    return round(FACE_MIRROR - board_x, 4)


def board_to_tayda(x: float, y: float) -> tuple:
    return (round(y - geometry.CENTRE[1], 4), round(geometry.CENTRE[0] - x, 4))


def _face(prefix: str) -> list:
    return sorted(((face_x(x), y) for label, x, y, _d in geometry.GUIDES if label.startswith(prefix)),
                  key=lambda p: (p[1], p[0]))


TEMPLATE_HOLES = _face("POT ROW")       # 2 rows of 6, row by row, west to east on the face
LED_FACE = _face("LED ")                # the three LEDs above the footswitches


def frame_rects(rows: list) -> list:
    """One (x0, y0, x1, y1) per knob row, from (hole y, occupied face xs), top row first. Adjacent rows meet at
    the midpoint between the upper row's labels and the lower row's frame top."""
    rects = []
    for i, (hy, xs) in enumerate(rows):
        top = hy - MARGIN_TOP if i == 0 else rects[-1][3]
        if i + 1 < len(rows):
            bottom = round((hy + LABEL_DY + rows[i + 1][0] - MARGIN_TOP) / 2, 4)
        else:
            bottom = round(hy + LABEL_DY + MARGIN_BOTTOM, 4)
        rects.append((round(min(xs) - MARGIN_X, 4), round(top, 4), round(max(xs) + MARGIN_X, 4), bottom))
    return rects


def stepped_outline(rects: list) -> list:
    """The union of vertically stacked row rectangles as one polygon, clockwise on screen (y down)."""
    pts = [(rects[0][0], rects[0][1]), (rects[0][2], rects[0][1])]
    for a, b in zip(rects, rects[1:]):                   # down the right side
        if a[2] != b[2]:
            pts += [(a[2], a[3]), (b[2], a[3])]
    last = rects[-1]
    pts += [(last[2], last[3]), (last[0], last[3])]
    for a, b in reversed(list(zip(rects, rects[1:]))):   # back up the left side
        if a[0] != b[0]:
            pts += [(b[0], a[3]), (a[0], a[3])]
    return pts


COLUMNS = sorted({x for x, _y in TEMPLATE_HOLES})
ROWS = sorted({y for _x, y in TEMPLATE_HOLES})


def frame_for(points: list) -> list:
    """The stepped frame around a group of knobs given as face (x, y). Each knob snaps to the template grid first,
    so a pot a fraction of a millimetre off its column can't put a tiny step (and a looped fillet) in the frame."""
    rows = {}
    for x, y in points:
        rows.setdefault(min(ROWS, key=lambda r: abs(r - y)), []).append(min(COLUMNS, key=lambda c: abs(c - x)))
    return stepped_outline(frame_rects(sorted(rows.items())))


def fillet(points: list, r: float) -> list:
    """Round every corner of a closed polygon with radius r: ('line', a, b) and ('arc', start, mid, end) items.
    The arc is tangent to both edges, so one rule rounds convex and concave corners alike."""
    n = len(points)
    corners = []
    for i, p in enumerate(points):
        a, b = points[i - 1], points[(i + 1) % n]
        u1 = _unit(a[0] - p[0], a[1] - p[1])
        u2 = _unit(b[0] - p[0], b[1] - p[1])
        theta = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1])))
        t = r / math.tan(theta / 2)
        bis = _unit(u1[0] + u2[0], u1[1] + u2[1])
        d = r / math.sin(theta / 2)
        centre = (p[0] + bis[0] * d, p[1] + bis[1] * d)
        corners.append(((p[0] + u1[0] * t, p[1] + u1[1] * t),
                        (centre[0] - bis[0] * r, centre[1] - bis[1] * r),
                        (p[0] + u2[0] * t, p[1] + u2[1] * t)))
    for i, (_t1, _m, t2) in enumerate(corners):
        nxt = corners[(i + 1) % n][0]
        edge = (points[(i + 1) % n][0] - points[i][0], points[(i + 1) % n][1] - points[i][1])
        if (nxt[0] - t2[0]) * edge[0] + (nxt[1] - t2[1]) * edge[1] < -1e-9:
            raise ValueError(f"edge from {points[i]} is too short for r {r}: the fillets would overlap")
    items = []
    for i, (t1, mid, t2) in enumerate(corners):
        items.append(('arc', t1, mid, t2))
        items.append(('line', t2, corners[(i + 1) % n][0]))
    return items


def _unit(dx: float, dy: float) -> tuple:
    length = math.hypot(dx, dy)
    return (dx / length, dy / length)


def num(v: float) -> str:
    """Tayda's own number format (L7's file from Tayda): at most two decimals, at least one (-38.0, 27.4, -35.24)."""
    s = ('%.2f' % (0.0 if abs(v) < 0.005 else v)).rstrip('0')
    return s + '0' if s.endswith('.') else s


def tayda_lines(pots: list, feet_y: list) -> list:
    """Tayda drill lines: the pots (board shaft x, y), then a footswitch and an LED per Tayda Y in feet_y, then
    L7's side C."""
    holes = sorted((board_to_tayda(x, y) for x, y in pots), key=lambda h: (round(h[0], 1), h[1]))
    lines = ['A\t%s\t%s\t%s' % (num(POT_HOLE), num(tx), num(ty)) for tx, ty in holes]
    lines += ['A\t%s\t%s\t%s' % (num(SWITCH_HOLE), num(geometry.SWITCH_X_TAYDA), num(y)) for y in feet_y]
    lines += ['A\t%s\t%s\t%s' % (num(LED_HOLE), num(geometry.LED_X_TAYDA), num(y)) for y in feet_y]
    return lines + SIDE_C
