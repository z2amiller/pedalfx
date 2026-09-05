import subprocess

from pedalfleet import gitutil


def make_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / "README.md").write_text("x\n")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)
    return path


def test_repo_root_none_outside_git(tmp_path):
    assert gitutil.repo_root(tmp_path) is None


def test_commit_paths_commits_only_the_given_files(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "a.kicad_dru").write_text("(version 1)\n")
    (repo / "README.md").write_text("changed but not ours\n")
    assert gitutil.repo_root(repo) == repo.resolve()
    assert gitutil.commit_paths(repo, [repo / "a.kicad_dru"], "pedal-fleet: test") is True
    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True).stdout
    assert "pedal-fleet: test" in log
    status = subprocess.run(["git", "-C", str(repo), "status", "--short"], capture_output=True, text=True).stdout
    assert status.strip() == "M README.md"


def test_commit_paths_returns_false_when_nothing_changed(tmp_path):
    repo = make_repo(tmp_path / "r")
    assert gitutil.commit_paths(repo, [repo / "README.md"], "nothing") is False
