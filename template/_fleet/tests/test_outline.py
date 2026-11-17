"""pedal-fleet outline: Edge.Cuts micro-gaps, stubs, collinear splits, fold-backs and exact closure."""
import difflib
import itertools

import pytest

from pedalfleet import cli, outline
from tests.helpers import write_project

_ids = itertools.count(1)
KICAD = ["/Applications/KiCad/KiCad.app/Contents/MacOS/pcbnew x.kicad_pcb"]


def _uuid():
    return f"00000000-0000-0000-0000-{next(_ids):012d}"


def _tail(uuid=None):
    return (f'\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type default)\n\t\t)\n\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{uuid or _uuid()}")\n\t)\n')


def line(a, b, uuid=None):
    return f"\t(gr_line\n\t\t(start {a[0]} {a[1]})\n\t\t(end {b[0]} {b[1]})\n" + _tail(uuid)


def arc(a, m, b):
    return f"\t(gr_arc\n\t\t(start {a[0]} {a[1]})\n\t\t(mid {m[0]} {m[1]})\n\t\t(end {b[0]} {b[1]})\n" + _tail()


def circle(c, r):
    return f"\t(gr_circle\n\t\t(center {c[0]} {c[1]})\n\t\t(end {c[0] + r} {c[1]})\n" + _tail()


def board(*shapes):
    return '(kicad_pcb\n\t(version 20260206)\n\t(generator "pcbnew")\n' + "".join(shapes) + ")\n"


# A 20 x 10 mm board with 1 mm corner fillets, split into its parts so tests can swap one out.
TOP = line((1, 0), (19, 0))
TR = arc((19, 0), (19.707107, 0.292893), (20, 1))
RIGHT = line((20, 1), (20, 9))
BR = arc((20, 9), (19.707107, 9.707107), (19, 10))
BOTTOM = line((19, 10), (1, 10))
BL = arc((1, 10), (0.292893, 9.707107), (0, 9))
LEFT = line((0, 9), (0, 1))
TL = arc((0, 1), (0.292893, 0.292893), (1, 0))


def rounded(top=TOP, left=LEFT, extra=""):
    return board(top, TR, RIGHT, BR, BOTTOM, BL, left, TL, extra)


def changed_lines(old, new):
    """(removed, added) lines of a line diff."""
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))
    removed = [d[1:] for d in diff if d.startswith("-") and not d.startswith("---")]
    added = [d[1:] for d in diff if d.startswith("+") and not d.startswith("+++")]
    return removed, added


def kinds(result):
    return [f.kind for f in result.plan.findings]


def test_number_format_round_trip():
    for text in ("104.977735", "-0.5", "58", "0.000001", "-104.9"):
        assert outline.fmt_nm(outline.to_nm(text)) == text
    assert outline.to_nm("104.89") == 104_890_000


def test_clean_outline_is_left_alone():
    text = rounded()
    result = outline.analyse(text)
    assert result.clean and not result.plan.findings and not result.plan.changes
    assert result.closure.summary() == "closes exactly: 1 board outline, 0 cutout(s)"
    assert result.text == text


def test_gap_between_collinear_lines_snaps_to_the_coarser_grid_then_merges():
    # the back-bipolar-15 case: two halves of an edge 0.010 mm apart
    left_half = line((1, 0), (9.99, 0))
    right_half = line((10, 0), (19, 0))
    text = rounded(top=left_half + right_half)
    result = outline.analyse(text)
    assert kinds(result) == ["gap", "collinear"]
    gap = result.plan.findings[0].text
    assert "0.0100 mm" in gap and "keep the end on the 1 mm grid" in gap
    assert not result.closure.closed and "2 unmatched end(s)" in result.closure.summary()
    assert result.heals and result.healed is not None and result.healed.ok and not result.leftover
    removed, added = changed_lines(text, result.text)
    assert added == ["\t\t(end 19 0)"]                       # the left half now spans the edge
    assert removed[0] == "\t\t(end 9.99 0)" and "\t\t(start 10 0)" in removed  # the right half is gone
    assert outline.analyse(result.text).clean


def test_line_end_moves_onto_the_arc_end_not_the_reverse():
    # a 3 um miss; the arc end is off grid, but moving it would change the arc's radius and centre
    arc_end = arc((0, 1), (0.292893, 0.292893), (1.000003, 0))
    text = board(TOP, TR, RIGHT, BR, BOTTOM, BL, LEFT, arc_end)
    result = outline.analyse(text)
    assert kinds(result) == ["gap"] and "move the line end onto the arc end" in result.plan.findings[0].text
    removed, added = changed_lines(text, result.text)
    assert (removed, added) == (["\t\t(start 1 0)"], ["\t\t(start 1.000003 0)"])
    assert arc_end in result.text and result.healed is not None and result.healed.ok


def test_stub_is_dropped_and_its_neighbours_joined():
    # a 0.008 mm stub in the middle of an edge
    text = rounded(top=line((1, 0), (10, 0)) + line((10, 0), (10.008, 0)) + line((10.008, 0), (19, 0)))
    result = outline.analyse(text)
    assert kinds(result) == ["stub", "gap", "collinear"]
    assert "0.0080 mm long" in result.plan.findings[0].text and "(left by the stub)" in result.plan.findings[1].text
    assert result.heals and result.healed is not None and result.healed.ok and outline.analyse(result.text).clean
    top = [s for s in outline.parse(result.text) if s.kind == "line" and s.pts["start"][1] == 0]
    assert len(top) == 1 and {top[0].pts["start"], top[0].pts["end"]} == {(1_000_000, 0), (19_000_000, 0)}


def test_stub_between_a_line_and_an_arc_goes_and_the_line_meets_the_arc():
    text = rounded(top=line((1, 0), (1.007, 0)) + line((1.007, 0), (19, 0)))
    result = outline.analyse(text)
    assert kinds(result) == ["stub", "gap"]
    assert result.heals and outline.analyse(result.text).clean
    assert "\t\t(start 1 0)\n\t\t(end 19 0)" in result.text


def test_zero_length_line_is_a_stub():
    text = rounded(extra=line((20, 1), (20, 1)))
    result = outline.analyse(text)
    assert kinds(result) == ["stub"] and "3+ ends meet" in result.closure.summary()
    assert result.heals and outline.analyse(result.text).clean


@pytest.mark.parametrize("end_x, tol", [(9.8, 0.05), (9.95, 0.05)])
def test_open_outline_beyond_the_tolerance_is_reported_not_healed(end_x, tol):
    # 0.2 mm is a real gap; 0.05 mm is not *closer* than the 0.05 mm tolerance
    text = rounded(top=line((1, 0), (end_x, 0)) + line((10, 0), (19, 0)))
    result = outline.analyse(text, tol)
    assert kinds(result) == ["open", "open"] and not any(f.fixable for f in result.plan.findings)
    assert not result.plan.changes and result.text == text
    assert "unmatched" in result.closure.summary()


def test_a_larger_tolerance_heals_what_the_default_reports_as_open():
    text = rounded(top=line((1, 0), (9.8, 0)) + line((10, 0), (19, 0)))
    result = outline.analyse(text, tol=0.3)
    assert result.heals and outline.analyse(result.text).clean


def test_grid_rule_looks_at_the_coordinate_that_differs():
    # util-BiasTee: same off-grid x on both ends; y = 20 beats y = 19.995363, keeping both lines axis-aligned
    text = board(line((100, 20), (116.938604, 20)), line((116.938604, 19.995363), (116.938604, 30)),
                 line((116.938604, 30), (100, 30)), line((100, 30), (100, 20)))
    result = outline.analyse(text)
    assert kinds(result) == ["gap"] and "1 mm grid" in result.plan.findings[0].text
    assert changed_lines(text, result.text) == (["\t\t(start 116.938604 19.995363)"], ["\t\t(start 116.938604 20)"])


def test_fold_back_is_reported_and_heals_as_a_stub_with_the_suggested_tolerance():
    # fx-SixSeven: a 0.075 mm line doubles back over its neighbour on one edge
    folded = line((0, 9), (0, 4.925)) + line((0, 4.925), (0, 5)) + line((0, 5), (0, 1))
    text = rounded(left=folded)
    result = outline.analyse(text)
    assert kinds(result) == ["fold-back"] and "--tol 0.08" in result.plan.findings[0].text
    assert "overlaps itself" in result.closure.summary() and not result.plan.changes
    healed = outline.analyse(text, tol=0.08)
    assert healed.heals and outline.analyse(healed.text, tol=0.08).clean


def test_stub_between_two_arcs_is_kept_and_the_rest_still_heals():
    split_corner = (arc((19, 0), (19.382683, 0.07612), (19.707107, 0.292893))
                    + line((19.707107, 0.292893), (19.714, 0.3))
                    + arc((19.714, 0.3), (19.92388, 0.617317), (20, 1)))
    text = board(line((1, 0), (9.99, 0)), line((10, 0), (19, 0)), split_corner, RIGHT, BR, BOTTOM, BL, LEFT, TL)
    result = outline.analyse(text)
    stub = next(f for f in result.plan.findings if f.kind == "stub")
    assert not stub.fixable and "kept" in stub.text
    assert result.heals and result.healed is not None and result.healed.ok
    assert [f.kind for f in result.leftover] == ["stub"]
    assert "(start 19.707107 0.292893)" in result.text


def test_dropped_shape_leaves_its_group():
    keep, gone = _uuid(), _uuid()
    group = f'\t(group ""\n\t\t(uuid "{_uuid()}")\n\t\t(members "{keep}" "{gone}")\n\t)\n'
    text = rounded(top=line((1, 0), (10, 0), keep) + line((10, 0), (19, 0), gone), extra=group)
    result = outline.analyse(text)
    assert kinds(result) == ["collinear"]
    assert f'(members "{keep}")' in result.text and gone not in result.text


def test_footprint_edge_cuts_are_read_only_context():
    # an off-centre notch drawn by a footprint rotated 180 degrees: local (3,0)->(3,-2)->(-1,-2)->(-1,0)
    # is board (7,0)->(7,2)->(11,2)->(11,0); the board line misses the footprint by 4 um and moves onto it
    def fp_line(a, b):
        return (f"\t\t(fp_line\n\t\t\t(start {a[0]} {a[1]})\n\t\t\t(end {b[0]} {b[1]})\n\t\t\t(stroke\n"
                f'\t\t\t\t(width 0.05)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(layer "Edge.Cuts")\n'
                f'\t\t\t(uuid "{_uuid()}")\n\t\t)\n')
    footprint = (f'\t(footprint "Fleet:Notch"\n\t\t(layer "F.Cu")\n\t\t(uuid "{_uuid()}")\n\t\t(at 10 0 180)\n'
                 f'\t\t(property "Reference" "J1"\n\t\t\t(at 0 0 0)\n\t\t\t(layer "F.SilkS")\n'
                 f'\t\t\t(uuid "{_uuid()}")\n\t\t)\n'
                 + fp_line((3, 0), (3, -2)) + fp_line((3, -2), (-1, -2)) + fp_line((-1, -2), (-1, 0)) + "\t)\n")
    text = rounded(top=line((1, 0), (6.996, 0)) + line((11, 0), (19, 0)), extra=footprint)
    result = outline.analyse(text)
    assert sum(1 for s in result.shapes if s.footprint == "J1") == 3
    assert kinds(result) == ["gap"] and "move the board line's end onto footprint J1's" in result.plan.findings[0].text
    assert changed_lines(text, result.text) == (["\t\t(end 6.996 0)"], ["\t\t(end 7 0)"])
    assert footprint in result.text and result.healed is not None and result.healed.ok


def test_footprint_to_footprint_gap_is_reported_not_healed():
    text = rounded()
    shapes = outline.parse(text)
    for shape in shapes:
        shape.footprint = "U1"
    shapes[0].pts["start"] = (1_000_004, 0)
    plan = outline.heal_plan(shapes, 50_000)
    assert [f.kind for f in plan.findings] == ["gap"] and not plan.findings[0].fixable and not plan.changes


def test_self_crossing_outline_does_not_close():
    text = board(line((0, 0), (10, 10)), line((10, 10), (10, 0)), line((10, 0), (0, 10)), line((0, 10), (0, 0)))
    closure = outline.analyse(text).closure
    assert not closure.closed and "crosses or overlaps itself at (5.0000, 5.0000)" in closure.summary()


def test_cutouts_and_separate_outlines():
    inside = outline.analyse(rounded(extra=circle((10, 5), 1)))
    assert inside.closure.ok and inside.closure.summary() == "closes exactly: 1 board outline, 1 cutout(s)"
    outside = outline.analyse(rounded(extra=circle((10, 30), 1)))
    assert outside.closure.closed and not outside.closure.ok
    assert "2 separate board outlines" in outside.closure.summary() and outside.defects() == []


# ---------------------------------------------------------------- command line

def gap_board(tmp_path, name="fx-O"):
    p = write_project(tmp_path / name, name)
    p.pcb.write_text(rounded(top=line((1, 0), (9.99, 0)) + line((10, 0), (19, 0))))
    return p


def run(argv, capsys):
    code = cli.main(argv)
    return code, capsys.readouterr().out


def test_cli_check_is_read_only_and_exits_1_on_findings(tmp_path, capsys):
    p = gap_board(tmp_path)
    before = p.pcb.read_text()
    code, out = run(["outline", str(p.dir), "--no-process-check"], capsys)
    assert code == 1 and "gap 0.0100 mm" in out and "--fix heals this" in out
    assert p.pcb.read_text() == before


def test_cli_dry_run_prints_the_diff_and_writes_nothing(tmp_path, capsys):
    p = gap_board(tmp_path)
    before = p.pcb.read_text()
    code, out = run(["outline", str(p.dir), "--dry-run", "--no-process-check"], capsys)
    assert code == 1 and "+\t\t(end 19 0)" in out
    assert "nothing written (dry run): 1 end(s) moved, 1 shape(s) removed" in out
    assert p.pcb.read_text() == before


def test_cli_fix_writes_then_the_board_checks_clean(tmp_path, capsys):
    p = gap_board(tmp_path)
    code, out = run(["outline", str(p.dir), "--fix", "--no-process-check"], capsys)
    assert code == 0 and "wrote fx-O.kicad_pcb: 1 end(s) moved, 1 shape(s) removed" in out
    code, out = run(["outline", str(p.dir), "--fix", "--no-process-check"], capsys)
    assert code == 0 and "clean; closes exactly: 1 board outline, 0 cutout(s)" in out


def test_cli_fix_writes_nothing_for_a_real_open_outline(tmp_path, capsys):
    p = write_project(tmp_path / "fx-O", "fx-O")
    p.pcb.write_text(rounded(top=line((1, 0), (9.8, 0)) + line((10, 0), (19, 0))))
    before = p.pcb.read_text()
    code, out = run(["outline", str(p.dir), "--fix", "--no-process-check"], capsys)
    assert code == 1 and "nothing to heal automatically; fix by hand" in out
    assert p.pcb.read_text() == before


def test_cli_fix_writes_nothing_when_the_healed_outline_still_does_not_close(tmp_path, capsys):
    p = write_project(tmp_path / "fx-O", "fx-O")
    folded = line((0, 9), (0, 4.925)) + line((0, 4.925), (0, 5)) + line((0, 5), (0, 1))
    p.pcb.write_text(rounded(top=line((1, 0), (9.99, 0)) + line((10, 0), (19, 0)), left=folded))
    before = p.pcb.read_text()
    code, out = run(["outline", str(p.dir), "--fix", "--no-process-check"], capsys)
    assert code == 1 and "fold-back" in out and "not written: the healed outline would still not close exactly" in out
    assert p.pcb.read_text() == before


def test_cli_fix_refuses_while_kicad_has_the_board_open(tmp_path, capsys, monkeypatch):
    p = gap_board(tmp_path)
    before = p.pcb.read_text()
    p.lock_files[0].write_text("{}")
    monkeypatch.setattr("pedalfleet.guard.process_commands", lambda: KICAD)
    code, out = run(["outline", str(p.dir), "--fix", "--force"], capsys)
    assert code == 1 and "not touched" in out and "open in KiCad" in out
    assert p.pcb.read_text() == before


def test_cli_sweep_over_boards(tmp_path, capsys):
    repos = tmp_path / "repos"
    gap_board(repos, "fx-A")
    clean = write_project(repos / "fx-B", "fx-B")
    clean.pcb.write_text(rounded())
    write_project(repos / "fx-C", "fx-C")  # no Edge.Cuts yet
    code, out = run(["outline", "--boards", "--repos", str(repos), "--no-process-check"], capsys)
    assert code == 1 and "== fx-A: 9 Edge.Cuts shape(s), 2 finding(s)" in out
    assert "== fx-B: 8 Edge.Cuts shape(s), clean" in out and "== fx-C: no Edge.Cuts shapes" in out
    assert out.strip().endswith("3 projects: 2 clean, 0 healed, 1 with findings, 0 need a hand fix or were not touched")


def test_fleet_check_reports_outline_defects_but_not_collinear_splits(tmp_path, capsys):
    p = gap_board(tmp_path)
    run(["apply", str(p.dir), "--no-process-check"], capsys)
    code, out = run(["check", str(p.dir), "--no-process-check"], capsys)
    assert code == 1 and "OUTLINE: 1 gap(s) (see pedal-fleet outline)" in out and "1 with outline defects" in out
    code, out = run(["check", str(p.dir), "--no-process-check", "--no-outline"], capsys)
    assert code == 0 and "OUTLINE" not in out
    p.pcb.write_text(rounded(top=line((1, 0), (10, 0)) + line((10, 0), (19, 0))))  # split edge, closes exactly
    code, out = run(["check", str(p.dir), "--no-process-check"], capsys)
    assert code == 0 and "OUTLINE" not in out
