"""Commit exactly the files pedal-fleet wrote, and nothing else. Never pushes."""
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
