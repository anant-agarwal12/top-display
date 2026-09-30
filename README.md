# Top Display

A small always-on-top, click-through lyrics overlay for Windows. It reads the song
currently playing in the Spotify desktop app and shows its **time-synced lyrics** in a
translucent window, scrolling and highlighting the current line, so you can sing along
without switching windows.

> Not affiliated with or endorsed by Spotify. Lyrics are fetched from third-party
> services and belong to their respective rights holders.

## Features
- Synced lyrics that follow playback, with the current line highlighted and centred
- Stays on top of other windows; in normal ("locked") mode clicks pass straight through it
- **Unlock mode** (`Ctrl+Alt+L`): the screen dims and you can drag and resize the overlay
  and change its background opacity; your layout is remembered
- Lyrics are cached on disk, with a fallback source and automatic retries if the
  lyrics server is unreachable
- Optional tray launcher: `Ctrl+Alt+P` starts/stops the overlay, and it can start at login

## Install (Windows 10/11)
1. Download `TopDisplay-Setup-x.y.z.exe` from the [Releases](../../releases) page.
2. Run it. Windows SmartScreen may say "Windows protected your PC" because the installer is
   not code-signed yet: click **More info -> Run anyway**. You can compare the file with the
   published `.sha256` first.
3. The setup wizard asks you to accept the license, pick an install folder (per-user by
   default, no admin rights needed), a Start Menu folder, and whether to **start Top Display
   when you sign in** and whether to add a **desktop shortcut**.
4. Open the Spotify desktop app, play a song, then press `Ctrl+Alt+P`.

Uninstall from Windows Settings -> Apps; it asks whether to also delete your settings and
cached lyrics.

## Run from source (developers)
Requires Python 3.10+ and the Spotify desktop app.
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

| What | How |
| --- | --- |
| Overlay only | double-click `run.bat` |
| Tray launcher (`Ctrl+Alt+P` toggles the overlay) | double-click `run_launcher.bat` |
| Launcher at every login | `powershell -ExecutionPolicy Bypass -File .\install_startup.ps1` |

### Build the installer yourself
```powershell
.venv\Scripts\pip install -r requirements-dev.txt
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # -> dist\TopDisplay-Setup-<version>.exe
```
Pushing a tag like `v0.1.0` builds it on GitHub Actions and attaches it to a draft Release.

## Shortcuts
| Keys | Action |
| --- | --- |
| `Ctrl+Alt+P` | Start / stop the overlay (launcher must be running) |
| `Ctrl+Alt+L` | Lock / unlock the overlay (unlocked = move, resize, opacity) |

If a shortcut does nothing, another app may already be using that key combination.
Overlay errors are written to `%APPDATA%\TopDisplayLyricsOverlay\overlay.log`.

## Check the pieces
```powershell
.venv\Scripts\python test_media_session.py   # is Spotify's current track readable?
.venv\Scripts\python test_lyrics.py          # can lyrics be fetched?
```

## Data sources and privacy
Lyrics come from [lrclib.net](https://lrclib.net) (synced) with
[lyrics.ovh](https://lyrics.ovh) as a plain-text fallback. The artist, title, album and
duration of the current song are sent to those services to look up lyrics. Nothing else
leaves your machine. Settings are stored in `%APPDATA%\TopDisplayLyricsOverlay` and the
lyrics cache in `%LOCALAPPDATA%\TopDisplayLyricsOverlay\cache`.

## License
GPL-3.0, see [LICENSE](LICENSE). Uses PySide6 (LGPL), winsdk (MIT) and requests (Apache-2.0).
