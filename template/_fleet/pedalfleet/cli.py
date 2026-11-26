"""pedal-fleet command line: check | apply | drc | new-template | clone | silk-labels | outline."""
import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from . import apply as applymod
from . import clone as clonemod
from . import gitutil, guard, kicadcli, outline, projectfile, rules, silklabels
from .discover import find_boards, find_templates, project_from_path
from .kit import load_kit
from .newtemplate import create_template
from .paths import DEFAULT_REPOS, KIT_DIR, TEMPLATES_ROOT

COMMIT_MESSAGE = "pedal-fleet: apply fleet kit v{version}"


def _add_target_args(parser, kit=True):
    parser.add_argument("targets", nargs="*", help="project directories or .kicad_pro files")
    parser.add_argument("--templates", action="store_true", help="every template under the templates root")
    parser.add_argument("--boards", action="store_true", help="every board under the repos root")
    parser.add_argument("--all", action="store_true", help="--templates and --boards")
    parser.add_argument("--repos", type=Path, default=DEFAULT_REPOS)
    parser.add_argument("--templates-root", type=Path, default=TEMPLATES_ROOT)
    if kit:
        parser.add_argument("--kit", type=Path, default=KIT_DIR)
        parser.add_argument("--kicad-cli", default=None)
    parser.add_argument("--no-process-check", action="store_true",
                        help="do not look for running KiCad processes (tests)")


def build_parser():
    parser = argparse.ArgumentParser(prog="pedal-fleet",
                                     description="keep KiCad templates and boards on the fleet kit")
    sub = parser.add_subparsers(dest="verb", required=True)

    check = sub.add_parser("check", help="report drift from the kit and outline defects (read-only; exit 1 on either)")
    _add_target_args(check)
    check.add_argument("--no-outline", action="store_true", help="skip the board-outline check")

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

    sl = sub.add_parser("silk-labels",
                        help="put 2-pad passive/diode reference labels north (horizontal parts) or west (vertical), "
                             "and hand-fit cap values on the silk between their leads")
    sl.add_argument("targets", nargs="+", help="project directories or .kicad_pro files")
    sl.add_argument("--dry-run", action="store_true", help="report the plan, write nothing")
    sl.add_argument("--gap", type=float, default=silklabels.GAP, help="mm from the part's own pads and silk to the label's edge")
    sl.add_argument("--skip", default="", help="comma-separated refs to leave alone (label and value)")
    sl.add_argument("--no-values", action="store_true",
                    help="leave hand-fit cap values alone (default: show each one on F.SilkS between its leads)")
    sl.add_argument("--no-drc", action="store_true", help="skip the kicad-cli DRC cross-check")
    sl.add_argument("--kicad-cli", default=None)
    sl.add_argument("--force", action="store_true", help="proceed while KiCad runs (never with a lock file)")
    sl.add_argument("--no-process-check", action="store_true")

    ol = sub.add_parser("outline",
                        help="check board outlines (Edge.Cuts) for micro-gaps, stubs and split lines; --fix heals them")
    _add_target_args(ol, kit=False)
    ol.add_argument("--tol", type=float, default=outline.TOL,
                    help="heal tolerance in mm: ends closer than this are joined, lines shorter than it dropped")
    ol.add_argument("--fix", action="store_true", help="heal the outline and write the board")
    ol.add_argument("--dry-run", action="store_true", help="print the planned edits as a diff, write nothing")
    ol.add_argument("--force", action="store_true", help="proceed while KiCad runs (never with a lock file)")
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


def _outline_defects(project) -> str:
    """One-line summary of a board's outline defects for check, or ''."""
    if not project.pcb.exists():
        return ""
    try:
        result = outline.analyse(project.pcb.read_text(encoding="utf-8"))
    except ValueError as error:
        return f"OUTLINE: unreadable ({error})"
    defects = result.defects()
    if not defects:
        return ""
    kinds = Counter(f.kind for f in result.plan.findings if f.kind != "collinear")
    names = {"open": "open end", "junction": "tangle"}
    what = ", ".join(f"{count} {names.get(kind, kind)}(s)" for kind, count in sorted(kinds.items())) or defects[0]
    return f"OUTLINE: {what} (see pedal-fleet outline)"


def cmd_check(args, parser):
    kit = load_kit(args.kit)
    drifted = bad_outlines = 0
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
        defects = "" if args.no_outline else _outline_defects(project)
        if defects:
            bad_outlines += 1
            status = defects if result.ok() else f"{status}; {defects}"
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"{project.name:36s} {project.kind:9s} {status}{suffix}")
    tail = f", {bad_outlines} with outline defects" if bad_outlines else ""
    print(f"{len(projects)} projects, {len(projects) - drifted} in sync, {drifted} drifted{tail}")
    return 1 if drifted or bad_outlines else 0


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


def cmd_silk_labels(args, parser):
    skip = {ref.strip() for ref in args.skip.split(",") if ref.strip()}
    kicad_cli = None
    if not args.no_drc:
        try:
            kicad_cli = kicadcli.find_kicad_cli(args.kicad_cli)
        except FileNotFoundError:
            print("kicad-cli not found: DRC cross-check skipped")
    failures = 0
    for target in args.targets:
        project = project_from_path(target)
        if not project.pcb.exists():
            print(f"{project.name}: no board file, skipped")
            continue
        checked = guard.check_guard(project, force=args.force, commands=_commands(args))
        if not checked.ok:
            print(f"{project.name}: not touched: {checked.reason}")
            failures += 1
            continue
        result = silklabels.run(project.pcb, project.pro, gap=args.gap, skip=skip, kicad_cli=kicad_cli,
                                values=not args.no_values)
        moved, placed = result.count("move"), result.count_values("place")
        print(f"== {project.name}: {len(result.plans)} passive/diode label(s): {moved} moved, "
              f"{result.count('keep')} already fit, {result.count('blocked')} left alone"
              + (f", {result.count('skip')} skipped" if result.count("skip") else ""))
        left = sorted((ref, plan.reason) for ref, plan in result.plans.items() if plan.action == "blocked")
        if left:
            print("   left alone:")
            for ref, reason in left:
                print(f"     {ref:6s} {reason}")
        if result.values:
            _print_values(result)
        if result.drc_checked:
            kinds = sorted(set(result.silk_before) | set(result.silk_after))
            change = ", ".join(f"{k} {result.silk_before[k]} -> {result.silk_after[k]}" for k in kinds) or "none"
            new = "none" if not result.new_violations else f"{len(result.new_violations)} (not from moved labels or placed values)"
            print(f"   DRC silk: {change}; new: {new}")
        elif (moved or placed) and kicad_cli is None and not args.no_drc:
            print("   DRC cross-check skipped")
        if args.dry_run or not (moved or placed):
            print("   nothing written" + (" (dry run)" if args.dry_run and (moved or placed) else ""))
        else:
            project.pcb.write_text(result.text, encoding="utf-8")
            print(f"   wrote {project.pcb.name}: {moved} label(s) moved"
                  + (f", {placed} cap value(s) placed" if placed else "") + "; open it in KiCad to review")
    return 1 if failures else 0


def _print_values(result):
    print(f"   hand-fit cap values: {result.count_values('place')} placed, {result.count_values('keep')} already centred, "
          f"{result.count_values('blocked') + result.count_values('skip')} left alone")
    for heading, actions in (("placed", ("place",)), ("left alone", ("blocked", "skip"))):
        rows = sorted((ref, plan) for ref, plan in result.values.items() if plan.action in actions)
        if rows:
            print(f"   {heading}:")
        for ref, plan in rows:
            print(f"     {ref:6s} {plan.text:6s} {plan.reason}".rstrip())


def _kicad_open(project, args) -> bool:
    return any(path.exists() for path in project.lock_files) and guard.kicad_running(_commands(args))


def _outline_one(project, args) -> str:
    """Check (and with --fix or --dry-run, heal) one board. Returns clean | healed | findings | failed."""
    text = project.pcb.read_text(encoding="utf-8")
    try:
        result = outline.analyse(text, args.tol)
    except ValueError as error:
        print(f"== {project.name}: cannot read the outline: {error}")
        return "failed"
    owners = sorted({shape.footprint for shape in result.shapes if shape.footprint})
    footprint_shapes = len(result.shapes) - result.board_shapes
    count = f"{result.board_shapes} Edge.Cuts shape(s)" + (
        f" (+{footprint_shapes} in footprint(s) {', '.join(owners)}, read-only)" if owners else "")
    stale = "  [open in KiCad: the file on disk may be stale]" if _kicad_open(project, args) else ""
    if result.empty:
        print(f"== {project.name}: no Edge.Cuts shapes, nothing to check{stale}")
        return "clean"
    if result.clean:
        print(f"== {project.name}: {count}, clean; {result.closure.summary()}{stale}")
        return "clean"
    found = f"{len(result.plan.findings)} finding(s)" if result.plan.findings else "outline problem"
    print(f"== {project.name}: {count}, {found}{stale}")
    for finding in result.plan.findings:
        print(f"   {finding.text}")
    print(f"   as drawn: {result.closure.summary()}")
    if result.healed is not None:
        print(f"   healed:   {result.healed.summary()}")
    if result.heals:
        for finding in result.leftover:
            print(f"   still left after healing: {finding.text}")
    if not (args.fix or args.dry_run):
        if result.heals:
            print("   --fix heals this (--dry-run shows the diff)")
        return "findings"
    if not result.plan.changes:
        print("   nothing to heal automatically; fix by hand")
        return "failed"
    if not result.heals:
        print("   not written: the healed outline would still not close exactly")
        return "failed"
    edits = (f"{len(result.plan.moves)} end(s) moved, {len(result.plan.drops)} shape(s) removed")
    if args.dry_run:
        print(_diff(text, result.text, project.pcb.name), end="")
        print(f"   nothing written (dry run): {edits}")
        return "findings"
    checked = guard.check_guard(project, force=args.force, commands=_commands(args))
    if not checked.ok:
        print(f"   not touched: {checked.reason}")
        return "failed"
    project.pcb.write_text(result.text, encoding="utf-8")
    print(f"   wrote {project.pcb.name}: {edits}; open it in KiCad to review")
    return "findings" if result.leftover else "healed"


def cmd_outline(args, parser):
    if args.tol < 0:
        parser.error("--tol must not be negative")
    projects = resolve_targets(args, parser)
    outcomes = Counter()
    for project in projects:
        if not project.pcb.exists():
            print(f"{project.name}: no board file, skipped")
            continue
        outcomes[_outline_one(project, args)] += 1
    if len(projects) > 1:
        print(f"{len(projects)} projects: {outcomes['clean']} clean, {outcomes['healed']} healed, "
              f"{outcomes['findings']} with findings, {outcomes['failed']} need a hand fix or were not touched")
    return 1 if outcomes["findings"] or outcomes["failed"] else 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "apply": cmd_apply, "drc": cmd_drc, "new-template": cmd_new_template,
                "clone": cmd_clone, "silk-labels": cmd_silk_labels, "outline": cmd_outline}
    try:
        return handlers[args.verb](args, parser)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
