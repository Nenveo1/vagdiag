"""Start der Oberfläche:  python -m vagdiag"""

import sys


def _melden(text: str) -> None:
    """Ohne Konsole (pythonw unter Windows) als Meldungsfenster, sonst als Text."""
    if sys.stdout is None and sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "vagdiag", 0x10)
            return
        except Exception:
            pass
    print(text)


try:
    from .gui import main
except ImportError as exc:
    if "PySide6" not in str(exc):
        raise
    from . import einstellungen, sprache
    sprache.setzen(einstellungen.laden()["sprache"])
    _melden(sprache.t("PySide6 fehlt. Installation siehe README, z. B.:\n"
                      "  .venv/bin/pip install -r requirements.txt\n"
                      "Ohne Oberfläche geht es mit:  python -m vagdiag.cli --help"))
    sys.exit(1)

main()
