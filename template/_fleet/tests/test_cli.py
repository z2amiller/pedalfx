import subprocess

import pytest

from pedalfleet import cli
from tests.helpers import write_project


def run(argv, capsys):
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, out


def test_check_reports_drift_and_exit_1(tmp_path, capsys):
    p = write_project(tmp_path / "fx-A", "fx-A")
    code, out = run(["check", str(p.dir), "--no-process-check"], capsys)
    assert code == 1 and "fx-A" in out and "DRIFT" in out and "silk_text_size_h" in out


def test_apply_then_check_clean(tmp_path, capsys):
    p = write_project(tmp_path / "fx-A", "fx-A")
    code, out = run(["apply", str(p.dir), "--no-process-check"], capsys)
    assert code == 0 and "applied" in out and "fx-A.kicad_dru: created" in out
    code, out = run(["check", str(p.dir), "--no-process-check"], capsys)
    assert code == 0 and "ok" in out


def test_apply_dry_run_shows_diff_and_writes_nothing(tmp_path, capsys):
    p = write_project(tmp_path / "fx-A", "fx-A")
    code, out = run(["apply", str(p.dir), "--dry-run", "--no-process-check"], capsys)
    assert code == 0 and "would write" in out and '+        "silk_text_size_h": 0.8' in out
    assert "fleet rules v1 begin" in out
    assert not p.rules.exists()


def test_targets_from_flags(tmp_path, capsys):
    repos = tmp_path / "repos"; templates = tmp_path / "template"
    write_project(repos / "fx-A", "fx-A")
    write_project(templates / "T", "t", kind="template")
    code, out = run(["check", "--all", "--repos", str(repos), "--templates-root", str(templates), "--no-process-check"], capsys)
    assert "fx-A" in out and "t " in out and out.strip().endswith("2 projects, 0 in sync, 2 drifted")


def test_no_targets_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.main(["check"])
    assert exc.value.code == 2


def test_apply_commit_makes_one_commit_per_repo(tmp_path, capsys):
    repo = tmp_path / "fx-A"
    write_project(repo, "fx-A")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    code, out = run(["apply", str(repo), "--commit", "--no-process-check"], capsys)
    assert code == 0 and "committed" in out
    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True).stdout
    assert "pedal-fleet: apply fleet kit v1" in log


def test_new_template_verb(tmp_path, capsys):
    src = write_project(tmp_path / "fx-Src", "fx-Src")
    root = tmp_path / "template"
    code, out = run(["new-template", "Neat", "--from", str(src.dir), "--title", "Neat", "--description", "d",
                     "--templates-root", str(root), "--no-process-check"], capsys)
    assert code == 0 and "kit v1 applied" in out
    assert (root / "Neat" / "fx-Src.kicad_dru").exists() and (root / "Neat" / ".gitignore").exists()
