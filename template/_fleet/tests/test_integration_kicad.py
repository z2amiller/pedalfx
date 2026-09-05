import shutil
from pathlib import Path

import pytest

from pedalfleet import apply as applymod
from pedalfleet import kicadcli
from pedalfleet.discover import Project
from pedalfleet.paths import KICAD_CLI_DEFAULT

SCHWELL = Path.home() / "Documents" / "repos" / "fx-Schwell"
pytestmark = pytest.mark.skipif(not KICAD_CLI_DEFAULT.exists() or not (SCHWELL / "fx-Schwell.kicad_pcb").exists(),
                                reason="needs kicad-cli and fx-Schwell")


@pytest.fixture
def schwell(tmp_path):
    for name in ("fx-Schwell.kicad_pro", "fx-Schwell.kicad_pcb"):
        shutil.copy2(SCHWELL / name, tmp_path / name)
    return Project((tmp_path / "fx-Schwell.kicad_pro").resolve(), "board")


def drc(project):
    return kicadcli.run_drc(KICAD_CLI_DEFAULT, project.pcb, project.dir / "report.json")


def test_kit_removes_pot_and_jack_noise(schwell, kit):
    before = kicadcli.summarize(drc(schwell))
    assert before.total > 200                                   # 306 at design time
    applymod.apply_project(schwell, kit, applymod.ApplyOptions(commands=[]))
    report = drc(schwell)
    after = kicadcli.summarize(report)
    assert after.total < before.total / 2
    silk = {"silk_edge_clearance", "silk_over_copper", "silk_overlap", "text_height"}
    assert kicadcli.involving(report, silk, r"\b(RV|J)\d+\b") == 0
    assert after.by_type["courtyards_overlap"] == 0
    assert kicadcli.validate_rules(KICAD_CLI_DEFAULT, schwell.pro) == "ok"


def test_component_classes_from_project_file_are_honoured(schwell, kit):
    applymod.apply_project(schwell, kit, applymod.ApplyOptions(commands=[]))
    probe = ('(rule "probe pots" (condition "A.hasComponentClass(\'Pot\') && A.Type == \'Footprint\'")'
             ' (constraint assertion "A.Type != \'Footprint\'"))\n')
    schwell.rules.write_text(schwell.rules.read_text() + probe)
    report = drc(schwell)
    pots = sum(1 for v in report["violations"] if v["type"] == "assertion_failure" and "probe pots" in v["description"])
    assert pots == 5                                              # RV1-RV5 on fx-Schwell


def test_broken_rules_file_is_detected(schwell):
    schwell.rules.write_text("(version 1)\n(rule \"bad\" (condition \"A.NoSuchProperty == 1\") (constraint clearance (min 0.2mm)))\n")
    assert kicadcli.validate_rules(KICAD_CLI_DEFAULT, schwell.pro) == "broken"
