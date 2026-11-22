"""Tests for the 1590XX faceplate: geometry (pure), the template fix and the faceplate builder (stdlib + pytest)."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import faceplate  # noqa: E402


def test_mirror_direction():
    assert faceplate.face_x(202.5) == pytest.approx(95.5)
    assert faceplate.board_to_tayda(202.5, 62.75) == pytest.approx((-38.0, -55.0))


def test_template_holes():
    assert faceplate.TEMPLATE_HOLES == [(x, y) for y in (62.75, 88.05) for x in (95.5, 117.5, 139.5, 161.5, 183.5, 205.5)]


def test_led_face():
    assert faceplate.LED_FACE == [(112.5, 128.15), (150.5, 128.15), (188.5, 128.15)]


def test_pharmacist_frame_steps():
    rects = faceplate.frame_rects([(62.75, [95.5, 117.5, 139.5, 161.5]), (88.05, [117.5, 139.5, 161.5])])
    assert rects[0] == pytest.approx((85.5, 54.0, 171.5, 77.15))       # step y = (75.0 + 88.05 - 8.75) / 2
    assert rects[1] == pytest.approx((107.5, 77.15, 171.5, 104.3))      # 88.05 + 12.25 + 4.0
    pts = faceplate.stepped_outline(rects)
    assert len(pts) == 6                                                # one step on the left


def test_frame_snaps_to_grid():
    # the Mocker's real shafts: TONE sits 0.25 mm west of BIAS, which must not make a 0.25 mm step in the frame
    pts = faceplate.frame_for([(183.5, 62.99), (205.41, 62.83), (183.25, 88.15)])
    assert pts == [(173.5, 54.0), (215.5, 54.0), (215.5, 77.15), (193.5, 77.15), (193.5, 104.3), (173.5, 104.3)]


def test_fillet_refuses_short_edges():
    with pytest.raises(ValueError):
        faceplate.fillet([(0, 0), (10, 0), (10, 5), (10.25, 5), (10.25, 10), (0, 10)], 2.0)

def test_fillet_closes():
    items = faceplate.fillet([(0, 0), (10, 0), (10, 10), (0, 10)], 2.0)
    assert sum(1 for i in items if i[0] == 'arc') == 4


def test_tayda_lines():
    lines = faceplate.tayda_lines([(202.5, 62.75)], [-38.0, 0.0, 38.0])
    assert lines[0] == 'A\t8.2\t-38.0\t-55.0'                          # Tayda's own format keeps one decimal
    assert 'A\t12.4\t45.0\t0.0' in lines and 'A\t5.2\t27.4\t38.0' in lines
    assert lines[-1].startswith('C\t0\t')                               # side C copied last


# --- Task 2: the faceplate template ------------------------------------------------------------------------------
import subprocess  # noqa: E402

TEMPLATE = HERE.parent / "1950XXFacePlate" / "1950XXFacePlate.kicad_pcb"
REPO = HERE.parent.parent


def _template_messages():
    from check_face1590xx import check_face
    return check_face(TEMPLATE.read_text(), faceplate.TEMPLATE_HOLES, faceplate.LED_FACE)


def test_template_holes_exact():
    assert [m for m in _template_messages() if "hole" in m] == []


def test_template_trefoils():
    assert [m for m in _template_messages() if "trefoil" in m] == []


def test_template_no_125b():
    msgs = _template_messages()
    assert [m for m in msgs if "125B" in m or "User.4" in m] == []


def test_template_fill_current():
    assert [m for m in _template_messages() if "fill" in m] == []


def test_check_face_flags_old_template():
    from check_face1590xx import check_face
    old = subprocess.run(["git", "show", "ee40ad0:template/1950XXFacePlate/1950XXFacePlate.kicad_pcb"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    msgs = " | ".join(check_face(old, faceplate.TEMPLATE_HOLES, faceplate.LED_FACE))
    for word in ("hole", "trefoil", "125B", "fill"):
        assert word in msgs


# --- Task 3: the faceplate builder, run on the real fx-Revolver board --------------------------------------------
import json  # noqa: E402

KICAD_PYTHON = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
REVOLVER = Path.home() / "Documents/repos/fx-Revolver/fx-Revolver.kicad_pcb"
PHARMACIST = "RV301,RV302,RV303,RV304,RV305,RV306,RV307"
MOCKER = "RV201,RV202,RV203"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not REVOLVER.exists():
        pytest.skip("fx-Revolver board not on this machine")
    out = tmp_path_factory.mktemp("face") / "face-Revolver"
    report = out.parent / "report.json"
    run = subprocess.run([KICAD_PYTHON, str(HERE / "face_1590xx.py"), str(REVOLVER), str(out), "face-Revolver",
                          "--title", "REVOLVER", "--supply", "9-18 VDC", "--frame", PHARMACIST, "--frame", MOCKER,
                          "--report", str(report)], capture_output=True, text=True)
    text = (out / "face-Revolver.kicad_pcb").read_text() if (out / "face-Revolver.kicad_pcb").exists() else ""
    rep = json.loads(report.read_text()) if report.exists() else {}
    return {"out": out, "run": run, "text": text, "report": rep}


def test_face_holes_follow_pots(built):
    from check_face1590xx import board_pots, check_face
    pots = board_pots(REVOLVER.read_text())
    assert len(pots) == 10
    holes = [(faceplate.face_x(sx), sy) for _ref, _ctl, sx, sy in pots]
    msgs = check_face(built["text"], holes, faceplate.LED_FACE)
    assert [m for m in msgs if "hole" in m] == [], built["run"].stderr[-2000:]


def test_face_labels_clear(built):
    from check_face1590xx import board_pots, check_face
    pots = board_pots(REVOLVER.read_text())
    rep = built["report"]
    assert sorted(lab[0] for lab in rep["labels"]) == sorted(ctl for _r, ctl, _x, _y in pots)
    holes = [(faceplate.face_x(sx), sy) for _ref, _ctl, sx, sy in pots]
    msgs = check_face(built["text"], holes, faceplate.LED_FACE, labels=rep["labels"], frames=rep["frames"])
    assert msgs == []
    assert len(rep["frames"]) == 2


def test_face_text(built):
    text = built["text"]
    for s in ('"REVOLVER"', '"9-18 VDC"', '"z2a 2026"'):
        assert s in text
    assert '(gr_text "CONTROL"' not in text and '"PEDALNAME"' not in text


def test_face_tayda(built):
    lines = (built["out"] / "face-Revolver-tayda-drill.txt").read_text().splitlines()
    assert sum(1 for line in lines if line.startswith("A\t8.2\t")) == 10
    assert sum(1 for line in lines if line.startswith("A\t12.4\t")) == 3
    assert sum(1 for line in lines if line.startswith("A\t5.2\t")) == 3
    assert "A\t8.2\t-37.92\t54.91" in lines                            # RV201, shaft (92.59, 62.83)
