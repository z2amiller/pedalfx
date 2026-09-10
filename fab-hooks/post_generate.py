#!/usr/bin/env python3
"""kicad-jlcpcb-tools post-generate hook: FABLOG row, gerber at repo root (public repos), commit, tag, push.

Local-first: the FABLOG append, commit, and tag always land before any network
step, so a failed push never loses state. The FABLOG row also guarantees the
commit is never empty on unchanged re-generates.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabhooks


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print actions, change nothing")
    args = parser.parse_args(argv)

    try:
        board_path = Path(env["JLCPCB_BOARD_PATH"])
        project_dir = Path(env["JLCPCB_PROJECT_DIR"])
        gen = env["JLCPCB_GENERATION_COUNT"]
        zip_path = Path(env["JLCPCB_ARTIFACT_GERBER_ZIP"])
    except KeyError as e:
        print(f"FAIL: missing env var {e} -- run via kicad-jlcpcb-tools generation hooks")
        return 1

    if not gen:
        print("FAIL: JLCPCB_GENERATION_COUNT is empty")
        return 1

    board = board_path.stem
    rev = fabhooks.board_rev(board_path)
    if not fabhooks.is_valid_rev(rev):
        print(f"FAIL: board revision {rev!r} is not [prefix]N.M (e.g. v0.1, 0.3, psu-1.0) -- fix title block rev and re-generate")
        return 1
    root = fabhooks.repo_root(project_dir)
    if root is None:
        print(f"FAIL: {project_dir} is not a git repository -- run your repo-init script")
        return 1
    if not zip_path.exists():
        print(f"FAIL: gerber zip not found: {zip_path}")
        return 1

    sha = fabhooks.sha256_file(zip_path)
    tag = fabhooks.tag_name(board, rev, gen)
    msg = fabhooks.commit_message(board, rev, gen)

    if fabhooks.git(root, "check-ref-format", f"refs/tags/{tag}", check=False).returncode != 0:
        print(f"FAIL: {tag!r} is not a valid git tag name (board filename with "
              "spaces or special characters?) -- rename the board file")
        return 1

    if fabhooks.tag_exists(root, tag):
        print(f"FAIL: tag {tag} already exists -- refusing to overwrite. "
              "(Manual tag? Generation counter reset?)")
        return 2

    now = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M")
    row = fabhooks.fablog_row(now, board, rev, gen, sha)

    # A public repo gets a copy of the zip at its root, so people without KiCad can order
    # the board from the README; it lands in this same commit and tag.
    visibility = fabhooks.repo_visibility(root, env)
    publish = visibility == "public"
    if visibility is None:
        publish_note = "gerber not published at repo root: visibility unknown (gh unavailable or offline)"
    elif not publish:
        publish_note = f"gerber not published at repo root: repo is {visibility}"
    else:
        publish_note = f"published {zip_path.name} at repo root (public repo)"
    pathspec = [str(project_dir), fabhooks.FABLOG_NAME]
    if publish:
        pathspec.append(zip_path.name)

    if args.dry_run:
        print(f"DRY RUN: would append to {root / fabhooks.FABLOG_NAME}: {row.strip()}")
        if publish:
            print(f"DRY RUN: would publish {zip_path.name} at {root}")
        else:
            print(f"DRY RUN: {publish_note}")
        print(f"DRY RUN: would commit {msg!r}, tag {tag}, push origin HEAD + {tag}")
        return 0

    fabhooks.append_fablog(root, row)
    if publish:
        fabhooks.publish_gerber(root, zip_path)
    print(publish_note)
    try:
        fabhooks.git(root, "add", "-A", "--", *pathspec)
        fabhooks.git(root, "commit", "-m", msg, "--", *pathspec)
        fabhooks.git(root, "tag", "-a", tag, "-m", msg)
    except subprocess.CalledProcessError as e:
        detail = ((e.stderr or "") + (e.stdout or "")).strip()
        print(f"FAIL: {' '.join(e.cmd[3:])!r} failed:\n{detail}\n"
              "Nothing was pushed -- fix the issue and re-generate.")
        return 1
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"FAIL: git failed ({e}) -- nothing was pushed; fix the issue and re-generate.")
        return 1
    print(f"committed and tagged {tag} ({sha})")

    try:
        fabhooks.git(root, "push", "--atomic", "origin", "HEAD", f"refs/tags/{tag}", timeout=45)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        detail = (getattr(e, "stderr", "") or "").strip()
        print(f"FAIL: push failed. Commit and tag are safe locally.\n{detail}\n"
              f"If origin has newer commits (e.g. FABLOG edited on GitHub): "
              f"git pull --rebase, then: git push origin HEAD {tag}")
        return 1
    print(f"pushed HEAD and {tag} to origin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
