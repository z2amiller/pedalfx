"""Fixture builders shared by the test modules (kept out of conftest so tests can import them)."""
import json
from pathlib import Path

from pedalfleet.discover import Project

# A trimmed KiCad 10 project file: only the keys the tool touches, plus neighbours it must not disturb.
MINIMAL_PRO = {
    "board": {
        "design_settings": {
            "defaults": {
                "apply_defaults_to_fp_fields": False,
                "apply_defaults_to_fp_shapes": False,
                "apply_defaults_to_fp_text": False,
                "copper_text_size_h": 1.5,
                "fab_text_size_h": 1.0,
                "fab_text_size_v": 1.0,
                "fab_text_thickness": 0.15,
                "silk_line_width": 0.1,
                "silk_text_size_h": 1.0,
                "silk_text_size_v": 1.0,
                "silk_text_thickness": 0.1,
            },
            "drc_exclusions": [
                ["silk_edge_clearance|1|2|a|b", ""],
                ["courtyards_overlap|5|6|e|f", ""],
                ["clearance|3|4|c|d", "keep me"],
            ],
            "rules": {"min_text_height": 0.8, "min_text_thickness": 0.08},
        }
    },
    "component_class_settings": {
        "assignments": [
            {"component_class": "Over4mm", "conditions_operator": "ALL",
             "conditions": {"REFERENCE": {"primary": "C9*"}}}
        ],
        "meta": {"version": 0},
        "sheet_component_classes": {"enabled": False},
    },
    "meta": {"filename": "fx-Test.kicad_pro", "version": 3},
    "net_settings": {"classes": [{"name": "Default", "clearance": 0.2}]},
}

MINIMAL_PCB = "(kicad_pcb\n\t(version 20240108)\n\t(generator \"pedal-fleet-tests\")\n)\n"


def write_project(directory: Path, name: str, pro: dict = None, kind: str = "board") -> Project:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.kicad_pro").write_text(json.dumps(pro if pro is not None else MINIMAL_PRO, indent=2) + "\n")
    (directory / f"{name}.kicad_pcb").write_text(MINIMAL_PCB)
    if kind == "template":
        (directory / "meta").mkdir(exist_ok=True)
        (directory / "meta" / "info.html").write_text("<html><head><title>t</title></head><body>t</body></html>")
    return Project((directory / f"{name}.kicad_pro").resolve(), kind)
