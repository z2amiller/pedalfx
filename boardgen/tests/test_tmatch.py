import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tmatch import (best_stock_fit, design, input_impedance, reflection, rejection_fit, stock_fits,  # noqa: E402
                    stock_values, transducer_gain_db)

BENCH = Path(__file__).resolve().parents[3] / "util-UHFModule" / "docs" / "lcsc-bench-stock.csv"


def test_symmetric_design_is_symmetric_and_matched():
    c1, l, c2 = design(50 + 0j, 50.0, 1090.0, 100.0)
    assert abs(c1 - c2) < 1e-9
    assert abs(input_impedance(c1, l, c2, 50.0, 1090.0) - 50) < 1e-6


@pytest.mark.parametrize("zs", [150 - 60j, 150 + 40j, 120 - 10j, 30 + 5j])
def test_complex_source_gets_conjugate_match(zs):
    c1, l, c2 = design(zs, 50.0, 1090.0, 250.0)
    assert abs(input_impedance(c1, l, c2, 50.0, 1090.0) - zs.conjugate()) < 1e-6
    assert reflection(c1, l, c2, zs, 50.0, 1090.0) < 1e-9
    assert abs(transducer_gain_db(c1, l, c2, zs, 50.0, 1090.0)) < 1e-9


def test_it_is_a_highpass():
    c1, l, c2 = design(150 - 60j, 50.0, 1090.0, 250.0)
    at = [transducer_gain_db(c1, l, c2, 150 - 60j, 50.0, f) for f in (500, 700, 900, 1090)]
    assert at == sorted(at) and at[0] < -6


def test_rv_below_the_terminations_is_rejected():
    with pytest.raises(ValueError):
        design(150 + 0j, 50.0, 1090.0, 120.0)


def test_very_capacitive_source_is_rejected():
    with pytest.raises(ValueError):
        design(60 - 200j, 50.0, 1090.0, 100.0)


def test_stock_fit_uses_bench_values():
    if not BENCH.exists():
        pytest.skip("util-UHFModule not checked out beside pedalfx")
    caps, inds = stock_values(BENCH)
    assert 2.7 in caps and 5.6 in inds and 150.0 in inds
    fit = best_stock_fit(150 - 60j, 50.0, 1090.0, caps, inds, range(160, 600, 10))
    assert fit["stock"][0] in caps and fit["stock"][1] in inds and fit["stock"][2] in caps
    assert fit["gamma"] < 0.33                       # better than -10 dB with standard values


def test_stock_fits_lists_every_feasible_rv_and_best_is_the_minimum():
    if not BENCH.exists():
        pytest.skip("util-UHFModule not checked out beside pedalfx")
    caps, inds = stock_values(BENCH)
    fits = stock_fits(205 - 100j, 50.0, 1090.0, caps, inds, [150, 250, 300, 400])
    assert [f["rv"] for f in fits] == [300, 400]    # 150 is below Rs; at 250 the +100j source needs a series L
    best = best_stock_fit(205 - 100j, 50.0, 1090.0, caps, inds, [150, 250, 300, 400])
    assert best["gamma"] == min(f["gamma"] for f in fits)


def test_rejection_fit_trades_match_for_rejection_within_the_limit():
    if not BENCH.exists():
        pytest.skip("util-UHFModule not checked out beside pedalfx")
    caps, inds = stock_values(BENCH)
    z = 205 - 100j
    rej = rejection_fit(z, 50.0, 1090.0, caps, inds)
    best = best_stock_fit(z, 50.0, 1090.0, caps, inds, range(215, 1500, 10))
    assert rej["gamma"] < 0.15
    assert transducer_gain_db(*rej["stock"], z, 50.0, 850.0) <= transducer_gain_db(*best["stock"], z, 50.0, 850.0)
