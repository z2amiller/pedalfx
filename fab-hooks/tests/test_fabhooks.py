"""Tests for fabhooks library."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fabhooks
import pre_generate

BOARD_WITH_REV = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(title_block
\t\t(title "Test Board")
\t\t(rev "v0.3")
\t)
\t(gr_text "v9.9"
\t\t(at 1 1)
\t\t(layer "F.SilkS")
\t)
)
"""

BOARD_TEMPLATE_REV = BOARD_WITH_REV.replace('(rev "v0.3")', '(rev "1.0")')
BOARD_NO_TITLE_BLOCK = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(gr_text "v0.7"
\t\t(at 1 1)
\t\t(layer "F.SilkS")
\t)
)
"""

BOARD_TITLE_WITH_PAREN = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(title_block
\t\t(title "Tone Bender :)")
\t\t(rev "v0.3")
\t)
\t(gr_text "v9.9"
\t\t(at 1 1)
\t\t(layer "F.SilkS")
\t)
)
"""

BOARD_SILK_LAYER_FILTER = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(gr_text "v2.0"
\t\t(at 1 1)
\t\t(layer "F.Cu")
\t)
\t(gr_text "v0.7"
\t\t(at 2 2)
\t\t(layer "F.SilkS")
\t)
)
"""

BOARD_NO_REV_ANYWHERE = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(gr_text "hello"
\t\t(at 1 1)
\t\t(layer "F.SilkS")
\t)
)
"""

BOARD_TITLE_BLOCK_NO_REV = """(kicad_pcb (version 20240108) (generator "pcbnew")
\t(title_block
\t\t(title "No Rev Board")
\t)
)
"""


def _write(tmp_path, text):
    p = tmp_path / "board.kicad_pcb"
    p.write_text(text, encoding="utf-8")
    return p


def test_board_rev_from_title_block(tmp_path):
    assert fabhooks.board_rev(_write(tmp_path, BOARD_WITH_REV)) == "v0.3"


def test_board_rev_title_block_wins_over_silk(tmp_path):
    # silk says v9.9 but the title block is authoritative
    assert fabhooks.board_rev(_write(tmp_path, BOARD_WITH_REV)) == "v0.3"


def test_board_rev_template_junk_falls_back_to_silk(tmp_path):
    # "1.0" fails validation, so the silk v-text is used
    assert fabhooks.board_rev(_write(tmp_path, BOARD_TEMPLATE_REV)) == "v9.9"


def test_board_rev_no_title_block_uses_silk(tmp_path):
    assert fabhooks.board_rev(_write(tmp_path, BOARD_NO_TITLE_BLOCK)) == "v0.7"


def test_board_rev_title_with_parens_in_quotes_still_parses(tmp_path):
    # a ")" inside a quoted title string must not truncate the title_block scan
    assert fabhooks.board_rev(_write(tmp_path, BOARD_TITLE_WITH_PAREN)) == "v0.3"


def test_board_rev_silk_ignores_non_silk_layer(tmp_path):
    # v2.0 is on F.Cu (copper) and appears first in the file; it must be
    # skipped in favor of the v0.7 text that is actually on a silk layer
    assert fabhooks.board_rev(_write(tmp_path, BOARD_SILK_LAYER_FILTER)) == "v0.7"


def test_board_rev_none_when_no_rev_anywhere(tmp_path):
    assert fabhooks.board_rev(_write(tmp_path, BOARD_NO_REV_ANYWHERE)) is None


def test_board_rev_none_when_title_block_has_no_rev(tmp_path):
    assert fabhooks.board_rev(_write(tmp_path, BOARD_TITLE_BLOCK_NO_REV)) is None



def test_board_rev_silk_matches_knockout_text(tmp_path):
    # KiCad 7+ emits (layer "F.SilkS" knockout) for knockout text
    board = BOARD_NO_TITLE_BLOCK.replace('(layer "F.SilkS")', '(layer "F.SilkS" knockout)')
    assert fabhooks.board_rev(_write(tmp_path, board)) == "v0.7"


def test_is_valid_rev():
    assert fabhooks.is_valid_rev("v0.1")
    assert fabhooks.is_valid_rev("v12.3")
    assert not fabhooks.is_valid_rev("1.0")
    assert not fabhooks.is_valid_rev("v1")
    assert not fabhooks.is_valid_rev("")
    assert not fabhooks.is_valid_rev(None)
    assert not fabhooks.is_valid_rev("v1.0\n")


def test_tag_and_commit_rendering():
    assert fabhooks.tag_name("fx-BloodySMD", "v0.1", "17") == "fx-BloodySMD-v0.1-g17"
    assert (
        fabhooks.commit_message("fx-BloodySMD", "v0.1", "17")
        == "fx-BloodySMD v0.1 fab outputs (g17)"
    )


def test_fablog_row():
    row = fabhooks.fablog_row("2026-08-02T14:03", "fx-BloodySMD", "v0.1", "17", "a1b2c3d4e5f6")
    assert row == "| 2026-08-02T14:03 | fx-BloodySMD | v0.1 | 17 | a1b2c3d4e5f6 | | |\n"


def test_sha256_file(tmp_path):
    f = tmp_path / "x.zip"
    f.write_bytes(b"hello")
    # sha256("hello") = 2cf24dba5fb0a30e...; first 12 hex chars
    assert fabhooks.sha256_file(f) == "2cf24dba5fb0"


def test_append_fablog_creates_header_then_appends(tmp_path):
    row1 = fabhooks.fablog_row("2026-08-02T14:03", "fx-BloodySMD", "v0.1", "17", "aaaaaaaaaaaa")
    row2 = fabhooks.fablog_row("2026-08-02T15:00", "face-BloodySMD", "v0.2", "18", "bbbbbbbbbbbb")
    fabhooks.append_fablog(tmp_path, row1)
    fabhooks.append_fablog(tmp_path, row2)
    text = (tmp_path / "FABLOG.md").read_text()
    assert text.startswith("# Fab Log\n")
    assert text.count("| Date |") == 1  # header written exactly once
    assert row1 in text and row2 in text
    assert text.index(row1.strip()) < text.index(row2.strip())



HERMETIC_GIT_ENV = {
    **__import__("os").environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, env=HERMETIC_GIT_ENV)


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "-b", "main"], path)
    _git(["config", "user.email", "t@t"], path)
    _git(["config", "user.name", "t"], path)
    (path / "seed.txt").write_text("seed")
    _git(["add", "-A"], path)
    _git(["commit", "-q", "-m", "seed"], path)
    return path


def test_repo_root(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    sub = repo / "sub"
    sub.mkdir()
    assert fabhooks.repo_root(sub) == repo
    assert fabhooks.repo_root(tmp_path) is None


def test_origin_url_and_tag_exists(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    assert fabhooks.origin_url(repo) is None
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
    assert fabhooks.origin_url(repo) == str(bare)
    assert fabhooks.origin_reachable(repo)
    assert not fabhooks.tag_exists(repo, "fx-x-v0.1-g1")
    subprocess.run(["git", "tag", "fx-x-v0.1-g1"], cwd=repo, check=True)
    assert fabhooks.tag_exists(repo, "fx-x-v0.1-g1")


def test_append_fablog_repairs_missing_trailing_newline(tmp_path):
    row1 = fabhooks.fablog_row("2026-08-02T14:03", "fx-a", "v0.1", "1", "aaaaaaaaaaaa")
    row2 = fabhooks.fablog_row("2026-08-02T15:00", "fx-a", "v0.1", "2", "bbbbbbbbbbbb")
    fabhooks.append_fablog(tmp_path, row1)
    log = tmp_path / "FABLOG.md"
    log.write_text(log.read_text().rstrip("\n"))  # simulate editor stripping newline
    fabhooks.append_fablog(tmp_path, row2)
    lines = log.read_text().splitlines()
    assert lines[-1] == row2.strip()
    assert lines[-2] == row1.strip()


def test_origin_reachable_false_for_missing_remote(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    _git(["remote", "add", "origin", str(tmp_path / "gone.git")], repo)
    assert not fabhooks.origin_reachable(repo)


def test_append_fablog_writes_header_into_empty_file(tmp_path):
    (tmp_path / "FABLOG.md").write_text("")
    row = fabhooks.fablog_row("2026-08-02T14:03", "fx-a", "v0.1", "1", "aaaaaaaaaaaa")
    fabhooks.append_fablog(tmp_path, row)
    text = (tmp_path / "FABLOG.md").read_text()
    assert text.startswith("# Fab Log\n")
    assert row in text


def _board_file(path, text=BOARD_WITH_REV):
    p = path / "board.kicad_pcb"
    p.write_text(text, encoding="utf-8")
    return p


def _env(project_dir, board_path):
    return {
        "JLCPCB_HOOK_STAGE": "pre",
        "JLCPCB_PROJECT_DIR": str(project_dir),
        "JLCPCB_BOARD_PATH": str(board_path),
    }


def test_pre_fails_outside_git_repo(tmp_path, capsys):
    board = _board_file(tmp_path)
    assert pre_generate.main(env=_env(tmp_path, board)) == 1
    out = capsys.readouterr().out
    assert "not a git repository" in out


def test_pre_fails_without_origin(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo")
    board = _board_file(repo)
    assert pre_generate.main(env=_env(repo, board)) == 1
    assert "origin" in capsys.readouterr().out


def test_pre_fails_on_bad_rev(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=HERMETIC_GIT_ENV)
    _git(["remote", "add", "origin", str(bare)], repo)
    board = _board_file(repo, BOARD_TEMPLATE_REV.replace('(gr_text "v9.9"', '(gr_text "x"'))
    assert pre_generate.main(env=_env(repo, board)) == 1
    assert "revision" in capsys.readouterr().out


def test_pre_passes_when_all_good(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=HERMETIC_GIT_ENV)
    _git(["remote", "add", "origin", str(bare)], repo)
    board = _board_file(repo)
    assert pre_generate.main(env=_env(repo, board)) == 0
    assert "OK" in capsys.readouterr().out
