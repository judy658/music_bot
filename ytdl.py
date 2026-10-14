from __future__ import annotations

import asyncio
import functools
import logging
import re
from pathlib import Path
from typing import Any, Iterable

import discord
import yt_dlp
from yt_dlp.utils import DownloadError

import config
from audio_source import MusicAudioSource

log = logging.getLogger("music_bot.ytdl")

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|"
    r"music\.youtube\.com/watch\?v=|youtube\.com/live/|youtube\.com/playlist\?list=)",
    re.IGNORECASE,
)

AUDIO_EXTENSIONS = (".opus", ".webm", ".m4a", ".mp3", ".ogg", ".wav")


class YTDLException(Exception):
    def __init__(self, message: str, *, skippable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.skippable = skippable


def is_url(query: str) -> bool:
    return bool(URL_PATTERN.search(query.strip()))


def _friendly_error(exc: DownloadError | Exception) -> YTDLException:
    raw = str(getattr(exc, "msg", None) or exc)
    text = raw.lower()

    rules: tuple[tuple[tuple[str, ...], str, bool], ...] = (
        (
            ("sign in to confirm your age", "age-restricted", "age restricted"),
            "Bu video yaş sınırlı. Bot için YouTube çerezleri ayarlanmalı (COOKIES_FILE).",
            True,
        ),
        (
            ("confirm you're not a bot", "sign in to confirm you’re not a bot", "not a bot"),
            "YouTube bot doğrulaması istedi. .env içindeki PLAYER_CLIENTS değerini değiştir.",
            True,
        ),
        (
            ("private video", "this video is private"),
            "Bu video gizli, bot erişemiyor.",
            True,
        ),
        (
            ("members-only", "join this channel"),
            "Bu video sadece üyelere açık.",
            True,
        ),
        (
            ("video unavailable", "this video is unavailable", "has been removed", "removed by the uploader"),
            "Video kaldırılmış veya kullanılamıyor.",
            True,
        ),
        (
            ("not available in your country", "blocked it in your country", "geo restricted"),
            "Bu video bulunduğun ülkede engelli.",
            True,
        ),
        (
            ("requested format is not available", "no video formats found"),
            "Ses akışı alınamadı, video YouTube tarafından kısıtlanmış olabilir.",
            True,
        ),
        (
            ("unable to download webpage", "unable to extract", "http error 429", "too many requests"),
            "YouTube'a ulaşılamadı. Birkaç saniye sonra tekrar dene.",
            True,
        ),
    )

    for needles, message, skippable in rules:
        if any(needle in text for needle in needles):
            return YTDLException(message, skippable=skippable)

    return YTDLException(f"Ses alınamadı: {raw[:180]}", skippable=True)


def _base_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "ignoreerrors": False,
        "noplaylist": False,
        "cachedir": str(config.YTDLP_CACHE_DIR),
        "socket_timeout": 20,
        "retries": 5,
        "extractor_retries": 3,
        "default_search": "ytsearch",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
        },
    }
    if config.COOKIES_FILE:
        opts["cookiefile"] = config.COOKIES_FILE
    if config.PROXY:
        opts["proxy"] = config.PROXY
    if config.PLAYER_CLIENTS:
        opts["extractor_args"] = {"youtube": {"player_client": config.PLAYER_CLIENTS}}
    return opts


def _stream_opts() -> dict[str, Any]:
    opts = _base_opts()
    opts["format"] = config.STREAM_FORMAT
    return opts


def _download_opts() -> dict[str, Any]:
    opts = _base_opts()
    opts["format"] = config.DOWNLOAD_FORMAT
    opts["outtmpl"] = str(config.CACHE_DIR / "%(id)s.%(ext)s")
    opts["postprocessors"] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": "128",
        }
    ]
    return opts


def _extract_sync(url: str, opts: dict[str, Any]) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _download_sync(url: str, opts: dict[str, Any]) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=True) or {}


async def _in_executor(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args))


async def extract_info(url: str, *, opts: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return await _in_executor(_extract_sync, url, opts or _stream_opts())
    except DownloadError as exc:
        if opts is None and _should_retry_with_fallback_format(exc):
            try:
                return await _in_executor(_extract_sync, url, _fallback_opts())
            except Exception as retry_exc:
                raise _friendly_error(retry_exc) from retry_exc
        raise _friendly_error(exc) from exc
    except Exception as exc:
        raise _friendly_error(exc) from exc


_FORMAT_ERROR_MARKERS = (
    "requested format is not available",
    "no video formats found",
    "only images are available",
    "unable to extract",
    "fragment",
    "signature",
)


def _should_retry_with_fallback_format(exc: DownloadError) -> bool:
    """Format/erisim kaynakli hatalarda daha yedek bir format ile tekrar dener."""
    if not config.FALLBACK_FORMAT or config.FALLBACK_FORMAT == config.STREAM_FORMAT:
        return False
    text = str(getattr(exc, "msg", None) or exc).lower()
    if not any(marker in text for marker in _FORMAT_ERROR_MARKERS):
        return False
    log.info("Format erisimi basarisiz, yedek format deneniyor: %s", config.FALLBACK_FORMAT)
    return True


def _fallback_opts() -> dict[str, Any]:
    opts = _base_opts()
    opts["format"] = config.FALLBACK_FORMAT
    return opts


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    webpage_url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or ""
    if not webpage_url:
        video_id = entry.get("id")
        webpage_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""

    live = bool(entry.get("is_live"))
    duration = entry.get("duration")

    return {
        "id": entry.get("id") or webpage_url,
        "title": entry.get("title") or "bilinmeyen",
        "webpage_url": webpage_url,
        "duration": None if live else duration,
        "uploader": entry.get("uploader") or entry.get("channel") or entry.get("uploader_id") or "bilinmiyor",
        "thumbnail": entry.get("thumbnail"),
        "is_live": live,
    }


def _passes_filters(track: dict[str, Any]) -> bool:
    if track["is_live"]:
        return config.ALLOW_LIVE

    duration = track.get("duration")
    if duration is None:
        return True

    if duration < config.MIN_DURATION_SECONDS and not config.ALLOW_SHORT:
        return False
    if config.MAX_DURATION_MINUTES > 0 and duration > config.MAX_DURATION_MINUTES * 60:
        return False
    return True


def _walk(entries: Iterable[dict[str, Any] | None], depth: int) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    if depth > 3:
        return tracks

    for entry in entries:
        if entry is None:
            continue
        if entry.get("_type") in {"playlist", "multi_video"} and entry.get("entries"):
            tracks.extend(_walk(entry["entries"], depth + 1))
            continue
        track = normalize_entry(entry)
        if track["webpage_url"] and _passes_filters(track):
            tracks.append(track)
    return tracks


async def resolve(query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        raise YTDLException("Ne çalınacağını yazmadın.")

    max_items = limit or config.MAX_PLAYLIST_ITEMS
    if is_url(query):
        target = query
    else:
        target = f"ytsearch1:{query}"

    opts = _stream_opts()
    opts["playlistend"] = max_items

    info = await extract_info(target, opts=opts)

    entries = info.get("entries")
    if entries is None:
        entries = [info]
    if info.get("_type") in {"playlist", "multi_video"} and not entries:
        raise YTDLException("Bu oynatma listesinde oynatılabilir şarkı bulunamadı.", skippable=True)

    tracks = _walk(entries, 0)
    if not tracks:
        raise YTDLException("Sonuç bulunamadı. Farklı bir arama dene.", skippable=True)
    return tracks[:max_items]


async def search(query: str, *, count: int | None = None) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        raise YTDLException("Ne aranacak yazmadın.")

    total = count or config.MAX_SEARCH_RESULTS
    opts = _stream_opts()
    opts["noplaylist"] = True
    info = await extract_info(f"ytsearch{total}:{query}", opts=opts)
    entries = [normalize_entry(e) for e in (info.get("entries") or []) if e]
    return [track for track in entries if track["webpage_url"]][:total]


def _pick_stream_url(info: dict[str, Any]) -> str:
    formats = info.get("formats") or []
    audio = [f for f in formats if f.get("url") and f.get("acodec") != "none"]
    if not audio:
        if info.get("url"):
            return str(info["url"])
        raise YTDLException("Ses akışı bulunamadı.", skippable=True)

    def score(fmt: dict[str, Any]) -> tuple:
        vcodec = fmt.get("vcodec") in {"none", None}
        abr = fmt.get("abr") or fmt.get("tbr") or 0
        return (1 if vcodec else 0, abr)

    best = max(audio, key=score)
    if not best.get("url"):
        raise YTDLException("Ses bağlantısı alınamadı.", skippable=True)
    return str(best["url"])


def _audio_filters(normalize: bool) -> list[str]:
    filters: list[str] = []
    if config.AUDIO_FILTER:
        filters.append(config.AUDIO_FILTER)
    if normalize or config.NORMALIZE_AUDIO:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    return filters


def _ffmpeg_kwargs(source: Any, *, volume: float, normalize: bool, seek: float = 0.0) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"volume": volume}
    filters = _audio_filters(normalize)
    if filters:
        kwargs["filters"] = filters
    if config.FFMPEG_PATH:
        kwargs["executable"] = config.FFMPEG_PATH
    if seek > 0:
        kwargs["seek"] = seek
    return {"source": source, **kwargs}


def _build_source(source: Any, *, volume: float, normalize: bool, seek: float = 0.0) -> MusicAudioSource:
    return MusicAudioSource(**_ffmpeg_kwargs(source, volume=volume, normalize=normalize, seek=seek))


async def create_stream_source(track: dict[str, Any], *, volume: float, normalize: bool = False, seek: float = 0.0):
    info = await extract_info(track["webpage_url"])
    url = _pick_stream_url(info)
    try:
        return _build_source(url, volume=volume, normalize=normalize, seek=seek), None
    except (discord.ClientException, OSError) as exc:
        log.warning("Ses kaynağı oluşturulamadı: %s", exc)
        raise YTDLException("Ses akışı başlatılamadı (ffmpeg hatası).", skippable=True) from exc


def _find_downloaded(video_id: str) -> Path | None:
    for extension in AUDIO_EXTENSIONS:
        candidate = config.CACHE_DIR / f"{video_id}{extension}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


async def create_file_source(track: dict[str, Any], *, volume: float, normalize: bool = False, seek: float = 0.0):
    video_id = track["id"]
    path = _find_downloaded(str(video_id))

    if path is None:
        try:
            await _in_executor(_download_sync, track["webpage_url"], _download_opts())
        except DownloadError as exc:
            raise _friendly_error(exc) from exc
        except Exception as exc:
            raise _friendly_error(exc) from exc
        path = _find_downloaded(str(video_id))

    if path is None:
        raise YTDLException("Ses dosyası indirilemedi.", skippable=True)

    try:
        return _build_source(f"file://{path.as_posix()}", volume=volume, normalize=normalize, seek=seek), path
    except (discord.ClientException, OSError) as exc:
        log.warning("Ses dosyası oynatılamadı: %s", exc)
        raise YTDLException("Ses dosyası oynatılamadı (ffmpeg hatası).", skippable=True) from exc


async def create_source(track: dict[str, Any], *, volume: float, normalize: bool = False, seek: float = 0.0):
    if track.get("is_live"):
        try:
            source, path = await create_stream_source(track, volume=volume, normalize=normalize, seek=seek)
            return source, path, False
        except YTDLException as exc:
            log.info("Canlı yayın akışı başarısız, indiriliyor: %s", exc.message)

    try:
        source, path = await create_stream_source(track, volume=volume, normalize=normalize, seek=seek)
        return source, path, False
    except YTDLException:
        source, path = await create_file_source(track, volume=volume, normalize=normalize, seek=seek)
        return source, path, True
