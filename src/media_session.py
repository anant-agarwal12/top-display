"""Reads the currently-playing Spotify track from the Windows System Media
Transport Controls (GSMTC). This works with the Spotify desktop app and a
free Spotify account -- no developer app, OAuth, or Premium required.
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)


@dataclass
class NowPlaying:
    title: str
    artist: str
    album: str
    duration_sec: float
    position_sec: float
    is_playing: bool
    position_ref_epoch: float  # wall-clock time (time.time()) that position_sec corresponds to
    track_key: str

    def interpolated_position(self) -> float:
        if not self.is_playing:
            return self.position_sec
        elapsed = max(0.0, time.time() - self.position_ref_epoch)
        pos = self.position_sec + elapsed
        if self.duration_sec:
            pos = min(pos, self.duration_sec)
        return pos


async def _get_spotify_session():
    manager = await MediaManager.request_async()
    for session in manager.get_sessions():
        app_id = (session.source_app_user_model_id or "").lower()
        if "spotify" in app_id:
            return session
    return None


async def _fetch_now_playing_async() -> Optional[NowPlaying]:
    session = await _get_spotify_session()
    if session is None:
        return None

    info = await session.try_get_media_properties_async()
    timeline = session.get_timeline_properties()
    playback_info = session.get_playback_info()

    title = (info.title or "").strip()
    artist = (info.artist or "").strip()
    album = (info.album_title or "").strip()

    if not title:
        return None

    duration_sec = timeline.end_time.total_seconds() - timeline.start_time.total_seconds()
    position_sec = timeline.position.total_seconds()
    is_playing = playback_info.playback_status == PlaybackStatus.PLAYING

    poll_time = time.time()
    try:
        position_ref_epoch = timeline.last_updated_time.timestamp()
    except Exception:
        position_ref_epoch = poll_time

    # Guard against clock/timezone weirdness in the WinRT->Python conversion:
    # if the reported update time doesn't make sense relative to now, fall
    # back to treating the position as fresh at poll time.
    elapsed_since_update = poll_time - position_ref_epoch
    if elapsed_since_update < -2 or elapsed_since_update > 120:
        position_ref_epoch = poll_time

    return NowPlaying(
        title=title,
        artist=artist,
        album=album,
        duration_sec=max(duration_sec, 0.0),
        position_sec=max(position_sec, 0.0),
        is_playing=is_playing,
        position_ref_epoch=position_ref_epoch,
        track_key=f"{artist}::{title}::{album}",
    )


def fetch_now_playing() -> Optional[NowPlaying]:
    """Synchronous wrapper -- safe to call from a background thread."""
    try:
        return asyncio.run(_fetch_now_playing_async())
    except Exception:
        return None
