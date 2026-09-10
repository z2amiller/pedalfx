"""pedal-fleet command line: check | apply | drc | new-template | clone."""
import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import apply as applymod
from . import clone as clonemod
from . import gitutil, kicadcli, projectfile, rules
from .discover import find_boards, find_templates, project_from_path
from .kit import load_kit
from .newtemplate import create_template
from .paths import DEFAULT_REPOS, KIT_DIR, TEMPLATES_ROOT

COMMIT_MESSAGE = "pedal-fleet: apply fleet kit v{version}"


def _add_target_args(parser):
    parser.add_argument("targets", nargs="*", help="project directories or .kicad_pro files")
    parser.add_argument("--templates", action="store_true", help="every template under the templates root")
    parser.add_argument("--boards", action="store_true", help="every board under the repos root")
    parser.add_argument("--all", action="store_true", help="--templates and --boards")
    parser.add_argument("--repos", type=Path, default=DEFAULT_REPOS)
    parser.add_argument("--templates-root", type=Path, default=TEMPLATES_ROOT)
    parser.add_argument("--kit", type=Path, default=KIT_DIR)
    parser.add_argument("--kicad-cli", default=None)
    parser.add_argument("--no-process-check", action="store_true",
                        help="do not look for running KiCad processes (tests)")


def build_parser():
    parser = argparse.ArgumentParser(prog="pedal-fleet",
                                     description="keep KiCad templates and boards on the fleet kit")
    sub = parser.add_subparsers(dest="verb", required=True)

    check = sub.add_parser("check", help="report drift from the kit (read-only; exit 1 on drift)")
    _add_target_args(check)

    apply_ = sub.add_parser("apply", help="stamp the kit into projects")
    _add_target_args(apply_)
    apply_.add_argument("--dry-run", action="store_true")
    apply_.add_argument("--force", action="store_true", help="proceed while KiCad runs (never with a lock file)")
    apply_.add_argument("--prune-exclusions", action="store_true")
    apply_.add_argument("--commit", action="store_true", help="commit the written files, one commit per repo")
    apply_.add_argument("--validate", action="store_true", help="run a kicad-cli probe to prove the rules parse")

    drc = sub.add_parser("drc", help="run kicad-cli DRC and summarise by type")
    _add_target_args(drc)
    drc.add_argument("--baseline", type=Path, help="summary JSON from an earlier --save, printed as before/after")
    drc.add_argument("--save", type=Path, help="write per-project counts as JSON")
    drc.add_argument("--fail-on", choices=["error", "warning"], help="exit 1 if any such violation remains")
    drc.add_argument("--validate-rules", action="store_true")

    new = sub.add_parser("new-template", help="scaffold a template from a project and apply the kit")
    new.add_argument("name")
    new.add_argument("--from", dest="source", required=True, type=Path)
    new.add_argument("--project-name", default=None)
    new.add_argument("--title", required=True)
    new.add_argument("--description", required=True)
    new.add_argument("--templates-root", type=Path, default=TEMPLATES_ROOT)
    new.add_argument("--kit", type=Path, default=KIT_DIR)
    new.add_argument("--no-process-check", action="store_true")

    cl = sub.add_parser("clone", help="copy a board into a new project (renamed, kit applied, git initialised)")
    cl.add_argument("name", help="new project name, e.g. util-BleedAFuzz")
    cl.add_argument("--from", dest="source", required=True, type=Path, help="source project dir or .kicad_pro")
    cl.add_argument("--dest", type=Path, default=None, help="destination dir (default: <repos>/<name>)")
    cl.add_argument("--repos", type=Path, default=DEFAULT_REPOS)
    cl.add_argument("--status", choices=clonemod.STATUSES, default=None, help="BOARD_STATUS for the clone")
    cl.add_argument("--note", default=None, help="BOARD_NOTE for the clone")
    cl.add_argument("--github", choices=("public", "private"), default=None,
                    help="also create the GitHub repo and push main")
    cl.add_argument("--no-git", action="store_true", help="skip git init / initial commit")
    cl.add_argument("--kit", type=Path, default=KIT_DIR)
    cl.add_argument("--kicad-cli", type=Path, default=None)
    cl.add_argument("--no-verify", action="store_true", help="skip the kicad-cli netlist export that checks the rename")
    cl.add_argument("--force", action="store_true")
    cl.add_argument("--no-process-check", action="store_true")
    return parser


def resolve_targets(args, parser):
    projects = []
    if args.all or args.templates:
        projects += find_templates(args.templates_root)
    if args.all or args.boards:
        projects += find_boards(args.repos)
    for target in args.targets:
        projects.append(project_from_path(target))
    unique, seen = [], set()
    for project in projects:
        if project.pro not in seen:
            seen.add(project.pro)
            unique.append(project)
    if not unique:
        parser.error("no targets: give project paths or --templates / --boards / --all")
    return unique


def _commands(args):
    return [] if args.no_process_check else None


def cmd_check(args, parser):
    kit = load_kit(args.kit)
    drifted = 0
    projects = resolve_targets(args, parser)
    for project in projects:
        result = applymod.check_project(project, kit, commands=_commands(args))
        flags = []
        if result.kicad_open:
            flags.append("open in KiCad")
        if result.stale_exclusions:
            flags.append(f"{result.stale_exclusions} exclusion(s) the kit now covers")
        status = "ok" if result.ok() else "DRIFT: " + "; ".join(result.drift)
        drifted += 0 if result.ok() else 1
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"{project.name:36s} {project.kind:9s} {status}{suffix}")
    print(f"{len(projects)} projects, {len(projects) - drifted} in sync, {drifted} drifted")
    return 1 if drifted else 0


def _diff(old: str, new: str, name: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{name}", f"b/{name}"))


def _managed_paths(project):
    return [p for p in (project.pro, project.rules, project.dir / ".gitignore") if p.exists()]


def _apply_one(project, kit, options, args, kicad_cli, by_repo) -> int:
    """Apply the kit to one project and print the outcome. Returns 1 on a failure worth the exit code."""
    before = {}
    if args.dry_run:
        for path in (project.pro, project.rules, project.dir / ".gitignore"):
            before[path] = path.read_text(encoding="utf-8") if path.exists() else ""
    result = applymod.apply_project(project, kit, options)
    if result.skipped:
        print(f"skipped: {project.name} ({result.skipped})")
        return 1
    if not result.written:
        print(f"unchanged: {project.name}")
    else:
        verb = "would write" if args.dry_run else "applied"
        print(f"{verb}: {project.name} ({', '.join(p.name for p in result.written)})")
    for note in result.notes:
        print(f"    {note}")
    if args.dry_run:
        if result.written:
            pro = projectfile.load(project.pro)
            projectfile.merge_fragment(pro, kit.fragment)
            if args.prune_exclusions:
                projectfile.prune_exclusions(pro)
            print(_diff(before[project.pro], projectfile.dumps(pro), project.pro.name))
            new_rules, status = rules.splice(before[project.rules] or None, kit.rules_block)
            if status not in (rules.UNCHANGED, rules.MALFORMED):
                print(_diff(before[project.rules], new_rules, project.rules.name))
        return 0
    failure = 0
    if kicad_cli is not None and result.written and project.pcb.exists():
        verdict = kicadcli.validate_rules(kicad_cli, project.pro)
        print(f"    rules: {verdict}")
        if verdict == "broken":
            failure = 1
    if args.commit:
        root = gitutil.repo_root(project.dir)
        if root is None:
            print("    not a git repository; nothing committed")
        else:
            # Managed files are staged whether or not this run wrote them, so an interrupted
            # earlier run (applied, not committed) is picked up by the next --commit.
            by_repo.setdefault(root, []).extend(_managed_paths(project))
    return failure


def cmd_apply(args, parser):
    kit = load_kit(args.kit)
    options = applymod.ApplyOptions(dry_run=args.dry_run, force=args.force,
                                    prune_exclusions=args.prune_exclusions, commands=_commands(args))
    kicad_cli = kicadcli.find_kicad_cli(args.kicad_cli) if args.validate else None
    failures = 0
    by_repo = {}
    for project in resolve_targets(args, parser):
        try:
            failures += _apply_one(project, kit, options, args, kicad_cli, by_repo)
        except (OSError, ValueError, RuntimeError) as error:
            print(f"error: {project.name}: {error}")
            failures += 1
    for root, paths in by_repo.items():
        if gitutil.commit_paths(root, paths, COMMIT_MESSAGE.format(version=kit.version)):
            print(f"committed in {root}: {len(paths)} file(s)")
    return 1 if failures else 0


def cmd_drc(args, parser):
    kicad_cli = kicadcli.find_kicad_cli(args.kicad_cli)
    baseline = json.loads(args.baseline.read_text()) if args.baseline else {}
    saved = {}
    failed = 0
    for project in resolve_targets(args, parser):
        if not project.pcb.exists():
            print(f"{project.name}: no board file, skipped")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            report = kicadcli.run_drc(kicad_cli, project.pcb, Path(tmp) / "drc.json")
        summary = kicadcli.summarize(report)
        saved[project.name] = dict(summary.by_type)
        print(f"== {project.name}: {summary.total} violation(s) ({summary.errors} error(s)), {summary.excluded} excluded")
        old = baseline.get(project.name)
        if old is not None:
            before = kicadcli.DrcSummary()
            before.by_type.update(old)
            for kind, was, now in kicadcli.delta(before, summary):
                print(f"   {kind:28s} {was:5d} -> {now:5d}")
        else:
            for kind, count in summary.by_type.most_common():
                tops = ", ".join(f"{p}:{n}" for p, n in summary.prefixes[kind].most_common(4))
                print(f"   {count:5d} {kind:28s} {summary.severities[kind]:8s} {tops}")
        if args.validate_rules:
            print(f"   rules: {kicadcli.validate_rules(kicad_cli, project.pro)}")
        if args.fail_on == "error" and summary.errors:
            failed += 1
        if args.fail_on == "warning" and summary.total:
            failed += 1
    if args.save:
        args.save.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")
    return 1 if failed else 0


def cmd_new_template(args, parser):
    kit = load_kit(args.kit)
    project = create_template(args.name, args.source, args.title, args.description,
                              project_name=args.project_name, templates_root=args.templates_root)
    result = applymod.apply_project(project, kit, applymod.ApplyOptions(prune_exclusions=True, commands=_commands(args)))
    if result.skipped:
        print(f"template created at {project.dir} but the kit was NOT applied: {result.skipped}")
        return 1
    print(f"created {project.dir} (project {project.name}); kit v{kit.version} applied")
    print("next: uv run pedal-fleet drc --templates --fail-on error; git add; commit; then create one project from it in KiCad")
    return 0


def cmd_clone(args, parser):
    kit = load_kit(args.kit)
    project = clonemod.clone_project(args.name, args.source, dest=args.dest, dest_root=args.repos,
                                     status=args.status, note=args.note)
    source_name = project_from_path(args.source).name
    print(f"cloned {source_name} -> {project.dir}")
    result = applymod.apply_project(project, kit, applymod.ApplyOptions(
        force=args.force, prune_exclusions=True, commands=_commands(args)))
    if result.skipped:
        print(f"kit NOT applied: {result.skipped}")
        return 1
    print(f"kit v{kit.version} applied ({len(result.written)} file(s))")
    for note in result.notes:
        print(f"  {note}")
    try:
        kicad_cli = None if args.no_verify else kicadcli.find_kicad_cli(args.kicad_cli)
    except FileNotFoundError:
        kicad_cli = None
    if kicad_cli is None:
        print("rename not verified" + ("" if args.no_verify else ": kicad-cli not found"))
    else:
        sheet = project.pro.with_suffix(".kicad_sch")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "verify.net"
            proc = subprocess.run([str(kicad_cli), "sch", "export", "netlist", "--format", "kicadsexpr",
                                   "-o", str(out), str(sheet)], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            print("rename verified: kicad-cli netlist export ok")
        else:
            print(f"rename NOT verified: kicad-cli netlist export failed: {proc.stderr.strip() or proc.stdout.strip()}")
            return 1
    leftovers = clonemod.leftover_mentions(project, source_name)
    if leftovers:
        print(f"still mentions {source_name} (title block / silk / notes, edit in KiCad): "
              + ", ".join(f"{name} x{count}" for name, count in leftovers.items()))
    if not args.no_git:
        gitutil.init_repo(project.dir, f"Initial commit: cloned from {source_name}")
        print("git: initialised on main with one commit")
        if args.github:
            print(gitutil.create_github_repo(project.dir, args.name, args.github))
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "apply": cmd_apply, "drc": cmd_drc, "new-template": cmd_new_template,
                "clone": cmd_clone}
    try:
        return handlers[args.verb](args, parser)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
