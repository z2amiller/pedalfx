"""Tests for fabhooks library."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fabhooks
import pre_generate
import post_generate
import set_board_rev

import pytest


@pytest.fixture(autouse=True)
def _hermetic_git_env(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")

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

BOARD_UNSET_REV = BOARD_WITH_REV.replace('(rev "v0.3")', '(rev "")')
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


def test_board_rev_unset_falls_back_to_silk(tmp_path):
    # an empty rev fails validation, so the silk rev-text is used
    assert fabhooks.board_rev(_write(tmp_path, BOARD_UNSET_REV)) == "v9.9"


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
    # optional alpha prefix (letters/dashes, starts with a letter) + N.M
    assert fabhooks.is_valid_rev("v0.1")
    assert fabhooks.is_valid_rev("v12.3")
    assert fabhooks.is_valid_rev("1.0")
    assert fabhooks.is_valid_rev("0.3")
    assert fabhooks.is_valid_rev("psu1.0")
    assert fabhooks.is_valid_rev("util-1.2")
    assert fabhooks.is_valid_rev("power-supply-2.0")
    assert not fabhooks.is_valid_rev("v1")
    assert not fabhooks.is_valid_rev("1")
    assert not fabhooks.is_valid_rev("1.0.1")
    assert not fabhooks.is_valid_rev("-1.0")
    assert not fabhooks.is_valid_rev("SET-ME")
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
    assert "no 'origin' remote" in capsys.readouterr().out


def test_pre_fails_on_bad_rev(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=HERMETIC_GIT_ENV)
    _git(["remote", "add", "origin", str(bare)], repo)
    board = _board_file(repo, BOARD_UNSET_REV.replace('(gr_text "v9.9"', '(gr_text "x"'))
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


def test_pre_warns_but_passes_when_origin_unreachable(tmp_path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _git(["remote", "add", "origin", str(tmp_path / "gone.git")], repo)
    board = _board_file(repo)
    assert pre_generate.main(env=_env(repo, board)) == 0
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "FAIL" not in out


def _full_setup(tmp_path):
    """Repo with origin + board file + fake gerber zip; returns (repo, bare, env)."""
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=HERMETIC_GIT_ENV)
    _git(["remote", "add", "origin", str(bare)], repo)
    board = repo / "fx-Test.kicad_pcb"
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    outdir = repo / "jlcpcb" / "production_files"
    outdir.mkdir(parents=True)
    zipf = outdir / "GERBER-fx-Test.zip"
    zipf.write_bytes(b"fake gerbers")
    env = {
        "JLCPCB_HOOK_STAGE": "post",
        "JLCPCB_PROJECT_DIR": str(repo),
        "JLCPCB_BOARD_PATH": str(board),
        "JLCPCB_GENERATION_COUNT": "7",
        "JLCPCB_ARTIFACT_GERBER_ZIP": str(zipf),
    }
    return repo, bare, env


def test_post_dry_run_mutates_nothing(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    assert post_generate.main(argv=["--dry-run"], env=env) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert not (repo / "FABLOG.md").exists()
    assert not fabhooks.tag_exists(repo, "fx-Test-v0.3-g7")


def test_post_full_run_commits_tags_pushes(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    assert post_generate.main(argv=[], env=env) == 0
    log = (repo / "FABLOG.md").read_text()
    assert "| fx-Test | v0.3 | 7 |" in log
    assert fabhooks.tag_exists(repo, "fx-Test-v0.3-g7")
    msg = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert msg == "fx-Test v0.3 fab outputs (g7)"
    remote_tags = subprocess.run(
        ["git", "tag"], cwd=bare, capture_output=True, text=True
    ).stdout
    assert "fx-Test-v0.3-g7" in remote_tags


def test_post_refuses_existing_tag(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    _git(["tag", "fx-Test-v0.3-g7"], repo)
    assert post_generate.main(argv=[], env=env) == 2
    assert "already exists" in capsys.readouterr().out


def test_post_push_failure_keeps_local_state(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    _git(["remote", "set-url", "origin", str(tmp_path / "missing.git")], repo)
    assert post_generate.main(argv=[], env=env) == 1
    out = capsys.readouterr().out
    assert "push failed" in out
    assert fabhooks.tag_exists(repo, "fx-Test-v0.3-g7")  # local state preserved


def test_post_rejects_invalid_tag_name(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    board = repo / "fx Bad Name.kicad_pcb"  # spaces -> illegal git ref
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    env["JLCPCB_BOARD_PATH"] = str(board)
    assert post_generate.main(argv=[], env=env) == 1
    out = capsys.readouterr().out
    assert "not a valid git" in out
    assert not (repo / "FABLOG.md").exists()  # rejected before any mutation


def test_post_commit_failure_prints_hook_stderr(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'lint failed' >&2\nexit 1\n")
    hook.chmod(0o755)
    assert post_generate.main(argv=[], env=env) == 1
    out = capsys.readouterr().out
    assert "lint failed" in out
    assert "FAIL" in out


def test_post_commit_leaves_unrelated_staged_work_alone(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=HERMETIC_GIT_ENV)
    _git(["remote", "add", "origin", str(bare)], repo)
    proj = repo / "pedal"
    proj.mkdir()
    board = proj / "fx-Sub.kicad_pcb"
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    zipf = proj / "GERBER-fx-Sub.zip"
    zipf.write_bytes(b"zzz")
    unrelated = repo / "notes.md"
    unrelated.write_text("wip")
    _git(["add", "notes.md"], repo)
    env = {
        "JLCPCB_PROJECT_DIR": str(proj),
        "JLCPCB_BOARD_PATH": str(board),
        "JLCPCB_GENERATION_COUNT": "3",
        "JLCPCB_ARTIFACT_GERBER_ZIP": str(zipf),
    }
    assert post_generate.main(argv=[], env=env) == 0
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "notes.md" not in committed
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "notes.md" in staged  # still staged, not swept into the fab commit


def test_post_fails_on_empty_generation_count(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    env["JLCPCB_GENERATION_COUNT"] = ""
    assert post_generate.main(argv=[], env=env) == 1
    assert "JLCPCB_GENERATION_COUNT" in capsys.readouterr().out


def test_set_rev_replaces_existing(tmp_path):
    board = tmp_path / "b.kicad_pcb"
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    old = set_board_rev.set_rev(board, "v0.1")
    assert old == "v0.3"
    assert fabhooks.title_block_rev(board.read_text()) == "v0.1"


def test_set_rev_inserts_when_missing(tmp_path):
    board = tmp_path / "b.kicad_pcb"
    board.write_text(BOARD_WITH_REV.replace('\t\t(rev "v0.3")\n', ""), encoding="utf-8")
    old = set_board_rev.set_rev(board, "v0.2")
    assert old == ""
    assert fabhooks.title_block_rev(board.read_text()) == "v0.2"


def test_set_rev_aborts_on_kicad_lock(tmp_path):
    board = tmp_path / "b.kicad_pcb"
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    (tmp_path / "~b.kicad_pcb.lck").write_text("")
    try:
        set_board_rev.set_rev(board, "v0.1")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "close KiCad" in str(e)


def test_set_rev_rejects_invalid_version(tmp_path):
    board = tmp_path / "b.kicad_pcb"
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    try:
        set_board_rev.set_rev(board, "v1")  # no minor component -> invalid
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_rev_handles_noncanonical_spacing(tmp_path):
    # (rev  "v0.3") with two spaces must be replaced, not duplicated
    board = tmp_path / "b.kicad_pcb"
    board.write_text(BOARD_WITH_REV.replace('(rev "v0.3")', '(rev  "v0.3")'), encoding="utf-8")
    old = set_board_rev.set_rev(board, "v0.5")
    assert old == "v0.3"
    text = board.read_text()
    assert text.count("(rev") == 1
    assert fabhooks.title_block_rev(text) == "v0.5"


def test_set_rev_cli_reports_missing_file(tmp_path, capsys):
    assert set_board_rev.main([str(tmp_path / "nope.kicad_pcb"), "v0.1"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_board_rev_accepts_bare_numeric_title_block(tmp_path):
    board = _write(tmp_path, BOARD_WITH_REV.replace('(rev "v0.3")', '(rev "1.0")'))
    assert fabhooks.board_rev(board) == "1.0"


def test_silk_fallback_accepts_prefixed_rev(tmp_path):
    board = _write(tmp_path, BOARD_NO_TITLE_BLOCK.replace('"v0.7"', '"psu0.7"'))
    assert fabhooks.board_rev(board) == "psu0.7"


# --- gerber publishing to the repo root (public repos only) ---

def test_repo_visibility_env_override_skips_gh(tmp_path):
    assert fabhooks.repo_visibility(tmp_path, env={"FABHOOKS_REPO_VISIBILITY": "Public"}) == "public"
    assert fabhooks.repo_visibility(tmp_path, env={"FABHOOKS_REPO_VISIBILITY": "private"}) == "private"


def test_repo_visibility_none_when_gh_unavailable(tmp_path):
    assert fabhooks.repo_visibility(tmp_path, env={"FABHOOKS_GH": str(tmp_path / "no-gh")}) is None


def test_post_publishes_gerber_at_root_in_public_repo(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    env["FABHOOKS_REPO_VISIBILITY"] = "public"
    assert post_generate.main(argv=[], env=env) == 0
    out = capsys.readouterr().out
    assert "published GERBER-fx-Test.zip" in out
    assert (repo / "GERBER-fx-Test.zip").read_bytes() == b"fake gerbers"
    tagged = subprocess.run(["git", "show", "--stat", "--format=", "fx-Test-v0.3-g7"],
                            cwd=repo, capture_output=True, text=True).stdout
    assert "GERBER-fx-Test.zip" in tagged
    status = subprocess.run(["git", "status", "--short"], cwd=repo, capture_output=True, text=True).stdout
    assert status.strip() == ""


def test_post_publishes_from_project_subdir_to_repo_root(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    sub = repo / "KiCad"
    sub.mkdir()
    board = sub / "fx-Test.kicad_pcb"
    board.write_text(BOARD_WITH_REV, encoding="utf-8")
    env.update({"JLCPCB_PROJECT_DIR": str(sub), "JLCPCB_BOARD_PATH": str(board),
                "FABHOOKS_REPO_VISIBILITY": "public"})
    assert post_generate.main(argv=[], env=env) == 0
    assert (repo / "GERBER-fx-Test.zip").exists() and not (sub / "GERBER-fx-Test.zip").exists()
    tagged = subprocess.run(["git", "show", "--stat", "--format=", "fx-Test-v0.3-g7"],
                            cwd=repo, capture_output=True, text=True).stdout
    assert "GERBER-fx-Test.zip" in tagged


def test_post_skips_gerber_in_private_repo(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    env["FABHOOKS_REPO_VISIBILITY"] = "private"
    assert post_generate.main(argv=[], env=env) == 0
    assert "not published" in capsys.readouterr().out
    assert not (repo / "GERBER-fx-Test.zip").exists()


def test_post_skips_gerber_when_visibility_unknown(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    env["FABHOOKS_GH"] = str(tmp_path / "no-gh")
    assert post_generate.main(argv=[], env=env) == 0
    assert "visibility unknown" in capsys.readouterr().out
    assert not (repo / "GERBER-fx-Test.zip").exists()


def test_post_dry_run_reports_publish_without_copying(tmp_path, capsys):
    repo, bare, env = _full_setup(tmp_path)
    env["FABHOOKS_REPO_VISIBILITY"] = "public"
    assert post_generate.main(argv=["--dry-run"], env=env) == 0
    assert "would publish GERBER-fx-Test.zip" in capsys.readouterr().out
    assert not (repo / "GERBER-fx-Test.zip").exists()
