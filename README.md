# Top Display

A small always-on-top lyrics overlay for Windows. It reads the song currently playing in the
Spotify desktop app and shows its **time-synced lyrics** in a translucent window, scrolling to
and highlighting the current line, so you can sing along without switching windows.

> Not affiliated with or endorsed by Spotify. Lyrics are fetched from third-party
> services and belong to their respective rights holders.

**Website and downloads: https://top-display.vercel.app** (it has a live demo of the animations). Its source is in [`site/`](site/); the download button follows the newest stable release.

## Features
- Synced lyrics that follow playback, with the current line highlighted and centred
- **Six lyric animation styles**, switchable while a song plays:
  Smooth, Karaoke (a colour sweep fills each line as it is sung), Typewriter (each line types
  itself out), Pop (a bouncy arrival), Spotlight (only the current line stands out) and
  Instant (no animation)
- Stays on top of other windows. Adjust the background opacity from fully solid down to **0**,
  which leaves just the text; at 0 clicks pass straight through the empty parts of the window
  (at any higher opacity the panel itself catches clicks)
- **Unlock mode**: the screen dims and you can drag and resize the overlay and change its
  opacity with the bar along the top. A small floating **gear** appears; click it for the
  settings pane (animation style, keyboard shortcuts, now-playing, quit). Drag the gear
  anywhere; the pane stays attached to it. Your layout is remembered.
- **Keyboard shortcuts you can change** (in the installer, or later in the settings pane)
- Lyrics are cached on disk, with a fallback source and automatic retries if the
  lyrics server is unreachable
- Optional tray launcher that starts and stops the overlay with a shortcut, and can start at login

## Install (Windows 10/11)
1. Download `TopDisplay-Setup-x.y.z.exe` from the [Releases](../../releases) page.
2. Run it. Windows SmartScreen may say "Windows protected your PC" because the installer is
   not code-signed yet: click **More info -> Run anyway**. You can compare the file with the
   published `.sha256` first.
3. The setup wizard asks you to accept the license, pick an install folder (per-user by
   default, no admin rights needed), a Start Menu folder, whether to **start Top Display when
   you sign in** and whether to add a **desktop shortcut**, and which **keyboard shortcuts**
   to use for start/stop and lock/unlock.
4. Open the Spotify desktop app, play a song, then press the start/stop shortcut
   (`Ctrl+Alt+P` unless you changed it).

Uninstall from Windows Settings -> Apps; it asks whether to also delete your settings and
cached lyrics. Installing a newer version over an older one keeps your settings and shortcuts.

## Using it
| Do this | To get this |
| --- | --- |
| Press the **start/stop** shortcut (default `Ctrl+Alt+P`) | Show or hide the lyrics overlay |
| Press the **lock/unlock** shortcut (default `Ctrl+Alt+L`) | Unlock: the screen dims, you can move and resize the overlay, set its opacity, and the gear appears |
| Click the **gear** (unlocked) | Open the settings pane: pick the lyric animation, change the shortcuts |
| Press lock/unlock again | Lock it again; the gear and pane go away |

While the overlay is running, its tray icon's menu has the same actions, including
**Lock / unlock**, which always works even if a shortcut is taken by another program.

### Shortcuts
Each shortcut is a pair of dropdowns: the modifier keys (`Ctrl + Alt`, `Ctrl + Shift`,
`Alt + Shift` or `Ctrl + Alt + Shift`) and a key (A-Z, 0-9 or F1-F12). The Windows key is not
offered because Windows reserves many of those combinations. The two shortcuts must differ.
If another program already uses a combination, the pane tells you and keeps the old one.
The start/stop shortcut is picked up by the tray launcher within a couple of seconds.

Overlay errors are written to `%APPDATA%\TopDisplayLyricsOverlay\overlay.log`.

## Run from source (developers)
Requires Python 3.10+ and the Spotify desktop app.
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

| What | How |
| --- | --- |
| Overlay only | double-click `run.bat` |
| Tray launcher | double-click `run_launcher.bat` |
| Launcher at every login | `powershell -ExecutionPolicy Bypass -File .\install_startup.ps1` |

### Build the installer yourself
```powershell
.venv\Scripts\pip install -r requirements-dev.txt
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # -> dist\TopDisplay-Setup-<version>.exe
```
The same build can be run on GitHub Actions (Actions tab -> Release -> Run workflow).

The installer is currently unsigned (Windows SmartScreen will warn on first run). The build signs
automatically once a certificate is configured; see [docs/SIGNING.md](docs/SIGNING.md).

Silent installs can choose the shortcuts too:
`TopDisplay-Setup-x.y.z.exe /VERYSILENT /TOGGLEHOTKEY=Ctrl+Alt+K /LOCKHOTKEY=Ctrl+Alt+J`

### Check the pieces
```powershell
.venv\Scripts\python test_media_session.py   # is Spotify's current track readable?
.venv\Scripts\python test_lyrics.py          # can lyrics be fetched?
```

## Data sources and privacy
Full details in [docs/PRIVACY.md](docs/PRIVACY.md). In short:

Lyrics come from [lrclib.net](https://lrclib.net) (synced) with
[lyrics.ovh](https://lyrics.ovh) as a plain-text fallback. The artist, title, album and
duration of the current song are sent to those services to look up lyrics. Nothing else
leaves your machine. Settings are stored in `%APPDATA%\TopDisplayLyricsOverlay` and the
lyrics cache in `%LOCALAPPDATA%\TopDisplayLyricsOverlay\cache`.

## License
GPL-3.0, see [LICENSE](LICENSE). Uses PySide6 (LGPL), winsdk (MIT) and requests (Apache-2.0).
