import os
import re
import tempfile
from html import unescape
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
    dir_name, file_name = os.path.split(video_path)
    if not dir_name:
        dir_name = "."
    base_name, _ = os.path.splitext(file_name)
    base_name_lower = base_name.lower()
    
    try:
        with os.scandir(dir_name) as entries:
            for entry in entries:
                if entry.is_file():
                    entry_base, entry_ext = os.path.splitext(entry.name)
                    if entry_base.lower() == base_name_lower and entry_ext.lower() in SUBTITLE_EXTENSIONS:
                        return entry.path
    except Exception:
        pass
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


def _format_srt_timestamp(milliseconds: int) -> str:
    milliseconds = max(0, milliseconds)
    seconds, millis = divmod(milliseconds, 1000)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _clean_smi_text(text: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"\{\\[^}]+\}", "", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = unescape(text).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def convert_smi_to_srt_text(smi_text: str) -> str:
    matches = list(re.finditer(r"(?is)<sync\s+start\s*=\s*(\d+)\s*>", smi_text))
    cues: list[tuple[int, int, str]] = []
    starts = [int(match.group(1)) for match in matches]
    for index, match in enumerate(matches):
        start = starts[index]
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(smi_text)
        text = _clean_smi_text(smi_text[body_start:body_end])
        if not text:
            continue
        later_starts = [candidate for candidate in starts[index + 1:] if candidate > start]
        end = later_starts[0] if later_starts else start + 3000
        if end <= start:
            end = start + 3000
        cues.append((start, end, text))
    blocks = []
    for number, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{number}\n{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _read_and_decode_subtitle(path: str) -> str:
    """Read a subtitle file and decode with CJK encoding fallback."""
    raw = open(path, "rb").read()
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def convert_subtitle_to_utf8(subtitle_path: str) -> str | None:
    """If subtitle file is not valid UTF-8, re-encode as a UTF-8 temp file.

    Returns the temp file path, or None if already valid UTF-8 or undecodable.
    """
    raw = open(subtitle_path, "rb").read()

    # Already valid UTF-8 (with or without BOM) → no conversion needed
    try:
        raw.decode("utf-8-sig")
        return None
    except UnicodeDecodeError:
        pass

    text = None
    for encoding in ("cp949", "euc-kr"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            pass

    if text is None:
        return None  # let mpv try its own guess

    _, ext = os.path.splitext(subtitle_path)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=ext, delete=False)
    with handle:
        handle.write(text)
    return handle.name


def convert_smi_file_to_temp_srt(smi_path: str) -> str | None:
    text = _read_and_decode_subtitle(smi_path)
    srt_text = convert_smi_to_srt_text(text)
    if not srt_text.strip():
        return None
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".srt", delete=False)
    with handle:
        handle.write(srt_text)
    return handle.name
