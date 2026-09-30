"""Fetches synced lyrics from lrclib.net (free, no API key required)."""
import json
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import quote

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

USER_AGENT = "TopDisplayLyricsOverlay/1.0 (personal desktop overlay)"
BASE_URL = "https://lrclib.net/api"
# Fallback source: free and keyless, but plain lyrics only (no timing).
OVH_URL = "https://api.lyrics.ovh/v1"

# lrclib has intermittent 503s/timeouts. A request is retried after each of
# these delays before we give up and report a transient error.
_RETRY_DELAYS_SEC = (0.0, 1.0, 2.5)
_REQUEST_TIMEOUT_SEC = 8
# A "not found" answer is re-checked after this long, since lrclib's
# community database keeps growing.
_NOT_FOUND_TTL_SEC = 24 * 60 * 60
# Bump when the selection logic changes so older cached picks are redone.
# v2: pick the consensus timing across lrclib uploads.
_CACHE_VERSION = 2

_CLEAN_PATTERNS = [
    re.compile(r"\s*-\s*remaster(ed)?.*$", re.IGNORECASE),
    re.compile(r"\s*\(feat\.[^)]*\)", re.IGNORECASE),
    re.compile(r"\s*-\s*live.*$", re.IGNORECASE),
    re.compile(r"\s*\(live.*?\)", re.IGNORECASE),
]

_LRC_LINE = re.compile(r"\[(\d{2}):(\d{2})(?:\.(\d{1,3}))?\](.*)")


def _clean(text: str) -> str:
    for pat in _CLEAN_PATTERNS:
        text = pat.sub("", text)
    return text.strip()


def _cache_path(track_key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", track_key)[:150]
    return CACHE_DIR / f"{safe}.json"


def parse_lrc(lrc_text: str) -> List[Tuple[float, str]]:
    lines = []
    for raw_line in lrc_text.splitlines():
        match = _LRC_LINE.match(raw_line.strip())
        if not match:
            continue
        minutes, seconds, frac, text = match.groups()
        frac = (frac or "0").ljust(3, "0")[:3]
        total = int(minutes) * 60 + int(seconds) + int(frac) / 1000.0
        text = text.strip()
        if text:
            lines.append((total, text))
    lines.sort(key=lambda x: x[0])
    return lines


def _get_json(url: str, params: dict):
    """Returns ("ok", data), ("not_found", None) or ("error", None).
    Only a real 404 counts as not found; 429/5xx/timeouts are errors."""
    headers = {"User-Agent": USER_AGENT}
    for delay in _RETRY_DELAYS_SEC:
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=_REQUEST_TIMEOUT_SEC)
        except requests.RequestException:
            continue
        if resp.status_code == 200:
            try:
                return "ok", resp.json()
            except ValueError:
                continue
        if resp.status_code == 404:
            return "not_found", None
    return "error", None


def _duration_gap(item: dict, duration_sec: float) -> float:
    return abs((item.get("duration") or 0) - duration_sec) if duration_sec else 0.0


def _best_match(results: list, duration_sec: float) -> Optional[dict]:
    if not results:
        return None

    def score(item):
        has_synced = bool(item.get("syncedLyrics"))
        has_any = has_synced or bool(item.get("plainLyrics"))
        return (not has_synced, not has_any, _duration_gap(item, duration_sec))

    return min(results, key=score)


def _timestamps(item: dict) -> List[float]:
    return [t for t, _ in parse_lrc(item.get("syncedLyrics") or "")]


def _timings_agree(a: List[float], b: List[float]) -> bool:
    if not a or not b or abs(len(a) - len(b)) > 3:
        return False
    diffs = sorted(abs(x - y) for x, y in zip(a, b))
    return diffs[len(diffs) // 2] < 0.6


def _consensus_pick(candidates: list, duration_sec: float) -> dict:
    """lrclib is community-uploaded, and one song can have many uploads with
    different timing -- e.g. one "Alag Aasmaan" upload drifts up to ~4s late
    while ~15 others agree exactly. Pick the timing most uploads agree on,
    breaking ties by closeness to Spotify's reported duration."""
    close = [c for c in candidates if _duration_gap(c, duration_sec) <= 3]
    pool = close or candidates
    stamps = [_timestamps(c) for c in pool]

    def score(i):
        votes = sum(1 for j in range(len(pool)) if _timings_agree(stamps[i], stamps[j]))
        return (-votes, _duration_gap(pool[i], duration_sec))

    return pool[min(range(len(pool)), key=score)]


def _query_lrclib(artist: str, title: str, album: str, duration_sec: float):
    """Returns ("ok", result), ("not_found", None) or ("error", None)."""
    search_status, results = _get_json(
        f"{BASE_URL}/search", {"artist_name": artist, "track_name": title}
    )
    if search_status == "ok" and results:
        synced = [r for r in results if r.get("syncedLyrics") and not r.get("instrumental")]
        if synced:
            return "ok", _consensus_pick(synced, duration_sec)
        return "ok", _best_match(results, duration_sec)

    # Search can miss when Spotify's title differs slightly; the exact-match
    # endpoint is the fallback.
    get_params = {"artist_name": artist, "track_name": title, "album_name": album}
    if duration_sec:
        get_params["duration"] = int(round(duration_sec))
    get_status, data = _get_json(f"{BASE_URL}/get", get_params)
    if get_status == "ok" and data:
        return "ok", data
    if search_status == "error" or get_status == "error":
        return "error", None
    return "not_found", None


def _tidy_plain(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = text.split("\n")
    # lyrics.ovh sometimes prepends a French "Paroles de la chanson X par Y" header.
    if lines and lines[0].lower().startswith("paroles de la chanson"):
        lines = lines[1:]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _query_lyrics_ovh(artist: str, title: str) -> Optional[str]:
    url = f"{OVH_URL}/{quote(artist, safe='')}/{quote(title, safe='')}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=_REQUEST_TIMEOUT_SEC)
        if resp.status_code != 200:
            return None
        return _tidy_plain(resp.json().get("lyrics") or "") or None
    except (requests.RequestException, ValueError):
        return None


def _read_cache(cache_file: Path):
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("v") != _CACHE_VERSION:
        return None
    state = data.get("state", "not_found")
    # Re-check lrclib periodically for songs it didn't have, including ones
    # we filled in with plain lyrics from the fallback source.
    provisional = state == "not_found" or data.get("source") == "lyrics.ovh"
    if provisional and time.time() - data.get("cached_at", 0) > _NOT_FOUND_TTL_SEC:
        return None
    return data.get("synced", []), data.get("plain", ""), state


def fetch_lyrics(artist: str, title: str, album: str, duration_sec: float, track_key: str):
    """Returns (synced_lines, plain_text, state) where state is one of
    'synced', 'plain', 'instrumental', 'not_found', or one of two uncached
    states the caller should retry later:
      'fallback' -- lrclib unreachable, plain lyrics from lyrics.ovh instead
      'error'    -- lrclib unreachable and the fallback had nothing either"""
    cache_file = _cache_path(track_key)
    cached = _read_cache(cache_file)
    if cached is not None:
        return cached

    clean_artist, clean_title = _clean(artist), _clean(title)
    status, result = _query_lrclib(clean_artist, clean_title, album, duration_sec)
    if status == "error":
        # Not cached: lrclib may well have timed lyrics once it's back.
        plain = _query_lyrics_ovh(clean_artist, clean_title)
        return ([], plain, "fallback") if plain else ([], "", "error")

    synced_lines: List[Tuple[float, str]] = []
    plain_text = ""
    state = "not_found"
    source = "lrclib"
    if result:
        if result.get("instrumental"):
            state = "instrumental"
        elif result.get("syncedLyrics"):
            synced_lines = parse_lrc(result["syncedLyrics"])
            state = "synced" if synced_lines else "not_found"
        elif result.get("plainLyrics"):
            plain_text = result["plainLyrics"]
            state = "plain"

    if state == "not_found":
        plain = _query_lyrics_ovh(clean_artist, clean_title)
        if plain:
            plain_text, state, source = plain, "plain", "lyrics.ovh"

    try:
        cache_file.write_text(
            json.dumps({
                "synced": synced_lines, "plain": plain_text, "state": state,
                "source": source, "cached_at": time.time(), "v": _CACHE_VERSION,
            }),
            encoding="utf-8",
        )
    except Exception:
        pass

    return synced_lines, plain_text, state
