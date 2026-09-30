"""Single entry point for the packaged app.

    TopDisplay.exe             tray launcher (Ctrl+Alt+P starts/stops the overlay)
    TopDisplay.exe --overlay   the lyrics overlay itself (what the launcher runs)
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))  # launcher.py lives in the project root


def run() -> None:
    if "--overlay" in sys.argv[1:]:
        import single_instance
        if not single_instance.acquire("TopDisplayOverlay"):
            return
        import main
        main.main()
    else:
        import single_instance
        if not single_instance.acquire("TopDisplayLauncher"):
            return
        import launcher
        launcher.main()


if __name__ == "__main__":
    run()
