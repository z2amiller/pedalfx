import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("PyNEC")
from dipole_nec import report_safe, POUR_1090_INTEGRATED, POUR_772_INTEGRATED

def test_1090_baseline():
    fr, rr = report_safe("1090 baseline", 50, 6, 30, [POUR_1090_INTEGRATED], f0=900, f1=1300, f_mark=1090)
    assert fr and abs(fr - 1078) < 6, fr
    assert rr and 70 < rr < 90, rr

def test_772_baseline():
    fr, rr = report_safe("772 baseline", 76, 8, 30, [POUR_772_INTEGRATED], f0=600, f1=950, f_mark=772)
    assert fr and abs(fr - 762) < 6, fr
