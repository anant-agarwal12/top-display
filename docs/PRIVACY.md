# Privacy

Top Display has no accounts, no analytics, no crash reporting and no advertising. It sends
nothing about you anywhere except what is needed to look up lyrics, described here.

## What leaves your computer
To find lyrics for the song that is playing, the app sends that song's **artist name, title,
album name and length** to:

- [lrclib.net](https://lrclib.net), a free public lyrics database (the main source), and
- [lyrics.ovh](https://lyrics.ovh), used as a plain-text fallback only if lrclib is unreachable or
  has nothing.

As with any internet request, those services can see your IP address. The requests identify the
app as `TopDisplayLyricsOverlay`. They are made only while a song is playing in the Spotify desktop
app. Nothing else is sent: not your listening history, not your Spotify account, not your files.

The app does not talk to Spotify's servers. It reads which song is playing from Windows' own media
session on your computer.

## What is stored on your computer
- `%APPDATA%\TopDisplayLyricsOverlay\settings.json`: your settings (window position, opacity,
  animation style, keyboard shortcuts), and `overlay.log`, an error log.
- `%LOCALAPPDATA%\TopDisplayLyricsOverlay\cache`: lyrics already looked up, so they are not
  requested twice.

Uninstalling offers to delete all of this. Nothing is stored anywhere else.

## Changes
If this ever changes, the change will be listed in the release notes and here.
