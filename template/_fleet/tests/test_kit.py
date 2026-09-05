import json
import pytest
from pedalfleet import kit as kitmod
from pedalfleet.paths import KIT_DIR


def test_real_kit_loads():
    k = kitmod.load_kit(KIT_DIR)
    assert k.version == 1
    assert k.rules_block.startswith("# --- pedalfx fleet rules v1 begin")
    assert k.rules_block.endswith("# --- pedalfx fleet rules v1 end ---\n")
    assert "(version 1)" not in k.rules_block
    assert k.fragment["board"]["design_settings"]["defaults"]["silk_text_size_h"] == 0.8
    classes = {a["component_class"] for a in k.fragment["component_class_settings"]["assignments"]}
    assert classes == {"Pot", "Jack", "Switch", "Tall"}
    assert "*-backups" in k.gitignore and "fp-info-cache" in k.gitignore


def test_kit_without_markers_is_rejected(tmp_path):
    (tmp_path / "fleet.kicad_dru").write_text("(version 1)\n(rule \"x\" (constraint clearance (min 1mm)))\n")
    (tmp_path / "design_settings.json").write_text(json.dumps({}))
    (tmp_path / "gitignore").write_text("")
    with pytest.raises(ValueError):
        kitmod.load_kit(tmp_path)
