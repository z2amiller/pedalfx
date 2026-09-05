import json

import pytest

from pedalfleet import newtemplate
from tests.helpers import write_project


def make_source(tmp_path):
    p = write_project(tmp_path / "fx-Src", "fx-Src")
    (p.dir / "fx-Src.kicad_sch").write_text("(kicad_sch)\n")
    (p.dir / "board_setup.kicad_sch").write_text("(kicad_sch)\n")
    (p.dir / "fx-Src.kicad_prl").write_text("{}")
    (p.dir / "fx-Src.kicad_sch_old").write_text("old")
    (p.dir / "~fx-Src.kicad_pcb.lck").write_text("{}")
    (p.dir / "fp-info-cache").write_text("")
    (p.dir / "fx-Src-backups").mkdir()
    (p.dir / "jlcpcb").mkdir(); (p.dir / "jlcpcb" / "project.db").write_bytes(b"db")
    (p.dir / "jlcpcb" / "gerber").mkdir(); (p.dir / "jlcpcb" / "gerber" / "x.gbr").write_text("")
    return p


def test_create_template_copies_renames_and_writes_meta(tmp_path):
    src = make_source(tmp_path)
    root = tmp_path / "template"
    project = newtemplate.create_template("Fancy125B", src.dir, "Fancy 125B", "A <fancy> board",
                                          project_name="fx-Fancy125B", templates_root=root)
    d = root / "Fancy125B"
    assert project.kind == "template" and project.pro == (d / "fx-Fancy125B.kicad_pro").resolve()
    assert sorted(p.name for p in d.iterdir()) == [
        "board_setup.kicad_sch", "fx-Fancy125B.kicad_pcb", "fx-Fancy125B.kicad_pro", "fx-Fancy125B.kicad_sch",
        "jlcpcb", "meta"]
    assert (d / "jlcpcb" / "project.db").read_bytes() == b"db" and not (d / "jlcpcb" / "gerber").exists()
    info = (d / "meta" / "info.html").read_text()
    assert "<title>Fancy 125B</title>" in info and "A &lt;fancy&gt; board" in info
    assert json.loads(project.pro.read_text())["meta"]["filename"] == "fx-Fancy125B.kicad_pro"


def test_create_template_defaults_project_name_to_source(tmp_path):
    src = make_source(tmp_path)
    project = newtemplate.create_template("Plain", src.dir, "Plain", "plain", templates_root=tmp_path / "t")
    assert project.name == "fx-Src"


def test_create_template_refuses_existing_dir(tmp_path):
    src = make_source(tmp_path)
    (tmp_path / "t" / "Dup").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        newtemplate.create_template("Dup", src.dir, "d", "d", templates_root=tmp_path / "t")
