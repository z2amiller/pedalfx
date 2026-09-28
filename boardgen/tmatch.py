"""Highpass T matching network for the UHF module's C11 / L11 / C12 position (bead kicad-gpmd.2).

Topology, source to load: series C1, shunt L to ground, series C2. It matches a complex source Zs (the antenna seen
through the module's 1:1 balun) to a resistive load RL (the LNA, 50 ohm) at one frequency through a virtual
resistance Rv > max(Rs, RL), i.e. two back-to-back highpass L-sections whose shunt inductors combine in parallel.
A larger Rv means a higher loaded Q: a steeper highpass and a narrower match. Stdlib only.
"""
import csv
import math
import re


def _w(f_mhz):
    return 2.0 * math.pi * f_mhz * 1e6


def design(zs, rl, f_mhz, rv):
    """Ideal (C1 pF, L nH, C2 pF) matching zs -> rl at f_mhz through virtual resistance rv."""
    rs, xs = zs.real, zs.imag
    if rv <= max(rs, rl):
        raise ValueError(f"Rv {rv} must exceed Rs {rs} and RL {rl}")
    q1, q2 = math.sqrt(rv / rs - 1.0), math.sqrt(rv / rl - 1.0)
    x1 = -q1 * rs - xs                        # series reactance on the source side, source reactance absorbed
    if x1 >= 0:
        raise ValueError(f"source reactance {xs:+.1f} too capacitive for a highpass T at Rv {rv}; raise Rv")
    x2 = -q2 * rl
    xl = 1.0 / (q1 / rv + q2 / rv)            # the two shunt L-section inductors (Rv/q1, Rv/q2) in parallel
    w = _w(f_mhz)
    return -1e12 / (w * x1), xl / w * 1e9, -1e12 / (w * x2)


def _abcd(c1_pf, l_nh, c2_pf, f_mhz):
    w = _w(f_mhz)
    z1, z3 = 1.0 / (1j * w * c1_pf * 1e-12), 1.0 / (1j * w * c2_pf * 1e-12)
    y2 = 1.0 / (1j * w * l_nh * 1e-9)
    a, b, c, d = 1.0, z1, 0.0, 1.0            # [1 z1; 0 1] x [1 0; y2 1] x [1 z3; 0 1]
    a, b, c, d = a + b * y2, b, c + d * y2, d
    return a, a * z3 + b, c, c * z3 + d


def input_impedance(c1_pf, l_nh, c2_pf, rl, f_mhz):
    """Impedance looking into C1 with rl on the far side of C2."""
    a, b, c, d = _abcd(c1_pf, l_nh, c2_pf, f_mhz)
    return (a * rl + b) / (c * rl + d)


def reflection(c1_pf, l_nh, c2_pf, zs, rl, f_mhz):
    """|Gamma| at the source: power-wave reflection between zs and the network input."""
    zin = input_impedance(c1_pf, l_nh, c2_pf, rl, f_mhz)
    return abs((zin - zs.conjugate()) / (zin + zs))


def transducer_gain_db(c1_pf, l_nh, c2_pf, zs, rl, f_mhz):
    """Power delivered to rl over the power available from zs, in dB (0 dB = matched and lossless)."""
    a, b, c, d = _abcd(c1_pf, l_nh, c2_pf, f_mhz)
    gt = 4.0 * zs.real * rl / abs(a * rl + b + c * zs * rl + d * zs) ** 2
    return 10.0 * math.log10(gt)


def stock_values(csv_path, extra_pf=(2.7,)):
    """(capacitors pF, inductors nH) available on the bench: 0603 rows of the bench-stock csv plus extra_pf."""
    caps, inds = set(extra_pf), set()
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["package"] != "0603":
                continue
            m = re.fullmatch(r"([0-9.]+)(pF|nH)", row["value"])
            if m:
                (caps if m.group(2) == "pF" else inds).add(float(m.group(1)))
    return sorted(caps), sorted(inds)


def _nearest(values, target):
    return min(values, key=lambda v: abs(math.log(v / target)))


def stock_fits(zs, rl, f_mhz, caps, inds, rv_grid):
    """Every ideal design on rv_grid rounded to stock values: [{'rv', 'ideal', 'stock', 'gamma'}] (infeasible Rv skipped)."""
    out = []
    for rv in rv_grid:
        try:
            ideal = design(zs, rl, f_mhz, rv)
        except ValueError:
            continue
        pick = (_nearest(caps, ideal[0]), _nearest(inds, ideal[1]), _nearest(caps, ideal[2]))
        out.append({"rv": rv, "ideal": ideal, "stock": pick, "gamma": reflection(*pick, zs, rl, f_mhz)})
    return out


def best_stock_fit(zs, rl, f_mhz, caps, inds, rv_grid):
    """The stock-rounded design with the smallest |Gamma| at f_mhz."""
    fits = stock_fits(zs, rl, f_mhz, caps, inds, rv_grid)
    if not fits:
        raise ValueError(f"no highpass T fit for {zs} on the Rv grid")
    return min(fits, key=lambda d: d["gamma"])


def rejection_fit(zs, rl, f_mhz, caps, inds, reject_mhz=850.0, gamma_max=0.15, rv_step=10, rv_max=1500):
    """Among stock-rounded fits with |Gamma| < gamma_max at f_mhz, the one that rejects reject_mhz most (lowest
    transducer gain there); the smallest-|Gamma| fit when none is that good."""
    grid = range(int(max(zs.real, rl)) + rv_step, rv_max, rv_step)
    fits = stock_fits(zs, rl, f_mhz, caps, inds, grid)
    if not fits:
        raise ValueError(f"no highpass T fit for {zs} on the Rv grid")
    good = [d for d in fits if d["gamma"] < gamma_max] or [min(fits, key=lambda d: d["gamma"])]
    return min(good, key=lambda d: transducer_gain_db(*d["stock"], zs, rl, reject_mhz))
