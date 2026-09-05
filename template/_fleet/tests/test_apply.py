from pedalfleet import apply as applymod
from pedalfleet import projectfile

KICAD = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad"


def test_apply_writes_project_rules_and_gitignore_for_a_board(board, kit):
    result = applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    assert result.skipped is None
    assert [p.name for p in result.written] == ["fx-Test.kicad_pro", "fx-Test.kicad_dru", ".gitignore"]
    pro = projectfile.load(board.pro)
    assert pro["board"]["design_settings"]["defaults"]["silk_text_size_h"] == 0.8
    assert projectfile.count_exclusions(pro) == 2                      # not pruned by default
    assert board.rules.read_text() == "(version 1)\n" + kit.rules_block
    assert (board.dir / ".gitignore").read_text() == kit.gitignore


def test_apply_is_idempotent(board, kit):
    applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    before = {p.name: p.read_text() for p in board.dir.iterdir() if p.is_file()}
    second = applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    assert second.written == []
    assert {p.name: p.read_text() for p in board.dir.iterdir() if p.is_file()} == before


def test_apply_keeps_local_rules_and_board_gitignore(board, kit):
    board.rules.write_text("(version 1)\n(rule \"mine\" (constraint clearance (min 0.3mm)))\n")
    (board.dir / ".gitignore").write_text("mine\n")
    applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    text = board.rules.read_text()
    assert text.endswith("(rule \"mine\" (constraint clearance (min 0.3mm)))\n") and kit.rules_block in text
    assert (board.dir / ".gitignore").read_text() == "mine\n"


def test_apply_overwrites_template_gitignore(template, kit):
    (template.dir / ".gitignore").write_text("stale\n")
    applymod.apply_project(template, kit, applymod.ApplyOptions(commands=[]))
    assert (template.dir / ".gitignore").read_text() == kit.gitignore


def test_apply_prunes_exclusions_on_request(board, kit):
    result = applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[], prune_exclusions=True))
    assert "pruned 2 exclusion(s)" in result.notes
    assert projectfile.count_exclusions(projectfile.load(board.pro)) == 0


def test_apply_dry_run_writes_nothing(board, kit):
    original = board.pro.read_text()
    result = applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[], dry_run=True))
    assert [p.name for p in result.written] == ["fx-Test.kicad_pro", "fx-Test.kicad_dru", ".gitignore"]
    assert board.pro.read_text() == original and not board.rules.exists()


def test_apply_skips_when_kicad_running(board, kit):
    result = applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[KICAD]))
    assert result.skipped and result.written == []


def test_apply_leaves_malformed_rules_file_alone(board, kit):
    board.rules.write_text("(version 1)\n(version 1)\n")
    result = applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    assert board.rules.read_text() == "(version 1)\n(version 1)\n"
    assert any("malformed" in n for n in result.notes)
    assert board.pro in result.written                                    # the rest still applied


def test_check_reports_drift_then_clean(board, kit):
    before = applymod.check_project(board, kit, commands=[])
    assert not before.ok()
    assert any(d.startswith("board.design_settings.defaults.silk_text_size_h") for d in before.drift)
    assert "fx-Test.kicad_dru: missing" in before.drift
    assert ".gitignore: missing" in before.drift
    assert before.stale_exclusions == 2 and before.kicad_open is False
    applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    after = applymod.check_project(board, kit, commands=[])
    assert after.ok() and after.drift == []


def test_check_flags_old_block_and_weak_board_gitignore(board, kit):
    applymod.apply_project(board, kit, applymod.ApplyOptions(commands=[]))
    board.rules.write_text(board.rules.read_text().replace("v1 begin", "v0 begin").replace("v1 end", "v0 end"))
    (board.dir / ".gitignore").write_text("only-this\n")
    result = applymod.check_project(board, kit, commands=[])
    assert any("fleet block differs" in d for d in result.drift)
    assert ".gitignore: lacks *-backups" in result.drift and ".gitignore: lacks fp-info-cache" in result.drift


def test_check_flags_malformed_rules_once(board, kit):
    board.rules.write_text("(version 1)\n# --- pedalfx fleet rules v1 begin ---\n")
    result = applymod.check_project(board, kit, commands=[])
    assert [d for d in result.drift if "kicad_dru" in d] == ["fx-Test.kicad_dru: fleet markers incomplete or out of order"]


def test_check_reports_open_in_kicad(board, kit):
    board.lock_files[0].write_text("{}")
    assert applymod.check_project(board, kit, commands=[KICAD]).kicad_open is True
    assert applymod.check_project(board, kit, commands=[]).kicad_open is False
