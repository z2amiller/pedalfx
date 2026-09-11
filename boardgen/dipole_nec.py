"""Free-space NEC-2 model of a centre-gap PCB dipole (kicad-y27p item 2; from util-Antenna1090/tools/dipole1090_nec.py).

Two strip arms of width W and length L along x either side of a gap G; the balanced feed traces across the gap are
one wire of radius feed_r with the source on its middle segment (5 mm traces -> r 1.25: a thin feed makes NEC
misreport R). Flat strip -> wire radius W/4. Each ground pour is a wire grid (x0, x1, y0, y1, cell, r, z) in mm,
z above the arm plane; the stacked UHF module has one at z 0 and one at z 1.6. necpp raises a bare exception for
some L at a given segment length: report_safe steps L by 0.25 mm.

POUR_MODULE_BACK and POUR_MODULE_FRONT are modelled as two separate floating wire grids with no stitching vias
between the faces; that simplification is deliberate (a via mesh would need its own convergence study) and untested.
"""
import math
from PyNEC import nec_context

MM = 1e-3
POUR_1090_INTEGRATED = (-18, 18, 6, 22, 4.0, 0.6, 0.0)     # 36 x 16 mm pour, 6 mm off the feed line, as fabbed
# The fabbed util-Antenna772 board's pour is 36 x 16 mm, 6 mm off the feed line, exactly like the 1090's:
# gen_772_board.py POUR = x 97..133, y 21..37 with the feed at y 43, so this constant is correct as written. The
# old tools/dipole772_nec.py in that repo used a 24 x 16 pour with feed_r 0.4 and seg 4.0 and reported 762 MHz;
# this model gives 764.9 MHz for the same board.
POUR_772_INTEGRATED = (-18, 18, 6, 22, 4.0, 0.6, 0.0)
POUR_MODULE_BACK = (-15, 15, 6, 22, 4.0, 0.6, 0.0)         # module back face, mask on mask
POUR_MODULE_FRONT = (-15, 15, 6, 22, 4.0, 0.6, 1.6)        # module front face, one board thickness up


def build(ctx, L, W, G, pours=(), feed_r=1.25, seg=3.0):
    geo = ctx.get_geometry()
    tag = [0]

    def wire(x1, y1, x2, y2, rad, seg_mm, z=0.0):
        length = math.hypot(x2 - x1, y2 - y1)
        tag[0] += 1
        nseg = max(1, int(round(length / seg_mm)))
        geo.wire(tag[0], nseg, x1 * MM, y1 * MM, z * MM, x2 * MM, y2 * MM, z * MM, rad * MM, 1.0, 1.0)
        return tag[0], nseg

    nfeed = 5
    tag[0] += 1
    geo.wire(tag[0], nfeed, -G / 2 * MM, 0, 0, G / 2 * MM, 0, 0, feed_r * MM, 1.0, 1.0)
    feed = (tag[0], (nfeed + 1) // 2)
    for s in (+1, -1):
        wire(s * G / 2, 0, s * (G / 2 + L), 0, W / 4, seg)
    for x0, x1, y0, y1, cell, rg, z in pours:
        xs = [x0 + k * cell for k in range(int(round((x1 - x0) / cell)) + 1)]
        ys = [y0 + k * cell for k in range(int(round((y1 - y0) / cell)) + 1)]
        for y in ys:
            for xa, xb in zip(xs, xs[1:]):
                wire(xa, y, xb, y, rg, cell, z)
        for x in xs:
            for ya, yb in zip(ys, ys[1:]):
                wire(x, ya, x, yb, rg, cell, z)
    ctx.geometry_complete(0)
    return feed


def sweep(L, W, G, pours=(), f0=900.0, f1=1300.0, n=201, z0=50.0):
    ctx = nec_context()
    feed_tag, feed_seg = build(ctx, L, W, G, pours)
    ctx.gn_card(-1, 0, 0, 0, 0, 0, 0, 0)
    try:
        ctx.ek_card(0)
    except Exception:
        pass
    ctx.ex_card(0, feed_tag, feed_seg, 0, 1.0, 0, 0, 0, 0, 0)
    df = (f1 - f0) / (n - 1)
    ctx.fr_card(0, n, f0, df)
    ctx.xq_card(0)
    out = []
    for i in range(n):
        z = ctx.get_input_parameters(i).get_impedance()[0]
        f = f0 + i * df
        g = (z - z0) / (z + z0)
        vswr = (1 + abs(g)) / (1 - abs(g)) if abs(g) < 1 else 99
        out.append((f, z.real, z.imag, vswr))
    return out


def resonance(res):
    for (f1, r1, x1, _), (f2, r2, x2, _) in zip(res, res[1:]):
        if x1 <= 0 < x2:
            t = -x1 / (x2 - x1)
            return f1 + t * (f2 - f1), r1 + t * (r2 - r1)
    return None, None


def report(name, L, W, G, pours=(), f0=900.0, f1=1300.0, f_mark=1090.0, z0=50.0):
    res = sweep(L, W, G, pours, f0=f0, f1=f1, z0=z0)
    fr, rr = resonance(res)
    assert f0 <= f_mark <= f1, f"f_mark {f_mark} outside the sweep {f0}-{f1}"
    vmark = min(res, key=lambda r: abs(r[0] - f_mark))[3]
    lo = min((r for r in res if r[3] < 2), key=lambda r: r[0], default=None)
    hi = max((r for r in res if r[3] < 2), key=lambda r: r[0], default=None)
    bw = f"{lo[0]:.0f}-{hi[0]:.0f}" if lo and hi else "n/a"
    print(f"{name:44s} f_res={fr and round(fr, 1)} MHz  R={rr and round(rr, 1)}  VSWR50@{f_mark:g}={vmark:.2f}  VSWR<2: {bw}", flush=True)
    return fr, rr, L


def report_safe(name, L, W, G, pours=(), **kw):
    last_exc = None
    for trial in (L, L + 0.25, L - 0.25, L + 0.5):
        try:
            return report(f"{name} (L={trial:g})", trial, W, G, pours, **kw)
        except Exception as e:
            last_exc = e
            continue
    print(f"{name}: necpp failed for L near {L}: {last_exc!r}")
    return None, None, None
