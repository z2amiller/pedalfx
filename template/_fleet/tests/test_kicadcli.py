import json
from pathlib import Path

import pytest

from pedalfleet import kicadcli

FIXTURE = Path(__file__).parent / "fixtures" / "drc_sample.json"


def test_summarize_counts_types_severities_prefixes_and_excluded():
    report = json.loads(FIXTURE.read_text())
    s = kicadcli.summarize(report)
    assert s.total == 3 and s.excluded == 1 and s.errors == 2
    assert s.by_type["silk_edge_clearance"] == 1 and s.by_type["courtyards_overlap"] == 1
    assert s.severities["courtyards_overlap"] == "error"
    assert s.prefixes["silk_edge_clearance"]["RV*"] == 1
    assert s.prefixes["courtyards_overlap"]["J*"] == 2


def test_involving_counts_non_excluded_violations_touching_refdes_pattern():
    report = json.loads(FIXTURE.read_text())
    assert kicadcli.involving(report, {"silk_edge_clearance"}, r"\b(RV|J)\d+\b") == 1
    assert kicadcli.involving(report, {"courtyards_overlap"}, r"\bJ10[24]\b") == 1


def test_probe_fired_counts_probe_assertions():
    report = json.loads(FIXTURE.read_text())
    assert kicadcli.probe_fired(report) == 1


def test_delta_lists_union_of_types():
    a = kicadcli.DrcSummary(); a.by_type.update({"x": 3, "y": 1})
    b = kicadcli.DrcSummary(); b.by_type.update({"y": 1, "z": 2})
    assert kicadcli.delta(a, b) == [("x", 3, 0), ("y", 1, 1), ("z", 0, 2)]


def test_find_kicad_cli_prefers_explicit_then_env(tmp_path, monkeypatch):
    fake = tmp_path / "kicad-cli"; fake.write_text("")
    assert kicadcli.find_kicad_cli(str(fake)) == fake
    monkeypatch.setenv("KICAD_CLI", str(fake))
    assert kicadcli.find_kicad_cli(None) == fake


def test_find_kicad_cli_raises_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("KICAD_CLI", raising=False)
    monkeypatch.setattr(kicadcli, "KICAD_CLI_DEFAULT", tmp_path / "missing")
    monkeypatch.setattr(kicadcli.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        kicadcli.find_kicad_cli(None)


def test_count_footprints_in_board_text():
    text = "(kicad_pcb\n\t(footprint \"R_0603\"\n\t)\n\t(footprint \"C_0603\"\n\t)\n)\n"
    assert kicadcli.count_footprints(text) == 2
