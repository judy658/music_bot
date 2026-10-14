from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value else default


def _int(name: str, default: int) -> int:
    try:
        return int(_str(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_str(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    value = _str(name, "").lower()
    if value in {"1", "true", "yes", "on", "evet"}:
        return True
    if value in {"0", "false", "no", "off", "hayir"}:
        return False
    return default


def find_ffmpeg() -> str:
    configured = _str("FFMPEG_PATH")
    if configured:
        return configured

    found = shutil.which("ffmpeg")
    if found:
        return found

    candidates: list[Path] = []
    local = os.getenv("LOCALAPPDATA", "")
    program_files = os.getenv("ProgramFiles", r"C:\Program Files")
    if local:
        winget = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if winget.is_dir():
            candidates.extend(sorted(winget.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe")))
            candidates.extend(sorted(winget.glob("BtbN.FFmpeg*/**/ffmpeg.exe")))
    candidates.append(Path(r"C:\ffmpeg\bin\ffmpeg.exe"))
    candidates.append(Path(program_files) / "ffmpeg" / "bin" / "ffmpeg.exe")

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


DISCORD_TOKEN = _str("DISCORD_TOKEN")
PREFIX = _str("PREFIX", "!")

FFMPEG_PATH = find_ffmpeg()
YTDLP_EXE = shutil.which("yt-dlp") or ""

COOKIES_FILE = _str("COOKIES_FILE")
PROXY = _str("PROXY")
PLAYER_CLIENTS = [c.strip() for c in _str("PLAYER_CLIENTS").split(",") if c.strip()]

STREAM_FORMAT = _str("STREAM_FORMAT", "bestaudio/best")
FALLBACK_FORMAT = _str("FALLBACK_FORMAT", "worstaudio/worst")
DOWNLOAD_FORMAT = _str("DOWNLOAD_FORMAT", "bestaudio/best")

MAX_PLAYLIST_ITEMS = _int("MAX_PLAYLIST_ITEMS", 50)
MAX_SEARCH_RESULTS = _int("MAX_SEARCH_RESULTS", 5)
SEARCH_TTL_SECONDS = _int("SEARCH_TTL_SECONDS", 180)

MAX_DURATION_MINUTES = _int("MAX_DURATION_MINUTES", 180)
MIN_DURATION_SECONDS = _int("MIN_DURATION_SECONDS", 30)
ALLOW_SHORT = _bool("ALLOW_SHORT", False)
ALLOW_LIVE = _bool("ALLOW_LIVE", True)

VOLUME_DEFAULT = _float("VOLUME_DEFAULT", 0.45)
VOLUME_MAX = _float("VOLUME_MAX", 2.0)

LOOP_DEFAULT = _bool("LOOP_DEFAULT", False)
IDLE_TIMEOUT_SECONDS = _int("IDLE_TIMEOUT_SECONDS", 900)

NORMALIZE_AUDIO = _bool("NORMALIZE_AUDIO", False)
AUDIO_FILTER = _str("AUDIO_FILTER")

CACHE_DIR = Path(_str("CACHE_DIR", str(BASE_DIR / "cache" / "downloads")))
YTDLP_CACHE_DIR = BASE_DIR / "cache" / "yt-dlp"
LOG_DIR = BASE_DIR / "logs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
YTDLP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
