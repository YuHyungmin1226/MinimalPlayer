from __future__ import annotations

import codecs
import os
import re
import tempfile
from collections.abc import Iterable
from html import unescape

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


def is_supported_subtitle(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUBTITLE_EXTENSIONS


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


_NATURAL_CHUNK_RE = re.compile(r"(\d+)")


def natural_sort_key(name: str) -> tuple:
    """파일명을 탐색기/Finder와 비슷한 자연 정렬 순서로 비교하기 위한 키.

    숫자 구간은 정수로 비교하므로 "track2 < track10"이 성립하고, 문자 구간은
    대소문자를 무시합니다. 마지막에 원본 이름을 붙여 키가 같은 파일
    (예: "a1.mp3" / "a01.mp3")도 결정적인 순서를 갖도록 합니다.
    """
    parts = _NATURAL_CHUNK_RE.split(name.casefold())
    key = [(0, int(part), "") if index % 2 else (1, 0, part) for index, part in enumerate(parts)]
    return (tuple(key), name)


def list_media_files_in_folder(dir_path: str) -> list[str]:
    """폴더 안의 지원 미디어 파일 경로를 자연 정렬 순서로 반환합니다.

    숨김 파일은 제외합니다. exFAT/FAT USB 드라이브의 macOS AppleDouble 잔재
    (`._track.mp3`)가 미디어 확장자를 갖고 있어 연속 재생을 막기 때문입니다.
    """
    dir_path = dir_path or "."
    names: list[str] = []
    try:
        with os.scandir(dir_path) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                if is_supported_media(entry.name):
                    names.append(entry.name)
    except OSError:
        return []
    names.sort(key=natural_sort_key)
    return [os.path.join(dir_path, name) for name in names]


def find_adjacent_media_in_folder(current_path: str) -> tuple[str | None, str | None]:
    """같은 폴더에서 파일명 순으로 (이전, 다음) 미디어 파일을 한 번에 찾습니다.

    폴더의 처음/끝에서는 해당 방향이 None입니다(순환하지 않음).
    현재 파일이 목록에 없으면(재생 중 삭제/이름 변경) 이름 순으로 그 앞뒤에
    오는 파일을 반환합니다.

    스캔이 한 번뿐이라, 버튼 활성화 상태를 갱신할 때 디스크를 두 번 읽지 않습니다.
    """
    dir_name, file_name = os.path.split(current_path)
    if not dir_name:
        dir_name = "."

    paths = list_media_files_in_folder(dir_name)
    if not paths:
        return (None, None)

    target = os.path.normcase(file_name)
    for index, path in enumerate(paths):
        if os.path.normcase(os.path.basename(path)) == target:
            return (
                paths[index - 1] if index > 0 else None,
                paths[index + 1] if index + 1 < len(paths) else None,
            )

    current_key = natural_sort_key(file_name)
    earlier = [path for path in paths if natural_sort_key(os.path.basename(path)) < current_key]
    later = [path for path in paths if natural_sort_key(os.path.basename(path)) > current_key]
    return (earlier[-1] if earlier else None, later[0] if later else None)


def find_next_media_in_folder(current_path: str) -> str | None:
    """같은 폴더에서 파일명 순으로 다음 순서의 미디어 파일을 찾습니다."""
    return find_adjacent_media_in_folder(current_path)[1]


def find_previous_media_in_folder(current_path: str) -> str | None:
    """같은 폴더에서 파일명 순으로 이전 순서의 미디어 파일을 찾습니다."""
    return find_adjacent_media_in_folder(current_path)[0]


def normalize_recent_files(paths: Iterable[str] | None, new_path: str | None = None, limit: int = 5) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    if new_path:
        result.append(new_path)
        seen.add(os.path.normcase(new_path))
    for path in paths or []:
        if path and os.path.normcase(path) not in seen and os.path.exists(path):
            result.append(path)
            seen.add(os.path.normcase(path))
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
    # Note: real-world SMI files often have extra attributes after Class=... (e.g.
    # <P Class=KRCC Style=xyz>), so we can't require '>' immediately after the value.
    kr_match = re.search(r"(?i)<P\s+Class\s*=\s*['\"]?(KRCC|KORCC)['\"]?(?=[\s>])[^>]*>", smi_part)
    if kr_match:
        start_idx = kr_match.end()
        next_p = re.search(r"(?i)<P\s+Class\s*=", smi_part[start_idx:])
        if next_p:
            return smi_part[start_idx : start_idx + next_p.start()]
        return smi_part[start_idx:]

    # 2. Fallback to the first class if Korean isn't found
    any_p = re.search(r"(?i)<P\s+Class\s*=\s*['\"]?([a-zA-Z0-9_-]+)['\"]?(?=[\s>])[^>]*>", smi_part)
    if any_p:
        start_idx = any_p.end()
        next_p = re.search(r"(?i)<P\s*Class\s*=", smi_part[start_idx:])
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
    matches = list(
        re.finditer(
            r"(?is)<sync\s+start\s*=\s*['\"]?(\d+)['\"]?(?=[\s>])[^>]*>",
            smi_text,
        )
    )
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
        end = start + 3000
        # Usually the next cue is already greater. Avoid slicing and scanning the
        # full remainder for every cue, which made large SMI files O(n²).
        for later_index in range(index + 1, len(starts)):
            candidate = starts[later_index]
            if candidate > start:
                end = candidate
                break
        if end <= start:
            end = start + 3000
        cues.append((start, end, text))
    blocks = []
    for number, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{number}\n{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _decode_legacy_subtitle(raw: bytes) -> str | None:
    """Decode non-UTF-8 subtitle bytes without guessing BOM-less UTF-16.

    Python can decode many even-length CP949 byte strings as arbitrary UTF-16
    code points. UTF-16/32 are therefore accepted only when their BOM identifies
    the byte order; BOM-less Korean subtitles fall through to CP949/EUC-KR.
    """
    bom_encodings = (
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    )
    for bom, encoding in bom_encodings:
        if raw.startswith(bom):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                return None

    for encoding in ("cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return None


def _read_and_decode_subtitle(path: str) -> str:
    """Read a subtitle file and decode with CJK encoding fallback."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    decoded = _decode_legacy_subtitle(raw)
    if decoded is not None:
        return decoded
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

    text = _decode_legacy_subtitle(raw)
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
