"""Clone a board into a new project directory: copy the working files, rename the project, rewrite every
place KiCad embeds the project name (project-file meta, symbol-instance `project` entries in each sheet,
`sheetfile` entries in the board), and leave the owner's own text (silk, titles, notes) untouched."""
import json
import re
import shutil
from pathlib import Path

from .discover import Project, project_from_path
from .paths import DEFAULT_REPOS

STATUSES = ("active", "utility", "oddity", "wip", "shelved")
COPY_SUFFIXES = (".kicad_pro", ".kicad_pcb", ".kicad_sch", ".kicad_dru")
COPY_NAMES = ("fp-lib-table", "sym-lib-table", ".gitignore")
SKIP_PREFIXES = ("~", "_autosave")


def _copies(src: Project):
    for path in sorted(src.dir.iterdir()):
        if not path.is_file() or path.name.startswith(SKIP_PREFIXES):
            continue
        if path.suffix in COPY_SUFFIXES or path.name in COPY_NAMES:
            yield path


def _rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".kicad_sch":
        text = re.sub(r'\(project "' + re.escape(old) + '"', f'(project "{new}"', text)
    elif path.suffix == ".kicad_pcb":
        text = text.replace(f'(sheetfile "{old}.kicad_sch")', f'(sheetfile "{new}.kicad_sch")')
    path.write_text(text, encoding="utf-8")


def clone_project(name: str, source, dest=None, dest_root: Path = DEFAULT_REPOS,
                  status: str = None, note: str = None) -> Project:
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}, not {status!r}")
    src = project_from_path(source)
    dest = Path(dest).expanduser() if dest else Path(dest_root) / name
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    dest.mkdir(parents=True)
    for path in _copies(src):
        target = dest / (f"{name}{path.suffix}" if path.stem == src.name else path.name)
        shutil.copy2(path, target)
        if target.suffix in (".kicad_sch", ".kicad_pcb"):
            _rewrite(target, src.name, name)
    database = src.dir / "jlcpcb" / "project.db"
    if database.exists():
        (dest / "jlcpcb").mkdir()
        shutil.copy2(database, dest / "jlcpcb" / "project.db")

    pro_path = dest / f"{name}.kicad_pro"
    pro = json.loads(pro_path.read_text(encoding="utf-8"))
    pro.setdefault("meta", {})["filename"] = pro_path.name
    variables = pro.setdefault("text_variables", {})
    if status is not None:
        variables["BOARD_STATUS"] = status
        variables.pop("BOARD_NOTE", None)      # the source's reason is not this board's reason
    if note is not None:
        variables["BOARD_NOTE"] = note
    pro_path.write_text(json.dumps(pro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dest / "README.md").write_text(f"# {name}\n\nCloned from {src.name}.\n", encoding="utf-8")
    return Project(pro_path.resolve(), "board")


def leftover_mentions(project: Project, old: str) -> dict:
    """Files in the clone that still mention the source name (title blocks, silk, notes): the owner's to edit."""
    found = {}
    for path in sorted(project.dir.iterdir()):
        if path.is_file() and path.suffix in (".kicad_sch", ".kicad_pcb"):
            count = path.read_text(encoding="utf-8").count(old)
            if count:
                found[path.name] = count
    return found
