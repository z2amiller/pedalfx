"""Git helpers: commit exactly the files pedal-fleet wrote; init a cloned project; create its GitHub repo."""
import subprocess
from pathlib import Path


def repo_root(path: Path):
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, check=False)
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def commit_paths(root: Path, paths: list, message: str) -> bool:
    """Stage and commit only `paths` (repo-relative). Returns False when they hold no changes."""
    root = Path(root)
    relative = [str(Path(p).resolve().relative_to(root.resolve())) for p in paths]
    subprocess.run(["git", "-C", str(root), "add", "--", *relative], check=True)
    staged = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet", "--", *relative], check=False)
    if staged.returncode == 0:
        return False
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message, "--", *relative], check=True)
    return True


def init_repo(root: Path, message: str, env_identity=None) -> None:
    """git init on `main`, stage everything (the .gitignore decides what), one commit. Never pushes."""
    root = Path(root)
    identity = []
    if env_identity:
        identity = ["-c", f"user.name={env_identity[0]}", "-c", f"user.email={env_identity[1]}"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", *identity, "-C", str(root), "commit", "-q", "-m", message], check=True)


def create_github_repo(root: Path, name: str, visibility: str) -> str:
    """`gh repo create` from an existing local repo, add `origin`, push main. Returns gh's output."""
    if visibility not in ("public", "private"):
        raise ValueError(f"visibility must be public or private, not {visibility!r}")
    command = ["gh", "repo", "create", name, f"--{visibility}", "--source", str(root), "--remote", "origin", "--push"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh repo create failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    return (result.stdout + result.stderr).strip()
