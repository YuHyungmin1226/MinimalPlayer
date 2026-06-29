APP_NAME = "MinimalPlayer"
APP_DISPLAY_NAME = "Minimal Portable Player"
ORG_NAME = "MinimalPlayer"

DEFAULT_VOLUME = 70

MPV_DLL_NAME = "mpv-1.dll"
MPV_DLL_URL = "https://github.com/YuHyungmin1226/MinimalPlayer/releases/download/v1.0/mpv-1.dll"
MPV_DLL_SHA256 = "ABF3D4B0871A77029183C101343E0DE901E07725337243FB4775B44C9E9D7749"

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".3gp", ".mpeg", ".mpg", ".ts", ".tp", ".asf", ".m4v",
}

AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a", ".opus",
    ".wma", ".aiff", ".aif", ".ape", ".alac",
}

MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

SUBTITLE_EXTENSIONS = [".srt", ".ass", ".vtt", ".smi"]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
RECENT_FILES_LIMIT = 5
RESUME_THRESHOLD_SECONDS = 10
