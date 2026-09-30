"""Standalone check: can we read the currently-playing Spotify track from
Windows? Run this with Spotify desktop open and a song playing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from media_session import fetch_now_playing

snapshot = fetch_now_playing()
if snapshot is None:
    print("No Spotify session found. Is the Spotify desktop app open and playing something?")
else:
    print(f"Title:    {snapshot.title}")
    print(f"Artist:   {snapshot.artist}")
    print(f"Album:    {snapshot.album}")
    print(f"Position: {snapshot.position_sec:.1f}s / {snapshot.duration_sec:.1f}s")
    print(f"Playing:  {snapshot.is_playing}")
