from pathlib import Path

FLEET_DIR = Path(__file__).resolve().parents[1]      # .../pedalfx/template/_fleet
KIT_DIR = FLEET_DIR / "kit"
TEMPLATES_ROOT = FLEET_DIR.parent                    # .../pedalfx/template
DEFAULT_REPOS = Path.home() / "Documents" / "repos"
KICAD_CLI_DEFAULT = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
