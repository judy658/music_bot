from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

import config
import ytdl
from utils import COLOR_MAIN, COLOR_WARN, embed, format_duration, now, truncate

log = logging.getLogger("music_bot.music")

PLAYBACK_POLL_INTERVAL = 0.25
MAX_RESUMES = 3


class MusicError(Exception):
    def __init__(self, message: str, *, title: str = "Müzik Hatası") -> None:
        super().__init__(message)
        self.message = message
        self.title = title


class QueueEmpty(MusicError):
    def __init__(self) -> None:
        super().__init__("Sırada başka bir şarkı yok.")


class MusicQueue:
    def __init__(self) -> None:
        self._items: deque[dict[str, Any]] = deque()
        self._event = asyncio.Event()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def is_empty(self) -> bool:
        return not self._items

    def put(self, item: dict[str, Any]) -> None:
        self._items.append(item)
        self._event.set()

    def get_nowait(self) -> dict[str, Any]:
        if not self._items:
            raise QueueEmpty()
        item = self._items.popleft()
        if not self._items:
            self._event.clear()
        return item

    async def get(self, timeout: float) -> dict[str, Any]:
        if not self._items:
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
            except (asyncio.TimeoutError, TimeoutError):
                raise QueueEmpty()
        return self.get_nowait()

    def clear(self) -> None:
        self._items.clear()
        self._event.clear()

    def as_list(self) -> list[dict[str, Any]]:
        return list(self._items)

    def shuffle(self) -> None:
        random.shuffle(self._items)

    def remove_at(self, index: int) -> dict[str, Any]:
        if index < 0 or index >= len(self._items):
            raise MusicError("Sıradaki bu sıra numarası yok.")
        item = self._items[index]
        del self._items[index]
        if not self._items:
            self._event.clear()
        return item


@dataclass
class Song:
    track: dict[str, Any]
    requested_by: discord.abc.User
    source: Any = None
    temp_file: Path | None = None
    used_file: bool = False

    @property
    def title(self) -> str:
        return self.track.get("title") or "bilinmeyen"

    @property
    def webpage_url(self) -> str:
        return self.track.get("webpage_url") or ""

    @property
    def is_live(self) -> bool:
        return bool(self.track.get("is_live"))

    @property
    def duration_text(self) -> str:
        return "canlı" if self.is_live else format_duration(self.track.get("duration"))

    def embed(self) -> discord.Embed:
        result = discord.Embed(
            title=truncate(self.title, 60),
            color=COLOR_MAIN,
            url=self.webpage_url or None,
        )
        result.add_field(name="Süre", value=self.duration_text, inline=True)
        result.add_field(name="Kanal", value=truncate(self.track.get("uploader") or "bilinmiyor", 40), inline=True)
        result.add_field(name="İsteyen", value=self.requested_by.mention, inline=True)
        if self.track.get("thumbnail"):
            result.set_thumbnail(url=self.track["thumbnail"])
        return result


@dataclass
class GuildState:
    guild_id: int
    volume: float = config.VOLUME_DEFAULT
    loop: bool = config.LOOP_DEFAULT
    repeat_queue: bool = False
    queue: MusicQueue = field(default_factory=MusicQueue)
    current: Song | None = None
    played: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))
    repeat_snapshot: list[dict[str, Any]] = field(default_factory=list)
    text_channel: Any = None
    task: asyncio.Task | None = None
    search_results: list[dict[str, Any]] = field(default_factory=list)
    search_expires: float = 0.0
    opened_at: float = field(default_factory=now)
    paused_at: float = 0.0

    @property
    def idle_for(self) -> float:
        return now() - self.opened_at

    @property
    def elapsed(self) -> float:
        """Su anki sarkida gecen gercek sure (duraklatma suresi haric)."""
        if self.paused_at:
            return self.paused_at - self.opened_at
        return now() - self.opened_at

    def add_search_results(self, tracks: list[dict[str, Any]]) -> None:
        self.search_results = tracks
        self.search_expires = now() + config.SEARCH_TTL_SECONDS

    def get_search_results(self) -> list[dict[str, Any]]:
        if not self.search_results or now() > self.search_expires:
            self.search_results = []
            return []
        return self.search_results

    def clear_playback(self) -> None:
        self.current = None
        self.queue.clear()

    def reset(self) -> None:
        self.clear_playback()
        self.played.clear()
        self.repeat_snapshot = []
        self.search_results = []
        self.loop = config.LOOP_DEFAULT
        self.repeat_queue = False


class Music:
    def __init__(self) -> None:
        self.bot: commands.Bot | None = None
        self._states: dict[int, GuildState] = {}

    def get_state(self, guild: discord.Guild, *, create: bool = True) -> GuildState | None:
        state = self._states.get(guild.id)
        if state is None and create:
            state = GuildState(guild_id=guild.id)
            self._states[guild.id] = state
        return state

    def all_states(self) -> list[GuildState]:
        return list(self._states.values())

    async def notify(self, guild: discord.Guild, state: GuildState, embed: discord.Embed) -> None:
        channel = state.text_channel
        if channel is None:
            channel = guild.system_channel
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.debug("Bildirim gönderilemedi: %s", exc)

    async def ensure_voice_client(self, ctx: commands.Context) -> discord.VoiceProtocol:
        if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None or ctx.author.voice.channel is None:
            raise MusicError("Bir ses kanalına katılmalısın.", title="Ses Kanalı Gerekli")

        target = ctx.author.voice.channel
        guild = ctx.guild
        assert guild is not None
        state = self.get_state(guild)

        permissions = target.permissions_for(guild.me)
        if not permissions.connect:
            raise MusicError(f"**{target.name}** kanalına bağlanma iznim yok.")
        if not permissions.speak:
            raise MusicError(f"**{target.name}** kanalında konuşma iznim yok.")

        client = guild.voice_client
        if client is None:
            try:
                client = await target.connect(self_deaf=False)
            except discord.Forbidden as exc:
                raise MusicError(
                    "Kanala bağlanılamadı. Bot için **Bağlan**, **Konuş** ve **Etkinlik Kullan** izinleri gerekli."
                ) from exc
            except discord.ClientException as exc:
                raise MusicError(f"Kanala bağlanılamadı: {exc}") from exc
        elif client.channel.id != target.id:
            try:
                await client.move_to(target)
            except discord.Forbidden as exc:
                raise MusicError("Kanala taşınamadı, **Üyeleri Taşı** izni gerekli.") from exc
            except discord.ClientException as exc:
                raise MusicError(f"Kanala taşınamadı: {exc}") from exc

        state.opened_at = now()
        return client

    def start_playback(self, guild: discord.Guild, state: GuildState) -> None:
        if state.task and not state.task.done():
            return
        state.task = asyncio.create_task(self._playback_loop(guild, state), name=f"music-{guild.id}")

    def enqueue(
        self,
        guild: discord.Guild,
        state: GuildState,
        tracks: list[dict[str, Any]],
        requested_by: discord.abc.User,
    ) -> int:
        existing = {item["track"].get("id") for item in state.queue.as_list()}
        if state.current is not None:
            existing.add(state.current.track.get("id"))

        fresh: list[dict[str, Any]] = []
        for track in tracks:
            if track.get("id") in existing:
                continue
            existing.add(track.get("id"))
            fresh.append(track)

        if not fresh:
            return 0

        if state.queue.is_empty and state.current is None and state.repeat_queue:
            state.repeat_snapshot = list(fresh)

        for track in fresh:
            state.queue.put({"track": track, "requested_by": requested_by})

        self.start_playback(guild, state)
        return len(fresh)

    async def _playback_loop(self, guild: discord.Guild, state: GuildState) -> None:
        try:
            while True:
                try:
                    data = await state.queue.get(timeout=config.IDLE_TIMEOUT_SECONDS)
                except QueueEmpty:
                    await self._finish_session(guild, state)
                    return

                song = Song(track=data["track"], requested_by=data["requested_by"])
                state.current = song

                try:
                    await self._play_song(guild, state, song)
                except ytdl.YTDLException as exc:
                    state.current = None
                    self._cleanup_song(song)
                    if not exc.skippable:
                        await self.notify(
                            guild,
                            state,
                            embed(f"Çalınamadı: {truncate(song.title, 50)}", exc.message, color=COLOR_WARN),
                        )
                    log.info("Atlandi: %s (%s)", song.title, exc.message)
                    continue

                if await self._handle_after_song(guild, state, song):
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Oynatma döngüsü çöktü")
            state.current = None
            await self.notify(guild, state, embed("Hata", "Oynatma sırasında beklenmeyen bir hata oluştu.", color=COLOR_WARN))

    async def _play_song(
        self,
        guild: discord.Guild,
        state: GuildState,
        song: Song,
        *,
        seek: float = 0.0,
        resumes: int = 0,
    ) -> None:
        client = guild.voice_client
        if client is None:
            raise MusicError("Ses kanalına bağlı değilim.", title="Bağlantı Koptu")

        source, temp_file, used_file = await ytdl.create_source(
            song.track,
            volume=state.volume,
            normalize=config.NORMALIZE_AUDIO,
            seek=seek,
        )
        song.source = source
        song.temp_file = temp_file
        song.used_file = used_file

        loop = asyncio.get_running_loop()
        prime = getattr(source, "prime", None)
        if callable(prime):
            buffered = await loop.run_in_executor(None, prime)
            log.info("Ses tamponlandi: %.1f sn", (buffered or 0) * 0.02)

        if client.is_playing() or client.is_paused():
            client.stop()

        finished = asyncio.Event()
        errors: list[BaseException] = []

        def _after(error: BaseException | None) -> None:
            if error is not None:
                errors.append(error)
            try:
                loop.call_soon_threadsafe(finished.set)
            except RuntimeError:
                pass

        try:
            client.play(source, after=_after)
        except (discord.ClientException, ValueError) as exc:
            raise ytdl.YTDLException(
                "Ses oynatılamadı, şarkıyı tekrar kuyruğa al.",
                skippable=True,
            ) from exc

        if resumes == 0:
            state.played.append(song.track)
        state.opened_at = now() - seek
        state.paused_at = 0.0

        channel = getattr(getattr(client, "channel", None), "name", "?")
        protocol = getattr(client, "_connection", None)
        log.info(
            "Oynatiliyor: %s | kanal=#%s | ses=%%%d | dosya=%s | konum=%.0fs%s | bot_sessiz=%s bot_sagir=%s",
            song.title,
            channel,
            int(state.volume * 100),
            "evet" if used_file else "akış",
            seek,
            f" (devam #{resumes})" if resumes else "",
            getattr(protocol, "self_mute", False),
            getattr(protocol, "self_deaf", False),
        )

        if resumes == 0:
            await self.notify(guild, state, song.embed())

        await finished.wait()

        position = state.elapsed
        duration = song.track.get("duration")
        if errors:
            log.info("Ses akisi kesildi (%s): %s", song.title, errors[0])

        source_ended = source.ended_with_network_error() if hasattr(source, "ended_with_network_error") else False
        if (
            not used_file
            and duration
            and resumes < MAX_RESUMES
            and 15.0 <= position < duration - 5.0
            and position - seek >= 10.0
            and (errors or source_ended)
        ):
            log.warning(
                "Ses akisi erken bitti (%s): %.0f / %.0f sn; kaldigi yerden devam ediliyor (deneme %d/%d).",
                song.title,
                position,
                duration,
                resumes + 1,
                MAX_RESUMES,
            )
            await self._play_song(guild, state, song, seek=position, resumes=resumes + 1)
            return

        if errors:
            raise ytdl.YTDLException("Ses akışı kesildi, sonraki şarkıya geçiliyor.", skippable=True)

    def _cleanup_song(self, song: Song | None) -> None:
        if song is None:
            return
        song.source = None
        if song.temp_file and song.temp_file.exists():
            try:
                song.temp_file.unlink()
            except OSError:
                pass
            song.temp_file = None

    async def _handle_after_song(self, guild: discord.Guild, state: GuildState, song: Song) -> bool:
        self._cleanup_song(song)
        state.current = None
        state.opened_at = now()
        state.paused_at = 0.0

        client = guild.voice_client
        if client is None:
            state.reset()
            await self.notify(
                guild,
                state,
                embed("Bağlantı Kesildi", "Ses kanalından çıkarıldım, oynatma durduruldu.", color=COLOR_WARN),
            )
            return True

        if state.loop:
            state.queue.put({"track": song.track, "requested_by": song.requested_by})
            return False

        if state.queue.is_empty and state.repeat_queue:
            snapshot = state.repeat_snapshot or list(state.played)
            if snapshot:
                state.repeat_snapshot = snapshot
                for track in snapshot:
                    state.queue.put({"track": track, "requested_by": song.requested_by})

        return False

    async def _finish_session(self, guild: discord.Guild, state: GuildState) -> None:
        self._cleanup_song(state.current)
        state.clear_playback()
        client = guild.voice_client
        if client is not None:
            try:
                await client.disconnect(force=True)
            except (discord.HTTPException, asyncio.TimeoutError):
                log.debug("Ses kanalından ayrılınamadı (%s)", guild.id)
        await self.notify(guild, state, embed("Sıra bitti", "Oynatma kuyruğu tamamlandı, kanaldan ayrılıyorum."))

    async def pause(self, guild: discord.Guild, state: GuildState) -> None:
        client = guild.voice_client
        if client is None or not client.is_playing():
            raise MusicError("Şu an çalan bir şey yok.")
        client.pause()
        state.paused_at = now()

    async def resume(self, guild: discord.Guild, state: GuildState) -> None:
        client = guild.voice_client
        if client is None or not client.is_paused():
            raise MusicError("Duraklatılmış bir şey yok.")
        client.resume()
        if state.paused_at:
            state.opened_at += now() - state.paused_at
            state.paused_at = 0.0

    async def stop(self, guild: discord.Guild, state: GuildState, *, disconnect: bool = True) -> None:
        self._cleanup_song(state.current)
        state.reset()

        task = state.task
        state.task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        client = guild.voice_client
        if client is not None:
            try:
                if disconnect:
                    await client.disconnect(force=True)
                else:
                    client.stop()
            except (discord.HTTPException, asyncio.TimeoutError) as exc:
                log.debug("Durdurulamadı: %s", exc)

    async def skip(self, guild: discord.Guild, state: GuildState) -> bool:
        client = guild.voice_client
        if client is None or not (client.is_playing() or client.is_paused()):
            if state.queue.is_empty:
                raise MusicError("Atlanacak çalışan bir şey yok.")
            return True

        client.stop()
        return False

    async def set_volume(self, guild: discord.Guild, state: GuildState, volume: float) -> tuple[float, bool]:
        """Ses seviyesini ayarlar, canli sariki yerinde uygulamaya calisir.

        Donus: (normalize edilmis ses, canli olarak uygulandi mi)
        """
        volume = max(0.0, min(volume, config.VOLUME_MAX))
        previous = state.volume
        state.volume = volume

        client = guild.voice_client
        current = state.current
        source = current.source if current is not None else None
        player = getattr(client, "player", None) if client is not None else None
        if source is None or player is None or not (client.is_playing() or client.is_paused()):
            return volume, False
        if abs(previous - volume) < 0.001:
            return volume, False

        if current.is_live:
            return volume, False

        position = state.elapsed
        if position < 1.0:
            return volume, False

        try:
            new_source = source.clone(volume=volume, seek=position)
        except (discord.ClientException, OSError) as exc:
            log.warning("Yeni ses kaynagi olusturulamadi: %s", exc)
            return volume, False

        was_paused = client.is_paused()
        prime = getattr(new_source, "prime", None)
        if callable(prime):
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, prime)
            except Exception:
                log.warning("Yeni kaynak tamponlanamadi", exc_info=True)
        try:
            player.set_source(new_source)
        except Exception:
            new_source.cleanup()
            log.exception("Ses kaynagi degistirilemedi")
            return volume, False

        source.retire()
        current.source = new_source
        if was_paused:
            player.pause(update_speaking=False)
        self._schedule_cleanup(source)
        log.info("Ses seviyesi canli uygulandi: %%%d (konum %.1fs)", int(volume * 100), position)
        return volume, True

    def _schedule_cleanup(self, source: Any, delay: float = 1.0) -> None:
        """Emekli kaynagin ffmpeg surecini, oynatici yeni kaynaga gectikten sonra kapatir."""
        try:
            asyncio.get_running_loop().call_later(delay, source.cleanup)
        except RuntimeError:
            source.cleanup()

    async def leave_all(self) -> None:
        for state in self.all_states():
            guild = self._guild_for(state)
            if guild is None:
                continue
            try:
                await self.stop(guild, state)
            except Exception:
                log.exception("Sunucu temizlenemedi: %s", guild.id)

    def _guild_for(self, state: GuildState) -> discord.Guild | None:
        return self.bot.get_guild(state.guild_id) if self.bot else None
