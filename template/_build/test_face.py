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


def test_fillet_closes():
    items = faceplate.fillet([(0, 0), (10, 0), (10, 10), (0, 10)], 2.0)
    assert sum(1 for i in items if i[0] == 'arc') == 4


def test_tayda_lines():
    lines = faceplate.tayda_lines([(202.5, 62.75)], [-38.0, 0.0, 38.0])
    assert lines[0] == 'A\t8.2\t-38.0\t-55.0'                          # Tayda's own format keeps one decimal
    assert 'A\t12.4\t45.0\t0.0' in lines and 'A\t5.2\t27.4\t38.0' in lines
    assert lines[-1].startswith('C\t0\t')                               # side C copied last
