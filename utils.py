import os
from collections.abc import Iterable

from constants import SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS


def format_time(seconds: float | int | None) -> str:
    seconds = max(0, int(seconds or 0))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours > 0 else f"{minutes:02d}:{secs:02d}"


def is_supported_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def find_matching_subtitle(video_path: str) -> str | None:
    base = os.path.splitext(video_path)[0]
    for ext in SUBTITLE_EXTENSIONS:
        sub_path = base + ext
        if os.path.exists(sub_path):
            return sub_path
    return None


def normalize_recent_files(paths: Iterable[str] | None, new_path: str | None = None, limit: int = 5) -> list[str]:
    result: list[str] = []
    if new_path:
        result.append(new_path)
    for path in paths or []:
        if path and path not in result and os.path.exists(path):
            result.append(path)
        if len(result) >= limit:
            break
    return result
