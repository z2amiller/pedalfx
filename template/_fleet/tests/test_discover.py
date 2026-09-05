import pytest

from pedalfleet import discover
from tests.helpers import write_project


def test_project_properties(tmp_path):
    p = write_project(tmp_path / "fx-A", "fx-A")
    assert p.name == "fx-A" and p.dir == (tmp_path / "fx-A").resolve()
    assert p.pcb.name == "fx-A.kicad_pcb" and p.rules.name == "fx-A.kicad_dru"
    assert [l.name for l in p.lock_files] == ["~fx-A.kicad_pcb.lck", "~fx-A.kicad_sch.lck"]


def test_find_boards_applies_exclusions(tmp_path):
    repos = tmp_path / "repos"
    write_project(repos / "fx-A", "fx-A")
    write_project(repos / "fx-B" / "KiCad", "B")                       # depth 3, old layout
    write_project(repos / "fx-C" / "util-Backpack", "util-Backpack")   # sub-project
    write_project(repos / "fx-A" / "fx-A-backups", "fx-A")             # backups
    write_project(repos / "fx-D", "tmpabc")                            # temp copy
    write_project(repos / "Madbean", "pot")                            # library repo
    write_project(repos / "pedalfx" / "template" / "T", "T")           # a template
    write_project(repos / "deep" / "a" / "b", "deep")                  # depth 4
    (repos / "fx-E").mkdir(); (repos / "fx-E" / "fx-E.kicad_pro").write_text("{}")   # no pcb
    names = sorted(p.name for p in discover.find_boards(repos))
    assert names == ["B", "fx-A", "util-Backpack"]
    assert all(p.kind == "board" for p in discover.find_boards(repos))


def test_find_templates_needs_meta_dir(tmp_path):
    root = tmp_path / "template"
    write_project(root / "Good", "good", kind="template")
    write_project(root / "NoMeta", "nometa")
    (root / "_fleet").mkdir(); (root / "_fleet" / "kit").mkdir()
    found = discover.find_templates(root)
    assert [p.name for p in found] == ["good"] and found[0].kind == "template"


def test_find_templates_rejects_two_project_files(tmp_path):
    root = tmp_path / "template"
    p = write_project(root / "Two", "one", kind="template")
    (p.dir / "two.kicad_pro").write_text("{}")
    with pytest.raises(ValueError):
        discover.find_templates(root)


def test_project_from_path_accepts_dir_or_file(tmp_path):
    p = write_project(tmp_path / "fx-A", "fx-A")
    t = write_project(tmp_path / "T", "t", kind="template")
    assert discover.project_from_path(p.dir).pro == p.pro
    assert discover.project_from_path(p.pro).kind == "board"
    assert discover.project_from_path(t.dir).kind == "template"
