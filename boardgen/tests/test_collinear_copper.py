import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collinear_copper import (ISLAND_STEP, NECK, PAD_0603, UFL_GND_Y, UFL_SIG_X, Stub, collinear_footprint,  # noqa: E402
                              coupon_footprint, fold, layout, mousebite_footprint, stub_copper)

ST = Stub(length=44.91)


def length_to(path, y_stop):
    """Centreline length along a path whose last segment runs up (towards y_stop)."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        if (x1, y1) == path[-2]:
            return total + abs(y1 - y_stop)
        total += math.hypot(x2 - x1, y2 - y1)
    raise AssertionError("empty path")


@pytest.mark.parametrize("ya0,yb0", [(0.0, 0.0), (0.0, -UFL_GND_Y)])
@pytest.mark.parametrize("m", [40.91, 42.91, 44.91, 46.91, 48.91])
def test_mean_centreline_length_hits_every_ladder_position(ya0, yb0, m):
    f = fold(ST, 10.0, ya0, yb0)
    y = f["y_at"](m)
    assert abs((length_to(f["A"], y) + length_to(f["B"], y)) / 2 - m) < 1e-9


def test_fold_stays_on_the_board_and_above_the_element():
    f = fold(ST, 10.0)
    ys = [p[1] for p in f["A"] + f["B"]]
    assert min(ys) - ST.w / 2 >= ST.top_limit
    assert f["y_at"](ST.length - ST.steps * ST.step) == pytest.approx(ST.bot - ST.margin)
    assert ST.bot + ST.pitch + ST.w / 2 <= -3.0 - 1.0          # lower turn 1 mm clear of a 6 mm strip's top edge


def test_too_long_a_stub_is_refused():
    with pytest.raises(ValueError):
        fold(Stub(length=70.0), 0.0)


def test_layout_junction_matches_the_model_and_islands_step():
    L = layout(centre_arm=45.5, outer=84.6, stub=ST)
    assert L["xo"] - L["xe"] == pytest.approx(2 * NECK + ST.s)        # 6.9 mm, STUB_AXIAL in the NEC study
    assert L["x_tp"] - PAD_0603[0] / 2 < L["tip"]                        # tip pad overlaps the last bar
    (c0, i0), (c1, i1) = L["islands"]
    assert i1 - i0 == pytest.approx(ISLAND_STEP) and i0 - L["x_tp"] == pytest.approx(1.825)


def test_stub_pads_and_bars_count():
    sc = stub_copper(ST, 10.0)
    assert len(sc["bars"]) == ST.steps + 1 and len(sc["pads"]) == 2 * ST.steps


def test_footprint_pads():
    t = collinear_footprint(name="X", generator="t", descr="d", tags="t", centre_arm=45.5, outer=84.6, stub=ST)
    nums = re.findall(r'\(pad "([^"]*)" (\w+) (\w+)', t)
    assert sum(1 for n, *_ in nums if n == "") == 4                              # two islands per side
    assert sum(1 for n, k, sh in nums if n in "12" and n and sh == "rect") == 2 * (2 * ST.steps + 1)   # 0R pads + tip pads
    assert {n for n, *_ in nums} == {"", "1", "2"}
    assert t.count('(layer "F.Mask")') == 2 * (1 + (ST.steps + 1) + 8)         # landing, short bars, ladder bridges


def test_coupon_clears_the_ufl():
    sc = stub_copper(ST, UFL_SIG_X - 0.225, 0.0, -UFL_GND_Y)
    a_run1 = sc["rects"][0]                                  # trace A, first (rising) segment
    assert a_run1[2] <= -1.1 - 0.2 + 1e-9                    # 0.2 mm clear of the upper ground pad (x -1.1..1.1)
    assert a_run1[0] < UFL_SIG_X + 0.525 and a_run1[2] > UFL_SIG_X - 0.525      # overlaps the signal pad
    keepout = (-0.99, -0.95, 1.1, 0.95)
    for r in sc["rects"]:
        assert r[2] <= keepout[0] or r[0] >= keepout[2] or r[3] <= keepout[1] or r[1] >= keepout[3], r
    assert '(pad "1" smd custom' in coupon_footprint(name="C", generator="t", descr="d", stub=ST)


def test_mousebites():
    t = mousebite_footprint(name="M", generator="t")
    assert t.count("np_thru_hole") == 5
