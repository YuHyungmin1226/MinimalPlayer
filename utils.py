import os
import re
import tempfile
from html import unescape
from collections.abc import Iterable

from constants import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, MEDIA_EXTENSIONS, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS


def format_time(seconds: float | int | None) -> str:
    seconds = max(0, int(seconds or 0))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours > 0 else f"{minutes:02d}:{secs:02d}"


def is_supported_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def is_supported_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


def is_supported_media(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in MEDIA_EXTENSIONS


def find_matching_subtitle(video_path: str) -> str | None:
    dir_name, file_name = os.path.split(video_path)
    if not dir_name:
        dir_name = "."
    base_name, _ = os.path.splitext(file_name)
    base_name_lower = base_name.lower()

    # ext → path 매핑 수집 후 SUBTITLE_EXTENSIONS 순서대로 우선 반환 (비결정적 scandir 순서 방지)
    matches: dict[str, str] = {}
    try:
        with os.scandir(dir_name) as entries:
            for entry in entries:
                if entry.is_file():
                    entry_base, entry_ext = os.path.splitext(entry.name)
                    if entry_base.lower() == base_name_lower and entry_ext.lower() in SUBTITLE_EXTENSIONS:
                        matches[entry_ext.lower()] = entry.path
    except Exception:
        pass

    for ext in SUBTITLE_EXTENSIONS:
        if ext in matches:
            return matches[ext]
    return None


def find_matching_image(media_path: str) -> str | None:
    """오디오 파일과 같은 폴더에서 커버아트 이미지를 탐색합니다.

    우선순위: 동일 파일명 → cover → folder → album → front → artwork
    """
    dir_name, file_name = os.path.split(media_path)
    if not dir_name:
        dir_name = "."
    base_name, _ = os.path.splitext(file_name)

    COVER_NAMES = [base_name.lower(), "cover", "folder", "album", "front", "artwork"]

    found: dict[str, str] = {}  # name_lower → path
    try:
        with os.scandir(dir_name) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                entry_base, entry_ext = os.path.splitext(entry.name)
                if entry_ext.lower() in IMAGE_EXTENSIONS:
                    key = entry_base.lower()
                    if key in COVER_NAMES and key not in found:
                        found[key] = entry.path
    except Exception:
        pass

    for name in COVER_NAMES:
        if name in found:
            return found[name]
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


def _filter_smi_by_lang(smi_part: str) -> str:
    # 1. Prioritize Korean subtitle classes (KRCC, KORCC)
    kr_match = re.search(r"(?i)<P\s+Class\s*=\s*['\"]?(KRCC|KORCC)['\"]?\s*>", smi_part)
    if kr_match:
        start_idx = kr_match.end()
        next_p = re.search(r"(?i)<P\s+Class\s*=", smi_part[start_idx:])
        if next_p:
            return smi_part[start_idx : start_idx + next_p.start()]
        return smi_part[start_idx:]

    # 2. Fallback to the first class if Korean isn't found
    any_p = re.search(r"(?i)<P\s+Class\s*=\s*['\"]?([a-zA-Z0-9_-]+)['\"]?\s*>", smi_part)
    if any_p:
        start_idx = any_p.end()
        next_p = re.search(r"(?i)<P\s+Class\s*=", smi_part[start_idx:])
        if next_p:
            return smi_part[start_idx : start_idx + next_p.start()]
        return smi_part[start_idx:]

    return smi_part


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
        body_part = _filter_smi_by_lang(smi_text[body_start:body_end])
        text = _clean_smi_text(body_part)
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
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8-sig", "utf-16", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def convert_subtitle_to_utf8(subtitle_path: str) -> str | None:
    """If subtitle file is not valid UTF-8, re-encode as a UTF-8 temp file.

    Returns the temp file path, or None if already valid UTF-8 or undecodable.
    """
    with open(subtitle_path, "rb") as f:
        raw = f.read()

    # Already valid UTF-8 (with or without BOM) → no conversion needed
    try:
        raw.decode("utf-8-sig")
        return None
    except UnicodeDecodeError:
        pass

    text = None
    for encoding in ("utf-16", "cp949", "euc-kr"):
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
