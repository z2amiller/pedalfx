"""Free-space NEC-2 model of a centre-fed PCB collinear (bead kicad-gpmd.2), built on dipole_nec's conventions.

Along x, symmetric about the feed: the centre element (two arms either side of the module gap, the stacked UHF
module's two ground pours above it), then per side a phasing stub and an outer element, repeated outwards. Flat
strips of width W are wires of radius W/4.

Trimming is modelled the way the dipole calibration was: a cut shortens an element and a fitted 0R island lengthens
it; floating copper (cut-off bars, unbridged islands) is ignored. (necpp also rejects a thin 0R wire butted to a 6 mm
strip when it is shorter than ~3 mm, so a physical 0.9 mm island gap cannot be modelled directly.)

A stub is a shorted two-wire line in series with the current path: the element ends it joins are bridged by a short
wire (stub_axial long, the board length the folded stub occupies) whose middle segment is one port of a NEC
transmission-line card; the card's far end sits on a one-segment dummy wire far away, shorted by a huge shunt
admittance. NEC TL cards have no velocity factor, so a stub is given by its ELECTRICAL length in air; its physical
length on the board is that times the line's velocity factor (cps.py).

All lengths here are NEC-scale (free space). In-pipe loading is applied by the caller: k_c and k_o in
util-Collinear1090/tools/collinear1090_nec.py. Runs in the PyNEC venv, never KiCad's python.
"""
from dataclasses import dataclass, replace

from PyNEC import nec_context

from dipole_nec import POUR_MODULE_BACK, POUR_MODULE_FRONT, resonance

MM = 1e-3
DUMMY_X = 5000.0               # mm: stub-termination dummy wires sit 5 m away (18 wavelengths at 1090)


@dataclass
class Collinear:
    centre_arm: float                          # each centre arm, from the gap edge outwards
    outer: list                                # outer element lengths per side, innermost first
    stub_elec: list                            # stub electrical lengths in air, innermost first (len == len(outer))
    stub_z0: float = 150.0
    gap: float = 30.0
    stub_axial: float = 10.0
    width: float = 6.0
    pours: tuple = (POUR_MODULE_BACK, POUR_MODULE_FRONT)
    seg: float = 3.0
    feed_r: float = 1.25

    def half_length(self):
        """Copper from the feed centre to the outermost element tip."""
        return self.gap / 2 + self.centre_arm + sum(self.outer) + self.stub_axial * len(self.outer)


def build(ctx, c):
    """Add the geometry; returns ((feed tag, feed segment), [(stub tag, stub segment)])."""
    if len(c.outer) != len(c.stub_elec):
        raise ValueError("one stub per outer element")
    geo = ctx.get_geometry()
    tag = [0]

    def wire(x1, x2, rad, n=None, y=0.0, z=0.0):
        tag[0] += 1
        n = n or max(1, int(round(abs(x2 - x1) / c.seg)))
        geo.wire(tag[0], n, x1 * MM, y * MM, z * MM, x2 * MM, y * MM, z * MM, rad * MM, 1.0, 1.0)
        return tag[0]

    nfeed = 5
    feed = (wire(-c.gap / 2, c.gap / 2, c.feed_r, nfeed), (nfeed + 1) // 2)
    r = c.width / 4
    stubs = []
    for s in (+1, -1):
        x = c.gap / 2
        wire(s * x, s * (x + c.centre_arm), r) if s > 0 else wire(s * (x + c.centre_arm), s * x, r)
        x += c.centre_arm
        for length in c.outer:
            a, b = s * x, s * (x + c.stub_axial)
            stubs.append((wire(min(a, b), max(a, b), r, 3), 2))
            x += c.stub_axial
            a, b = s * x, s * (x + length)
            wire(min(a, b), max(a, b), r)
            x += length
    for x0, x1, y0, y1, cell, rg, z in c.pours:
        xs = [x0 + k * cell for k in range(int(round((x1 - x0) / cell)) + 1)]
        ys = [y0 + k * cell for k in range(int(round((y1 - y0) / cell)) + 1)]
        for y in ys:
            for xa, xb in zip(xs, xs[1:]):
                wire(xa, xb, rg, 1, y=y, z=z)
        for xx in xs:
            for ya, yb in zip(ys, ys[1:]):
                tag[0] += 1
                geo.wire(tag[0], 1, xx * MM, ya * MM, z * MM, xx * MM, yb * MM, z * MM, rg * MM, 1.0, 1.0)
    dummies = [wire(DUMMY_X + 20 * k, DUMMY_X + 20 * k + 2, 0.5, 1, y=DUMMY_X) for k in range(len(stubs))]
    ctx.geometry_complete(0)
    for (st, sg), stub_len, d in zip(stubs, c.stub_elec * 2, dummies):
        ctx.tl_card(st, sg, d, 1, c.stub_z0, stub_len * MM, 0.0, 0.0, 1e10, 0.0)   # far end shorted
    return feed, stubs


def _run(c, f0, n, df, pattern):
    ctx = nec_context()
    feed, _ = build(ctx, c)
    ctx.gn_card(-1, 0, 0, 0, 0, 0, 0, 0)
    ctx.ex_card(0, feed[0], feed[1], 0, 1.0, 0, 0, 0, 0, 0)
    ctx.fr_card(0, n, f0, df)
    if pattern:
        ctx.rp_card(0, 1, 2, 0, 5, 0, 0, 90.0, 0.0, 0.0, 90.0, 0, 0)      # theta 90, phi 0 (along x) and 90 (broadside)
    else:
        ctx.xq_card(0)
    return ctx


NUDGES = (0.0, 0.05, -0.05, 0.1, -0.1)       # mm added to the centre arm when necpp throws (see dipole_nec.report_safe)


def _run_safe(c, f0, n, df, pattern):
    last = None
    for d in NUDGES:
        try:
            return _run(replace(c, centre_arm=c.centre_arm + d), f0, n, df, pattern)
        except RuntimeError as e:          # necpp's bare "Unknown exception" for some segmentations
            last = e
    raise RuntimeError(f"necpp failed for {c} at every nudge") from last


def evaluate(c, f_mhz=1090.0):
    """{'z': feed impedance, 'gain_dbi': broadside gain} at one frequency."""
    ctx = _run_safe(c, f_mhz, 1, 0.0, True)
    z = ctx.get_input_parameters(0).get_impedance()[0]
    gain = float(ctx.get_radiation_pattern(0).get_gain()[0][1])
    return {"z": complex(z), "gain_dbi": gain}


def sweep(c, f0, f1, n=121, z0=50.0):
    """[(f, R, X, VSWR50)] across f0..f1, the same tuple shape as dipole_nec.sweep."""
    df = (f1 - f0) / (n - 1)
    ctx = _run_safe(c, f0, n, df, False)
    out = []
    for i in range(n):
        z = ctx.get_input_parameters(i).get_impedance()[0]
        g = (z - z0) / (z + z0)
        out.append((f0 + i * df, z.real, z.imag, (1 + abs(g)) / (1 - abs(g)) if abs(g) < 1 else 99.0))
    return out


def feed_resonance(c, f0=950.0, f1=1250.0, n=121):
    """(f, R) where the feed reactance crosses zero upwards, or (None, None)."""
    return resonance(sweep(c, f0, f1, n))
