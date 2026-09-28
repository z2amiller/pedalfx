import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cps import cps, ellip_k, ellip_k_comp, quarter_wave_mm  # noqa: E402


def test_ellip_k_known_values():
    assert ellip_k(0.0) == math.pi / 2
    assert abs(ellip_k(1 / math.sqrt(2)) - 1.854074677301372) < 1e-12      # Gamma(1/4)^2 / (4 sqrt(pi))
    assert abs(ellip_k_comp(1 / math.sqrt(2)) - ellip_k(1 / math.sqrt(2))) < 1e-12
    assert abs(ellip_k_comp(0.6) - ellip_k(0.8)) < 1e-12


def test_air_line_is_pure_geometry():
    z0, eps = cps(0.9, 0.9, 1.6, 1.0)
    k = 0.9 / 2.7
    assert eps == 1.0
    assert abs(z0 - 120 * math.pi * ellip_k(k) / ellip_k(math.sqrt(1 - k * k))) < 1e-9
    assert 240 < z0 < 242              # w = s: k = 1/3, the textbook ~241 ohm air coplanar strips


def test_substrate_limits():
    """A thick slab fills the lower half space (eps -> (er+1)/2); a thinning slab tends to air (eps -> 1)."""
    eps = [cps(0.9, 0.9, h, 4.5)[1] for h in (0.02, 0.2, 1.6, 1000.0)]
    assert eps == sorted(eps)
    assert abs(eps[-1] - (4.5 + 1) / 2) < 0.01 * (4.5 + 1) / 2
    assert eps[0] < 1.1


def test_fr4_stub_is_between_air_and_half_filled():
    z0, eps = cps(0.9, 0.9, 1.6, 4.5)
    assert 2.4 < eps < 2.75          # mostly-filled half space: a 1.6 mm slab under 0.9 mm traces
    assert 140 < z0 < 160


def test_quarter_wave():
    assert abs(quarter_wave_mm(1090.0) - 68.759) < 0.01
    assert abs(quarter_wave_mm(1090.0, 4.0) - 68.759 / 2) < 0.01
