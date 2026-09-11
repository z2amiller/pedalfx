import re, subprocess, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dipole_arms import arm_footprint, ARMS_1090, ARMS_772

REPOS = Path(__file__).resolve().parents[3]

def strip_uuids(t):
    return re.sub(r'\(uuid "[^"]+"\)', '(uuid X)', t)

def committed(repo, rel):
    if not (REPOS / repo / ".git").exists():
        pytest.skip(f"{repo} not checked out beside pedalfx")
    proc = subprocess.run(["git", "-C", str(REPOS / repo), "show", f"HEAD:{rel}"], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout

def test_1090_matches_fabbed():
    want = committed("util-Antenna1090", "util-Antenna1090.pretty/Dipole_1090_Arms.kicad_mod")
    assert strip_uuids(arm_footprint(**ARMS_1090)) == strip_uuids(want)

def test_772_matches_fabbed():
    want = committed("util-Antenna772", "util-Antenna772.pretty/Dipole_772_Arms.kicad_mod")
    assert strip_uuids(arm_footprint(**ARMS_772)) == strip_uuids(want)

def test_landing_window_adds_two_mask_rects_only():
    base, landed = arm_footprint(**ARMS_1090), arm_footprint(**ARMS_1090, landing=3.5)
    extra = [l for l in strip_uuids(landed).splitlines() if l not in strip_uuids(base).splitlines()]
    assert len(extra) == 2 and all('(layer "F.Mask")' in l for l in extra), extra
    assert any('(start -18.5 -3) (end -15 3)' in l for l in extra), extra
    assert any('(start 15 -3) (end 18.5 3)' in l for l in extra), extra

def test_landing_window_adds_two_mask_rects_only_772():
    base, landed = arm_footprint(**ARMS_772), arm_footprint(**ARMS_772, landing=3.5)
    extra = [l for l in strip_uuids(landed).splitlines() if l not in strip_uuids(base).splitlines()]
    assert len(extra) == 2 and all('(layer "F.Mask")' in l for l in extra), extra
    assert any('(start -18.5 -4) (end -15 4)' in l for l in extra), extra
    assert any('(start 15 -4) (end 18.5 4)' in l for l in extra), extra
