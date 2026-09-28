"""Coplanar-strip (CPS) transmission line on a dielectric slab: two parallel traces of width w with gap s on one
face of a substrate of thickness h (no ground plane). Closed-form conformal-mapping result (Gupta, Garg, Bahl and
Bhartia, "Microstrip Lines and Slotlines", 2nd ed., sec. 7.4); used to size the phasing stubs of the PCB collinear
(bead kicad-gpmd.2). Lengths in mm, frequency in MHz. Stdlib only.
"""
import math

C_MM_MHZ = 299792.458          # speed of light, mm * MHz


def _agm(a, b):
    while abs(a - b) > 1e-15 * a:
        a, b = (a + b) / 2.0, math.sqrt(a * b)
    return a


def ellip_k(k):
    """Complete elliptic integral of the first kind K(k), modulus 0 <= k < 1, by the arithmetic-geometric mean."""
    if not 0.0 <= k < 1.0:
        raise ValueError(f"modulus must be in [0, 1): {k}")
    return math.pi / (2.0 * _agm(1.0, math.sqrt(1.0 - k * k)))


def ellip_k_comp(k):
    """K(k') with k' = sqrt(1 - k^2), for 0 < k <= 1; computed from k directly so it stays finite for tiny k."""
    if not 0.0 < k <= 1.0:
        raise ValueError(f"modulus must be in (0, 1]: {k}")
    return math.pi / (2.0 * _agm(1.0, k))


def cps(w, s, h, er):
    """(Z0 ohm, eps_eff) of coplanar strips: trace width w, gap s, substrate thickness h, relative permittivity er."""
    k = s / (s + 2.0 * w)
    x1, x2 = math.pi * s / (4.0 * h), math.pi * (s + 2.0 * w) / (4.0 * h)
    k1 = math.exp(x1 - x2) * math.expm1(-2.0 * x1) / math.expm1(-2.0 * x2)     # sinh(x1)/sinh(x2), overflow-free
    eps_eff = 1.0 + (er - 1.0) / 2.0 * (ellip_k_comp(k) * ellip_k(k1)) / (ellip_k(k) * ellip_k_comp(k1))
    z0 = 120.0 * math.pi / math.sqrt(eps_eff) * ellip_k(k) / ellip_k_comp(k)
    return z0, eps_eff


def quarter_wave_mm(f_mhz, eps_eff=1.0):
    """Physical length of a quarter wavelength at f_mhz on a line with the given effective permittivity."""
    return C_MM_MHZ / f_mhz / 4.0 / math.sqrt(eps_eff)
