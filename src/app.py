"""Single entry point for the packaged app.

    TopDisplay.exe                              tray launcher (start/stop shortcut, default Ctrl+Alt+P)
    TopDisplay.exe --overlay                    the lyrics overlay itself (what the launcher runs)
    TopDisplay.exe --set-hotkeys <start/stop> <lock>
                                                write the two shortcuts into settings.json and exit
                                                (used by the installer; no window, no Qt)
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))  # launcher.py lives in the project root


def _set_hotkeys(args) -> int:
    """Exit code: 0 saved, 2 wrong arguments, 3 not an allowed pair of shortcuts."""
    if len(args) != 2:
        return 2
    import settings
    return 0 if settings.set_hotkeys(args[0], args[1]) else 3


def run() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "--set-hotkeys":
        sys.exit(_set_hotkeys(argv[1:]))
    if "--overlay" in argv:
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
