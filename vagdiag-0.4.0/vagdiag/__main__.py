"""Start der Oberfläche:  python -m vagdiag"""

import sys

try:
    from .gui import main
except ImportError as exc:
    if "PySide6" not in str(exc):
        raise
    from . import einstellungen, sprache
    sprache.setzen(einstellungen.laden()["sprache"])
    print(sprache.t("PySide6 fehlt. Installation siehe README, z. B.:\n"
                    "  .venv/bin/pip install -r requirements.txt\n"
                    "Ohne Oberfläche geht es mit:  python -m vagdiag.cli --help"))
    sys.exit(1)

main()
