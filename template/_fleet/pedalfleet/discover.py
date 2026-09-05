"""Find KiCad projects: the fleet's boards under ~/Documents/repos and the templates beside the kit."""
from dataclasses import dataclass
from pathlib import Path

from .paths import DEFAULT_REPOS, TEMPLATES_ROOT

EXCLUDED_PARTS = {".history", ".venv", "node_modules", "Madbean", "template", "_fleet"}


@dataclass(frozen=True)
class Project:
    pro: Path
    kind: str  # "board" or "template"

    @property
    def dir(self) -> Path:
        return self.pro.parent

    @property
    def name(self) -> str:
        return self.pro.stem

    @property
    def pcb(self) -> Path:
        return self.pro.with_suffix(".kicad_pcb")

    @property
    def rules(self) -> Path:
        return self.pro.with_suffix(".kicad_dru")

    @property
    def lock_files(self) -> list:
        return [self.dir / f"~{self.name}.kicad_pcb.lck", self.dir / f"~{self.name}.kicad_sch.lck"]


def _excluded(pro: Path, root: Path) -> bool:
    rel = pro.relative_to(root)
    for part in rel.parts[:-1]:
        if part in EXCLUDED_PARTS or part.endswith("-backups"):
            return True
    return rel.name.startswith("tmp")


def find_boards(repos_root: Path = DEFAULT_REPOS, max_depth: int = 3) -> list:
    repos_root = Path(repos_root)
    found = []
    for pro in sorted(repos_root.rglob("*.kicad_pro")):
        if len(pro.relative_to(repos_root).parts) > max_depth:
            continue
        if _excluded(pro, repos_root):
            continue
        if not pro.with_suffix(".kicad_pcb").exists():
            continue
        found.append(Project(pro.resolve(), "board"))
    return found


def find_templates(templates_root: Path = TEMPLATES_ROOT) -> list:
    """Every subdirectory holding a meta/ folder is a template (that is KiCad's own rule)."""
    found = []
    for directory in sorted(p for p in Path(templates_root).iterdir() if p.is_dir()):
        if not (directory / "meta").is_dir():
            continue
        pros = sorted(directory.glob("*.kicad_pro"))
        if len(pros) != 1:
            raise ValueError(f"{directory}: expected exactly one .kicad_pro, found {len(pros)}")
        found.append(Project(pros[0].resolve(), "template"))
    return found


def project_from_path(path) -> Project:
    """Accept a .kicad_pro file or a directory holding exactly one."""
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        pros = sorted(path.glob("*.kicad_pro"))
        if len(pros) != 1:
            raise ValueError(f"{path}: expected exactly one .kicad_pro, found {len(pros)}")
        path = pros[0]
    elif not path.is_file():
        raise FileNotFoundError(f"{path}: no such project directory or .kicad_pro file")
    kind = "template" if (path.parent / "meta").is_dir() else "board"
    return Project(path, kind)
