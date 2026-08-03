#!/usr/bin/env python3
"""kicad-jlcpcb-tools pre-generate hook: advisory sanity gate.

Nonzero exit -> the plugin shows Continue/Cancel, so nothing here hard-blocks.
Checks: project is a git repo; origin remote configured (reachability is only a
warning, offline generation is fine); board revision parseable and valid.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabhooks


def main(env=None) -> int:
    env = os.environ if env is None else env
    project_dir = env.get("JLCPCB_PROJECT_DIR")
    board_path = env.get("JLCPCB_BOARD_PATH")
    if not project_dir or not board_path:
        missing = [
            name
            for name, val in [
                ("JLCPCB_PROJECT_DIR", project_dir),
                ("JLCPCB_BOARD_PATH", board_path),
            ]
            if not val
        ]
        print(
            f"FAIL: {', '.join(missing)} not set -- "
            "run via kicad-jlcpcb-tools generation hooks"
        )
        return 1

    failures, warnings = [], []

    root = fabhooks.repo_root(Path(project_dir))
    if root is None:
        failures.append(
            f"{project_dir} is not a git repository -- run your repo-init script first"
        )
    elif fabhooks.origin_url(root) is None:
        failures.append("no 'origin' remote configured -- the post-hook push will fail")
    elif not fabhooks.origin_reachable(root):
        warnings.append("origin unreachable (offline?) -- commit/tag will be local-only")

    rev = None
    try:
        rev = fabhooks.board_rev(Path(board_path))
    except OSError as e:
        failures.append(f"cannot read board file for revision check: {e}")
    else:
        if not fabhooks.is_valid_rev(rev):
            what = "no board revision found" if rev is None else f"board revision {rev!r} is not vN.M"
            failures.append(
                f"{what} -- set it with set_board_rev.py "
                "(or KiCad File > Board Setup) so the fab tag is meaningful"
            )

    for w in warnings:
        print(f"WARN: {w}")
    for f in failures:
        print(f"FAIL: {f}")
    if not failures:
        print(f"pre-generate checks OK (rev {rev})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
