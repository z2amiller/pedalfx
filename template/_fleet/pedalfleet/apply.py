"""Stamp the kit into one project (apply) or measure its distance from the kit (check)."""
from dataclasses import dataclass, field

from . import projectfile, rules
from .discover import Project
from .guard import check_guard, kicad_running
from .kit import Kit


@dataclass
class ApplyOptions:
    dry_run: bool = False
    force: bool = False
    prune_exclusions: bool = False
    commands: list = None   # injected process list for tests; None = ask the OS


@dataclass
class ApplyResult:
    project: Project
    written: list = field(default_factory=list)   # paths written (or that would be, on dry run)
    notes: list = field(default_factory=list)
    skipped: str = None                            # reason, when the guard refused


def apply_project(project: Project, kit: Kit, options: ApplyOptions = None) -> ApplyResult:
    options = options or ApplyOptions()
    result = ApplyResult(project)
    guard = check_guard(project, force=options.force, commands=options.commands)
    if not guard.ok:
        result.skipped = guard.reason
        return result
    if guard.reason:
        result.notes.append(guard.reason)

    pro = projectfile.load(project.pro)
    changed = projectfile.merge_fragment(pro, kit.fragment)
    if options.prune_exclusions:
        pruned = projectfile.prune_exclusions(pro)
        if pruned:
            changed = True
            result.notes.append(f"pruned {pruned} exclusion(s)")
    if changed:
        if not options.dry_run:
            projectfile.save(project.pro, pro)
        result.written.append(project.pro)

    existing = project.rules.read_text(encoding="utf-8") if project.rules.exists() else None
    new_text, status = rules.splice(existing, kit.rules_block)
    if status == rules.MALFORMED:
        result.notes.append(f"{project.rules.name}: malformed (needs exactly one '(version N)' line and "
                            "complete fleet markers); left untouched")
    elif status != rules.UNCHANGED:
        if not options.dry_run:
            project.rules.write_text(new_text, encoding="utf-8")
        result.written.append(project.rules)
        result.notes.append(f"{project.rules.name}: {status}")

    gitignore = project.dir / ".gitignore"
    if project.kind == "board":
        needs_write = not gitignore.exists()
    else:
        needs_write = not gitignore.exists() or gitignore.read_text(encoding="utf-8") != kit.gitignore
    if needs_write:
        if not options.dry_run:
            gitignore.write_text(kit.gitignore, encoding="utf-8")
        result.written.append(gitignore)
    return result


@dataclass
class CheckResult:
    project: Project
    drift: list = field(default_factory=list)
    stale_exclusions: int = 0
    kicad_open: bool = False

    def ok(self) -> bool:
        return not self.drift


def check_project(project: Project, kit: Kit, commands=None) -> CheckResult:
    result = CheckResult(project)
    pro = projectfile.load(project.pro)
    result.drift.extend(projectfile.drift(pro, kit.fragment))
    result.stale_exclusions = projectfile.count_exclusions(pro)

    name = project.rules.name
    if not project.rules.exists():
        result.drift.append(f"{name}: missing")
    else:
        text = project.rules.read_text(encoding="utf-8")
        if len(rules.VERSION_RE.findall(text)) != 1:
            result.drift.append(f"{name}: needs exactly one (version N) line")
        try:
            span = rules.find_block(text)
        except ValueError:
            result.drift.append(f"{name}: fleet markers incomplete or out of order")
        else:
            if span is None:
                result.drift.append(f"{name}: fleet block missing")
            elif text[span[0]:span[1]] != kit.rules_block:
                result.drift.append(f"{name}: fleet block differs from kit v{kit.version}")

    gitignore = project.dir / ".gitignore"
    if not gitignore.exists():
        result.drift.append(".gitignore: missing")
    elif project.kind == "template":
        if gitignore.read_text(encoding="utf-8") != kit.gitignore:
            result.drift.append(".gitignore: differs from kit")
    else:
        text = gitignore.read_text(encoding="utf-8")
        for needle in ("*-backups", "fp-info-cache"):
            if needle not in text:
                result.drift.append(f".gitignore: lacks {needle}")

    locks = [path for path in project.lock_files if path.exists()]
    result.kicad_open = bool(locks) and kicad_running(commands)
    return result
