"""Copper of a centre-fed PCB collinear (bead kicad-gpmd.2) as KiCad footprint text, in the style of dipole_arms.py.

Along x, symmetric about the feed (pad "1" is the left half, pad "2" the right; every piece of a half is DC-joined,
because a shorted stub is a DC path): the centre arm (a both-face strip with the UHF module's landing window at its
inner end), a 1 mm neck, the phasing stub, a neck, and the outer element (both-face strip, then a front-only cut
ladder, a 0603 tip pad and 0603-bridgeable islands).

The stub is a pair of coplanar strips (trace A from the inner element, trace B from the outer one) folded into three
runs above the outer element: up, down, up. Its electrical length is the MEAN of the two traces' centreline lengths.
The far end is a bidirectional ladder on run 3: copper shorts at the nominal length and `steps` steps beyond it (cut
one to lengthen the stub a step), and 0603 pad pairs `steps` steps before it (fit a 0R to shorten it a step).

y is KiCad's (down positive); the feed line is y = 0 and the stub rises into negative y. System python, stdlib only.
"""
from dataclasses import dataclass

from dipole_arms import bars, gaps, poly, rect_pts, u

NECK, NECK_W = 3.0, 1.0                  # neck length and width at each side of a stub
PAD_0603 = (0.98, 0.95)                  # R_0603_1608Metric_Pad0.98x0.95mm_HandSolder pad
PITCH_0603 = 1.825                       # its pad centre spacing
ISLAND_LEN = 2.1                         # an island: two 0603 pads joined (the inner lands one 0R, the outer the next)
ISLAND_STEP = PITCH_0603 + ISLAND_LEN - PAD_0603[0]     # 2.945 mm of element each fitted 0R adds


@dataclass
class Stub:
    length: float                        # nominal short position, mean centreline length along the pair (mm)
    w: float = 0.9                       # trace width
    s: float = 0.9                       # gap between the traces
    step: float = 2.0                    # ladder step (mean length)
    steps: int = 2                       # steps each way
    run_sep: float = 3.0                 # centreline distance between neighbouring runs of the inner trace
    bot: float = -6.3                    # y of the lower turn's inner trace (A); the outer (B) sits a pitch lower
    top_limit: float = -22.0             # no copper above this y
    bar_h: float = 0.5                   # copper short-bar height
    margin: float = 1.6                  # lowest 0R pad centre this far above the lower turn

    @property
    def pitch(self):
        return self.w + self.s


def fold(st, xa, ya0=0.0, yb0=0.0):
    """Trace centrelines of a stub folded to +x, trace A rising from (xa, ya0) and B from (xa + pitch, yb0).

    Returns {'A': [(x, y)], 'B': [(x, y)], 'run3': (xA3, xB3), 'y_at': mean length -> y on run 3, 'y_top': top turn y}.
    The mean length at run-3 height y is (ya0 + yb0)/2 - 2 y_top + 2 bot + 4 pitch + 2 run_sep - y; y_top is chosen so
    the innermost 0R pad sits `margin` above the lower turn."""
    p, d, yb = st.pitch, st.run_sep, st.bot
    const = (ya0 + yb0) / 2 + 2 * yb + 4 * p + 2 * d
    m_low = st.length - st.steps * st.step
    y_top = (const - m_low - (yb - st.margin)) / 2

    def y_at(m):
        return const - 2 * y_top - m
    xA, xB = xa, xa + p
    xA3, xB3 = xB + 2 * d + p, xB + 2 * d + 2 * p
    y_end = y_at(st.length + st.steps * st.step) - st.bar_h / 2
    if y_top - p - st.w / 2 < st.top_limit or y_end - st.w / 2 < st.top_limit:
        raise ValueError(f"stub of {st.length} mm does not fit under y {st.top_limit}")
    A = [(xA, ya0), (xA, y_top - p), (xB + d + p, y_top - p), (xB + d + p, yb), (xA3, yb), (xA3, y_end)]
    B = [(xB, yb0), (xB, y_top), (xB + d, y_top), (xB + d, yb + p), (xB3, yb + p), (xB3, y_end)]
    return {"A": A, "B": B, "run3": (xA3, xB3), "y_at": y_at, "y_top": y_top}


def seg_rects(path, w):
    """One rectangle (x1, y1, x2, y2) per segment of a Manhattan centreline, square ends grown by w/2 so corners fill."""
    out = []
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        out.append((min(x1, x2) - w / 2, min(y1, y2) - w / 2, max(x1, x2) + w / 2, max(y1, y2) + w / 2))
    return out


def stub_copper(st, xa, ya0=0.0, yb0=0.0):
    """{'rects': trace and short-bar copper, 'bars': [bar rect], 'pads': [(x, y)] 0603 pad centres, 'fold': fold()}."""
    f = fold(st, xa, ya0, yb0)
    xA3, xB3 = f["run3"]
    rects = seg_rects(f["A"], st.w) + seg_rects(f["B"], st.w)
    bar_rects = []
    for k in range(st.steps + 1):                       # nominal short, then each step longer
        y = f["y_at"](st.length + k * st.step)
        bar_rects.append((xA3, y - st.bar_h / 2, xB3, y + st.bar_h / 2))
    pads = []
    for k in range(1, st.steps + 1):                    # each step shorter: a 0R across the pair
        y = f["y_at"](st.length - k * st.step)
        pads += [(xA3, y), (xB3, y)]
    return {"rects": rects + bar_rects, "bars": bar_rects, "pads": pads, "fold": f}


def mirror(r):
    return (-r[2], r[1], -r[0], r[3])


class _Fp:
    """Minimal footprint-text writer (same conventions as dipole_arms.arm_footprint)."""

    def __init__(self, name, generator, descr, tags):
        self.o = []
        a = self.o.append
        a(f'(footprint "{name}"')
        a('\t(version 20260206)')
        a(f'\t(generator "{generator}")')
        a('\t(generator_version "10.0")')
        a('\t(layer "F.Cu")')
        a(f'\t(descr "{descr}")')
        a(f'\t(tags "{tags}")')
        a(f'\t(property "Reference" "REF**" (at 0 -24 0) (layer "F.SilkS") (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))')
        a(f'\t(property "Value" "{name}" (at 0 6 0) (layer "F.Fab") (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))')
        a(f'\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1.27 1.27) (thickness 0.15))))')
        a(f'\t(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1.27 1.27) (thickness 0.15))))')
        a('\t(attr exclude_from_pos_files exclude_from_bom)')

    def pad(self, num, kind, shape, x, y, size, drill=None, layers='"*.Cu"', extra=""):
        d = f" (drill {drill:g})" if drill else ""
        self.o.append(f'\t(pad "{num}" {kind} {shape} (at {x:g} {y:g}) (size {size[0]:g} {size[1]:g}){d} (layers {layers}) '
                      f'(remove_unused_layers no){extra} (uuid "{u()}"))')

    def custom(self, num, kind, x, y, rects, drill=None, layers='"*.Cu"', anchor=(0.8, 0.8)):
        """A custom pad at (x, y) whose copper is the union of rects (board-local (x1, y1, x2, y2))."""
        prims = " ".join(poly(rect_pts(r[0] - x, r[1] - y, r[2] - x, r[3] - y)) for r in rects)
        self.pad(num, kind, "custom", x, y, anchor, drill=drill, layers=layers,
                 extra=f" (options (clearance outline) (anchor rect)) (primitives {prims})")

    def rect(self, layer, r, width=0.0, fill=True):
        self.o.append(f'\t(fp_rect (start {r[0]:g} {r[1]:g}) (end {r[2]:g} {r[3]:g}) (stroke (width {width:g}) (type default)) '
                      f'(fill {"yes" if fill else "no"}) (layer "{layer}") (uuid "{u()}"))')

    def outline(self, layer, pts, width=0.05):
        """A closed, unfilled polygon (courtyards must be one non-self-intersecting outline per region)."""
        xy = " ".join(f"(xy {x:g} {y:g})" for x, y in pts)
        self.o.append(f'	(fp_poly (pts {xy}) (stroke (width {width:g}) (type default)) (fill no) (layer "{layer}") (uuid "{u()}"))')

    def text(self, label, x, y, rot=0, size=0.8, layer="F.SilkS"):
        self.o.append(f'\t(fp_text user "{label}" (at {x:g} {y:g} {rot}) (layer "{layer}") (uuid "{u()}") '
                      f'(effects (font (size {size} {size}) (thickness {size * 0.15:.2f}))))')

    def done(self):
        self.o.append('\t(embedded_fonts no)')
        self.o.append(')')
        return "\n".join(self.o) + "\n"


def layout(*, centre_arm, outer, stub, gap=30.0, width=6.0, ladder_n=8, ladder_pitch=1.5, ladder_gap=0.6, islands=2):
    """Right-half geometry (x > 0) as plain numbers, for the footprint writer and the tests."""
    xe = gap / 2 + centre_arm                          # centre strip end
    xa = xe + NECK - stub.w / 2                        # trace A centreline (flush with neck A's outer end)
    xo = xe + 2 * NECK + stub.s                        # outer strip start
    tip = xo + outer                                   # end of the last ladder bar at nominal trim
    strip_end = tip - ladder_n * ladder_pitch
    if strip_end - xo < 10.0:
        raise ValueError(f"outer element {outer} mm leaves no room for a {ladder_n}-bar ladder")
    x_tp = tip - 0.1 + PAD_0603[0] / 2                 # tip pad overlaps the last bar by 0.1 mm
    isl = []
    for k in range(islands):
        inner = x_tp + PITCH_0603 + k * ISLAND_STEP
        isl.append((inner - PAD_0603[0] / 2 + ISLAND_LEN / 2, inner))
    return {"xe": xe, "xa": xa, "xo": xo, "tip": tip, "strip_end": strip_end, "x_tp": x_tp, "islands": isl,
            "necks": [(xe, -NECK_W / 2, xe + NECK, NECK_W / 2), (xo - NECK, -NECK_W / 2, xo, NECK_W / 2)],
            "stub": stub_copper(stub, xa), "end": isl[-1][0] + ISLAND_LEN / 2 if isl else x_tp + PAD_0603[0] / 2}


def collinear_footprint(*, name, generator, descr, tags, centre_arm, outer, stub, gap=30.0, width=6.0, landing=3.5,
                        ladder_n=8, ladder_pitch=1.5, ladder_gap=0.6, bridge_w=1.0, bridge_ext=0.25, islands=2):
    """Footprint text of the whole collinear (both halves)."""
    L = layout(centre_arm=centre_arm, outer=outer, stub=stub, gap=gap, width=width, ladder_n=ladder_n,
               ladder_pitch=ladder_pitch, ladder_gap=ladder_gap, islands=islands)
    hw = width / 2
    fp = _Fp(name, generator, descr, tags)
    for s, num in ((-1, "1"), (+1, "2")):
        m = (lambda r: r) if s > 0 else mirror
        # centre strip, both faces, anchor hole and stitch holes
        fp.custom(num, "thru_hole", s * (gap / 2 + 2), 0, [m((gap / 2, -hw, L["xe"], hw))], drill=1.0)
        x = gap / 2 + 7
        while x <= L["xe"] - 3:
            fp.pad(num, "thru_hole", "circle", s * x, 0, (1.8, 1.8), drill=1.0)
            x += 10
        if landing:
            fp.rect("F.Mask", m((gap / 2, -hw, gap / 2 + landing, hw)))
        # necks + stub (front only)
        st = L["stub"]
        neck_a = L["necks"][0]
        fp.custom(num, "smd", s * (neck_a[0] + neck_a[2]) / 2, 0, [m(r) for r in L["necks"] + st["rects"]], layers='"F.Cu"')
        for (px, py) in st["pads"]:
            fp.pad(num, "smd", "rect", s * px, py, PAD_0603, layers='"F.Cu" "F.Mask"')
        for b in st["bars"]:
            fp.rect("F.Mask", m((b[0] - 0.2, b[1] - 0.2, b[2] + 0.2, b[3] + 0.2)))
        # outer strip, both faces
        fp.custom(num, "thru_hole", s * (L["xo"] + 2), 0, [m((L["xo"], -hw, L["strip_end"], hw))], drill=1.0)
        x = L["xo"] + 7
        while x <= L["strip_end"] - 3:
            fp.pad(num, "thru_hole", "circle", s * x, 0, (1.8, 1.8), drill=1.0)
            x += 10
        # cut ladder (front only), tip pad, islands
        b = bars(s, L["strip_end"], ladder_n, ladder_pitch, ladder_gap)
        bx0 = (b[0][0] + b[0][1]) / 2
        rects = [(x1, -hw, x2, hw) for x1, x2 in b]
        for g1, g2 in gaps(s, L["strip_end"], ladder_n, ladder_pitch, ladder_gap):
            rects.append((g1 - bridge_ext, -bridge_w / 2, g2 + bridge_ext, bridge_w / 2))
            fp.rect("F.Mask", ((g1 + g2) / 2 - 0.55, -bridge_w / 2 - 0.35, (g1 + g2) / 2 + 0.55, bridge_w / 2 + 0.35))
        fp.custom(num, "smd", bx0, 0, rects, layers='"F.Cu"')
        fp.pad(num, "smd", "rect", s * L["x_tp"], 0, PAD_0603, layers='"F.Cu" "F.Mask"')
        for cx, _ in L["islands"]:
            fp.pad("", "smd", "rect", s * cx, 0, (ISLAND_LEN, PAD_0603[1]), layers='"F.Cu" "F.Mask"')
        # fab outline and courtyard: the strip line and the stub fold separately, so parts can sit above the centre arm
        sx0, sx1 = min(r[0] for r in st["rects"]), max(r[2] for r in st["rects"])
        top = min(r[1] for r in st["rects"])
        for r in ((gap / 2, -hw, L["end"], hw), (sx0, top, sx1, -hw)):
            fp.rect("F.Fab", m(r), width=0.1, fill=False)
        x0, x1, yb, ys = gap / 2 - 0.5, L["end"] + 0.5, hw + 0.5, -hw - 0.5
        cy = [(x0, yb), (x0, ys), (sx0 - 0.5, ys), (sx0 - 0.5, top - 0.5), (sx1 + 0.5, top - 0.5), (sx1 + 0.5, ys), (x1, ys), (x1, yb)]
        fp.outline("F.CrtYd", [(s * x, y) for x, y in cy])      # the strip line with the stub fold on top, one outline
    return fp.done()


# u.FL receptacle (Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical at rotation 0): signal pad 1.05 x 1.0 at
# (-1.525, 0), ground pads 2.2 x 1.05 at (0, +-1.475), copper keepout x -0.99..1.1, y -0.95..0.95.
UFL_SIG_X, UFL_GND_Y = -1.525, 1.475


def coupon_footprint(*, name, generator, descr, stub):
    """The test stub: the same fold and ladder as the antenna's, driven straight from a u.FL at the origin (trace A
    rising from the signal pad, trace B from the upper ground pad), the two ground pads joined around the +x side of
    the u.FL's keepout. All copper is pad "1" (a shorted stub is a DC short)."""
    xa = UFL_SIG_X - 0.225                              # trace A right edge 0.2 mm clear of the upper ground pad
    st = stub_copper(stub, xa, ya0=0.0, yb0=-UFL_GND_Y)
    gnd = [(0.9, -2.0, 2.3, -1.0), (0.9, 1.0, 2.3, 2.0), (1.3, -2.0, 2.3, 2.0),  # C around the keepout joining both ground pads
           (xa + stub.pitch - stub.w / 2, -2.0, 0.9, -1.0)]                     # ... and to trace B (below the keepout's y)
    fp = _Fp(name, generator, descr, "antenna collinear stub test coupon")
    fp.custom("1", "smd", xa, -3.0, st["rects"] + gnd, layers='"F.Cu"')
    for (px, py) in st["pads"]:
        fp.pad("1", "smd", "rect", px, py, PAD_0603, layers='"F.Cu" "F.Mask"')
    for b in st["bars"]:
        fp.rect("F.Mask", (b[0] - 0.2, b[1] - 0.2, b[2] + 0.2, b[3] + 0.2))
    xs = [r[2] for r in st["rects"]] + [2.3]
    top = min(r[1] for r in st["rects"])
    fp.rect("F.Fab", (-2.6, top, max(xs), 2.6), width=0.1, fill=False)
    fp.rect("F.CrtYd", (min(r[0] for r in st["rects"]) - 0.5, top - 0.5, max(xs) + 0.5, -2.8), width=0.05, fill=False)   # above the u.FL's
    return fp.done()


def mousebite_footprint(*, name, generator, n=5, pitch=1.0, drill=0.5):
    """A vertical row of n NPTH holes centred on the origin: the perforation of a break-off tab's bridge."""
    fp = _Fp(name, generator, f"{n} x {drill:g} mm NPTH mouse bites, {pitch:g} mm pitch", "mouse bite perforation")
    for k in range(n):
        fp.pad("", "np_thru_hole", "circle", 0, (k - (n - 1) / 2) * pitch, (drill, drill), drill=drill, layers='"*.Cu" "*.Mask"')
    return fp.done()
