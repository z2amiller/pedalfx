from pedalfleet import guard

KICAD = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad"
PCBNEW = "/Applications/KiCad/KiCad.app/Contents/MacOS/pcbnew /Users/x/fx-A.kicad_pcb"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc x.kicad_pcb"
MCP = "/opt/homebrew/bin/uvx kicad-mcp-pro"


def test_kicad_running_detects_app_processes_only():
    assert guard.kicad_running([MCP, "/usr/bin/login"]) is False
    assert guard.kicad_running([MCP, KICAD]) is True
    assert guard.kicad_running([PCBNEW]) is True
    assert guard.kicad_running([CLI]) is False


def test_guard_allows_when_kicad_closed(board):
    result = guard.check_guard(board, commands=[MCP])
    assert result.ok and result.reason == "" and result.stale_locks == []


def test_guard_reports_stale_lock_when_kicad_closed(board):
    lock = board.lock_files[1]
    lock.write_text('{"hostname":"Mac","username":"andrewmiller"}')
    result = guard.check_guard(board, commands=[])
    assert result.ok and result.stale_locks == [lock] and "stale" in result.reason


def test_guard_refuses_when_kicad_running(board):
    result = guard.check_guard(board, commands=[KICAD])
    assert not result.ok and "--force" in result.reason


def test_force_overrides_running_kicad_without_lock(board):
    assert guard.check_guard(board, force=True, commands=[KICAD]).ok


def test_force_never_overrides_a_lock_while_kicad_runs(board):
    board.lock_files[0].write_text("{}")
    result = guard.check_guard(board, force=True, commands=[KICAD])
    assert not result.ok and "lck" in result.reason
