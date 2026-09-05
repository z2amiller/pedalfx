"""Turn a finished project into a KiCad template directory (meta/info.html, clean files, kit applied by the CLI)."""
import json
import shutil
from html import escape
from pathlib import Path

from .discover import Project, project_from_path
from .paths import TEMPLATES_ROOT

COPY_SUFFIXES = (".kicad_pro", ".kicad_pcb", ".kicad_sch")
INFO_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h1>{title}</h1>
<p>{description}</p>
</body>
</html>
"""


def create_template(name: str, source, title: str, description: str,
                    project_name: str = None, templates_root: Path = TEMPLATES_ROOT) -> Project:
    src = project_from_path(source)
    dest = Path(templates_root) / name
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    new_base = project_name or src.name
    dest.mkdir(parents=True)
    for path in sorted(src.dir.iterdir()):
        if not path.is_file() or path.suffix not in COPY_SUFFIXES:
            continue
        if path.name.startswith("~") or path.name.startswith("_autosave"):
            continue
        target_name = f"{new_base}{path.suffix}" if path.stem == src.name else path.name
        shutil.copy2(path, dest / target_name)
    database = src.dir / "jlcpcb" / "project.db"
    if database.exists():
        (dest / "jlcpcb").mkdir()
        shutil.copy2(database, dest / "jlcpcb" / "project.db")
    pro_path = dest / f"{new_base}.kicad_pro"
    pro = json.loads(pro_path.read_text(encoding="utf-8"))
    pro.setdefault("meta", {})["filename"] = pro_path.name
    pro_path.write_text(json.dumps(pro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dest / "meta").mkdir()
    (dest / "meta" / "info.html").write_text(
        INFO_HTML.format(title=escape(title), description=escape(description)), encoding="utf-8")
    return Project(pro_path.resolve(), "template")
