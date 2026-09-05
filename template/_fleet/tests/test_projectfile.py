import copy
import json
import os

import pytest

from pedalfleet import projectfile
from tests.helpers import MINIMAL_PRO


def test_dumps_is_byte_stable_for_a_real_project_file():
    real = "/Users/andrewmiller/Documents/repos/fx-Schwell/fx-Schwell.kicad_pro"
    if not os.path.exists(real):
        pytest.skip("fx-Schwell not present")
    raw = open(real, encoding="utf-8").read()
    assert projectfile.dumps(json.loads(raw)) == raw


def test_merge_sets_defaults_and_creates_classes(kit):
    pro = copy.deepcopy(MINIMAL_PRO)
    changed = projectfile.merge_fragment(pro, kit.fragment)
    assert changed
    d = pro["board"]["design_settings"]["defaults"]
    assert d["silk_text_size_h"] == 0.8 and d["silk_text_thickness"] == 0.15 and d["silk_line_width"] == 0.15
    assert d["apply_defaults_to_fp_fields"] is True and d["apply_defaults_to_fp_text"] is False
    assert d["copper_text_size_h"] == 1.5                       # untouched neighbour
    assert pro["net_settings"]["classes"][0]["clearance"] == 0.2  # untouched sibling
    names = [a["component_class"] for a in pro["component_class_settings"]["assignments"]]
    assert names[0] == "Over4mm"                               # board-added class kept, first
    assert set(names) == {"Over4mm", "Pot", "Jack", "Switch", "Tall"}


def test_merge_is_idempotent(kit):
    pro = copy.deepcopy(MINIMAL_PRO)
    projectfile.merge_fragment(pro, kit.fragment)
    snapshot = copy.deepcopy(pro)
    assert projectfile.merge_fragment(pro, kit.fragment) is False
    assert pro == snapshot


def test_merge_creates_missing_component_class_settings(kit):
    pro = copy.deepcopy(MINIMAL_PRO)
    del pro["component_class_settings"]
    projectfile.merge_fragment(pro, kit.fragment)
    ccs = pro["component_class_settings"]
    assert ccs["meta"] == {"version": 0}
    assert ccs["sheet_component_classes"] == {"enabled": False}
    assert len(ccs["assignments"]) == len(kit.fragment["component_class_settings"]["assignments"])


def test_merge_updates_a_kit_assignment_that_drifted(kit):
    pro = copy.deepcopy(MINIMAL_PRO)
    pro["component_class_settings"]["assignments"].append(
        {"component_class": "Pot", "conditions_operator": "ANY", "conditions": {"REFERENCE": {"primary": "RV*"}}})
    projectfile.merge_fragment(pro, kit.fragment)
    pots = [a for a in pro["component_class_settings"]["assignments"] if a["component_class"] == "Pot"]
    assert pots == [{"component_class": "Pot", "conditions_operator": "ALL", "conditions": {"REFERENCE": {"primary": "RV*"}}}]


def test_drift_lists_every_difference(kit):
    pro = copy.deepcopy(MINIMAL_PRO)
    problems = projectfile.drift(pro, kit.fragment)
    assert any(p.startswith("board.design_settings.defaults.silk_text_size_h: 1.0") for p in problems)
    assert any("component class Pot" in p for p in problems)
    projectfile.merge_fragment(pro, kit.fragment)
    assert projectfile.drift(pro, kit.fragment) == []


def test_drift_reports_missing_component_class_settings(kit):
    pro = copy.deepcopy(MINIMAL_PRO)
    del pro["component_class_settings"]
    problems = projectfile.drift(pro, kit.fragment)
    assert "component_class_settings: missing" in problems


def test_prune_and_count_exclusions():
    pro = copy.deepcopy(MINIMAL_PRO)
    assert projectfile.count_exclusions(pro) == 2
    assert projectfile.prune_exclusions(pro) == 2
    assert pro["board"]["design_settings"]["drc_exclusions"] == [["clearance|3|4|c|d", "keep me"]]
    assert projectfile.count_exclusions(pro) == 0
    assert projectfile.prune_exclusions(pro) == 0


def test_exclusions_as_plain_strings_are_handled():
    pro = copy.deepcopy(MINIMAL_PRO)
    pro["board"]["design_settings"]["drc_exclusions"] = ["silk_overlap|1|2|a|b", "clearance|1|2|a|b"]
    assert projectfile.count_exclusions(pro) == 1
    assert projectfile.prune_exclusions(pro) == 1
