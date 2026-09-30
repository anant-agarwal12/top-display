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

## Requirements
- Windows 10/11
- Python 3.10+
- The Spotify desktop app (the song is read from Windows' media session)

## Setup
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run
| What | How |
| --- | --- |
| Overlay only | double-click `run.bat` |
| Tray launcher (`Ctrl+Alt+P` toggles the overlay) | double-click `run_launcher.bat` |
| Launcher at every login | `powershell -ExecutionPolicy Bypass -File .\install_startup.ps1` |

### Shortcuts
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
leaves your machine. Settings are stored in `%APPDATA%\TopDisplayLyricsOverlay`.

## License
GPL-3.0, see [LICENSE](LICENSE). Uses PySide6 (LGPL), winsdk (MIT) and requests (Apache-2.0).
