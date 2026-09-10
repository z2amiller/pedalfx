import json
import subprocess

import pytest

from pedalfleet import clone
from tests.helpers import write_project

SCH = """(kicad_sch
\t(uuid "aaaa")
\t(lib_symbols)
\t(symbol
\t\t(instances
\t\t\t(project "fx-Src"
\t\t\t\t(path "/aaaa" (reference "R1") (unit 1))
\t\t\t)
\t\t)
\t)
\t(text "z2a Src board")
)
"""
PCB = """(kicad_pcb
\t(version 20240108)
\t(footprint "R"
\t\t(sheetname "/")
\t\t(sheetfile "fx-Src.kicad_sch")
\t)
\t(gr_text "z2a Src board")
)
"""


def make_source(tmp_path):
    pro = json.loads(json.dumps(__import__("tests.helpers", fromlist=["MINIMAL_PRO"]).MINIMAL_PRO))
    pro["meta"]["filename"] = "fx-Src.kicad_pro"
    pro["text_variables"] = {"BOARD_STATUS": "utility", "BOARD_NOTE": "the source's reason"}
    p = write_project(tmp_path / "fx-Src", "fx-Src", pro=pro)
    (p.dir / "fx-Src.kicad_pcb").write_text(PCB)
    (p.dir / "fx-Src.kicad_sch").write_text(SCH)
    (p.dir / "sub.kicad_sch").write_text(SCH)
    (p.dir / "fx-Src.kicad_dru").write_text("(version 1)\n")
    (p.dir / "fx-Src.kicad_prl").write_text("{}")
    (p.dir / "fp-lib-table").write_text("(fp_lib_table)\n")
    (p.dir / ".gitignore").write_text("*.bak\n")
    (p.dir / "README.md").write_text("# fx-Src\n")
    (p.dir / "~fx-Src.kicad_pcb.lck").write_text("{}")
    (p.dir / "_autosave-fx-Src.kicad_sch").write_text("")
    (p.dir / "fp-info-cache").write_text("")
    (p.dir / "fx-Src-backups").mkdir()
    (p.dir / ".git").mkdir()
    (p.dir / "jlcpcb").mkdir(); (p.dir / "jlcpcb" / "project.db").write_bytes(b"db")
    (p.dir / "jlcpcb" / "gerber").mkdir(); (p.dir / "jlcpcb" / "gerber" / "x.gbr").write_text("")
    return p


def test_clone_copies_renames_and_rewrites_references(tmp_path):
    src = make_source(tmp_path)
    project = clone.clone_project("fx-New", src.dir, dest=tmp_path / "out" / "fx-New")
    d = tmp_path / "out" / "fx-New"
    assert project.kind == "board" and project.pro == (d / "fx-New.kicad_pro").resolve()
    assert sorted(p.name for p in d.iterdir()) == [
        ".gitignore", "README.md", "fp-lib-table", "fx-New.kicad_dru", "fx-New.kicad_pcb", "fx-New.kicad_pro",
        "fx-New.kicad_sch", "jlcpcb", "sub.kicad_sch"]
    assert (d / "jlcpcb" / "project.db").read_bytes() == b"db" and not (d / "jlcpcb" / "gerber").exists()
    pro = json.loads(project.pro.read_text())
    assert pro["meta"]["filename"] == "fx-New.kicad_pro"
    assert pro["text_variables"] == {"BOARD_STATUS": "utility", "BOARD_NOTE": "the source's reason"}
    for sheet in ("fx-New.kicad_sch", "sub.kicad_sch"):
        text = (d / sheet).read_text()
        assert '(project "fx-New"' in text and '(project "fx-Src"' not in text
        assert 'z2a Src board' in text            # free text is the owner's, not rewritten
    pcb = project.pcb.read_text()
    assert '(sheetfile "fx-New.kicad_sch")' in pcb and "fx-Src" not in pcb
    assert (d / "README.md").read_text().startswith("# fx-New\n")


def test_clone_sets_status_and_drops_inherited_note(tmp_path):
    src = make_source(tmp_path)
    project = clone.clone_project("fx-New", src.dir, dest=tmp_path / "fx-New", status="wip")
    assert json.loads(project.pro.read_text())["text_variables"] == {"BOARD_STATUS": "wip"}
    project = clone.clone_project("fx-New2", src.dir, dest=tmp_path / "fx-New2", status="utility", note="why")
    assert json.loads(project.pro.read_text())["text_variables"] == {"BOARD_STATUS": "utility", "BOARD_NOTE": "why"}


def test_clone_reports_leftover_mentions(tmp_path):
    src = make_source(tmp_path)
    (src.dir / "fx-Src.kicad_pcb").write_text(PCB.replace("z2a Src board", "fx-Src rev A"))
    project = clone.clone_project("fx-New", src.dir, dest=tmp_path / "fx-New")
    assert clone.leftover_mentions(project, "fx-Src") == {"fx-New.kicad_pcb": 1}


def test_clone_refuses_existing_dest_and_bad_status(tmp_path):
    src = make_source(tmp_path)
    (tmp_path / "dup").mkdir()
    with pytest.raises(FileExistsError):
        clone.clone_project("dup", src.dir, dest=tmp_path / "dup")
    with pytest.raises(ValueError):
        clone.clone_project("fx-New", src.dir, dest=tmp_path / "fx-New", status="bogus")


def test_init_repo_commits_everything_on_main(tmp_path):
    from pedalfleet import gitutil
    src = make_source(tmp_path)
    project = clone.clone_project("fx-New", src.dir, dest=tmp_path / "fx-New")
    subprocess.run(["git", "config", "--global", "--get", "user.email"], check=False)
    gitutil.init_repo(project.dir, "Initial commit", env_identity=("t", "t@example.com"))
    log = subprocess.run(["git", "-C", str(project.dir), "log", "--oneline", "--all"], capture_output=True, text=True).stdout
    branch = subprocess.run(["git", "-C", str(project.dir), "branch", "--show-current"], capture_output=True, text=True).stdout
    status = subprocess.run(["git", "-C", str(project.dir), "status", "--short"], capture_output=True, text=True).stdout
    assert "Initial commit" in log and branch.strip() == "main" and status.strip() == ""
