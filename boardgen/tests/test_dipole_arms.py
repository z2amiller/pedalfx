import re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dipole_arms import arm_footprint, ARMS_1090, ARMS_772

REPOS = Path(__file__).resolve().parents[3]

def strip_uuids(t):
    return re.sub(r'\(uuid "[^"]+"\)', '(uuid X)', t)

def committed(repo, rel):
    return subprocess.run(["git", "-C", str(REPOS / repo), "show", f"HEAD:{rel}"], check=True, capture_output=True, text=True).stdout

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
    assert '(start 15 -3) (end 18.5 3)' in extra[1] or '(start 15 -3) (end 18.5 3)' in extra[0]
