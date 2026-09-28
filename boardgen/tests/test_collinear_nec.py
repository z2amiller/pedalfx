import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("PyNEC")
from collinear_nec import Collinear, evaluate, feed_resonance  # noqa: E402
from dipole_nec import POUR_MODULE_BACK, POUR_MODULE_FRONT, resonance, sweep  # noqa: E402

QW = 68.759                    # quarter wave in air at 1090 MHz, mm
MOD = (POUR_MODULE_BACK, POUR_MODULE_FRONT)


def test_centre_only_is_the_dipole_model():
    want, _ = resonance(sweep(50, 6, 30, MOD, f0=950, f1=1250, n=121))
    got, _ = feed_resonance(Collinear(centre_arm=50, outer=[], stub_elec=[]))
    assert abs(got - want) < 0.5, (got, want)


def test_three_elements_beat_the_dipole():
    dipole = evaluate(Collinear(centre_arm=49.2, outer=[], stub_elec=[]))["gain_dbi"]
    three = evaluate(Collinear(centre_arm=46, outer=[110], stub_elec=[1.1 * QW]))["gain_dbi"]
    assert three > dipole + 1.0, (three, dipole)


def test_a_wrong_length_stub_loses_the_gain():
    good = evaluate(Collinear(centre_arm=46, outer=[110], stub_elec=[1.1 * QW]))["gain_dbi"]
    bad = evaluate(Collinear(centre_arm=46, outer=[110], stub_elec=[0.5 * QW]))["gain_dbi"]
    assert bad < good - 1.0, (bad, good)


def test_longer_outer_elements_lower_the_resonance():
    f = [feed_resonance(Collinear(centre_arm=46, outer=[lo], stub_elec=[1.1 * QW]))[0] for lo in (104, 110, 116)]
    assert all(v is not None for v in f), f
    assert f[0] > f[1] > f[2], f


def test_five_elements_build():
    r = evaluate(Collinear(centre_arm=46, outer=[95, 95], stub_elec=[QW, QW]))
    assert r["z"].real > 0


def test_necpp_failures_are_nudged(monkeypatch):
    import collinear_nec
    calls = []
    real = collinear_nec._run

    def flaky(c, *a):
        calls.append(c.centre_arm)
        if len(calls) == 1:
            raise RuntimeError("Unknown exception")
        return real(c, *a)
    monkeypatch.setattr(collinear_nec, "_run", flaky)
    r = evaluate(Collinear(centre_arm=46, outer=[110], stub_elec=[1.1 * QW]))
    assert r["z"].real > 0 and calls == [46, 46.05]


def test_thin_stub_junction_builds_and_matters_a_little():
    thick = evaluate(Collinear(centre_arm=46, outer=[110], stub_elec=[1.1 * QW], stub_axial=6.9))
    thin = evaluate(Collinear(centre_arm=46, outer=[110], stub_elec=[1.1 * QW], stub_axial=6.9, stub_r=0.25))
    assert thin["z"] != thick["z"]
    assert abs(thin["gain_dbi"] - thick["gain_dbi"]) < 0.5
