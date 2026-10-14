from __future__ import annotations

import time

import discord

COLOR_MAIN = discord.Color.blurple()
COLOR_ERROR = discord.Color.red()
COLOR_SUCCESS = discord.Color.green()
COLOR_WARN = discord.Color.orange()


def now() -> float:
    return time.monotonic()


def format_duration(seconds: float | int | None) -> str:
    try:
        total = int(float(seconds))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "bilinmiyor"
    if total <= 0:
        return "canlı"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def truncate(text: str, limit: int = 60) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def embed(
    title: str,
    description: str = "",
    *,
    color: discord.Color = COLOR_MAIN,
    url: str | None = None,
) -> discord.Embed:
    result = discord.Embed(title=title, description=description or discord.Embed.Empty, color=color)
    if url:
        result.url = url
    result.set_footer(text="!yardım | komut listesi")
    return result


def error_embed(message: str) -> discord.Embed:
    return embed("Hata", message, color=COLOR_ERROR)
