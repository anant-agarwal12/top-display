import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from lyrics_fetcher import fetch_lyrics

synced, plain, state = fetch_lyrics("Cigarettes After Sex", "Cry", "Cry", 257, "test::Cry")
print("state:", state)
print("synced line count:", len(synced))
if synced:
    print("first line timestamp:", synced[0][0])
    print("last line timestamp:", synced[-1][0])
print("plain length:", len(plain))
