from __future__ import annotations

import logging

import discord
import yt_dlp
from discord.ext import commands

import config
import ytdl
from music import Music, MusicError
from utils import COLOR_SUCCESS, COLOR_WARN, embed, format_duration, now, truncate

log = logging.getLogger("music_bot.commands")


class MusicCog(commands.Cog, name="Müzik"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.music: Music = bot.music

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        original = error.original if isinstance(error, commands.CommandError) else error
        if isinstance(original, MusicError):
            await ctx.send(embed=embed(original.title, original.message, color=COLOR_WARN))
            return
        if isinstance(original, ytdl.YTDLException):
            await ctx.send(embed=embed("YouTube Hatası", original.message, color=COLOR_WARN))
            return
        if isinstance(original, commands.CommandInvokeError):
            raise original
        log.exception("Komut hatası: %s", ctx.command.qualified_name if ctx.command else "?")
        await ctx.send(embed=embed("Beklenmeyen Hata", "Komut çalıştırılırken bir sorun oluştu, loglar kontrol ediliyor.", color=COLOR_WARN))

    def _state(self, ctx: commands.Context):
        return self.music.get_state(ctx.guild)

    @commands.command(name="play", aliases=["çal", "cal", "p"], help="Şarkı adı veya YouTube linki ile çalar.")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        state = self._state(ctx)
        state.text_channel = ctx.channel

        async with ctx.typing():
            tracks = await ytdl.resolve(query)

        await self.music.ensure_voice_client(ctx)

        was_playing = state.current is not None
        queued_before = len(state.queue)
        added = self.music.enqueue(ctx.guild, state, tracks, ctx.author)

        if added == 0:
            await ctx.send(embed=embed("Sırada Zaten Var", "Bu şarkı zaten kuyrukta.", color=COLOR_WARN))
            return

        state.opened_at = now()

        if added > 1:
            summary = f"**{added}** şarkı kuyruğa eklendi."
        elif was_playing:
            summary = f"Kuyruğa eklendi (kuyrukta **{queued_before + added}** şarkı)."
        else:
            summary = "Çalınıyor..."

        result = embed(
            truncate(tracks[0].get("title") or "Bilinmeyen", 60),
            summary,
            color=COLOR_SUCCESS,
            url=tracks[0].get("webpage_url"),
        )
        result.add_field(
            name="Süre",
            value="canlı" if tracks[0].get("is_live") else format_duration(tracks[0].get("duration")),
            inline=True,
        )
        result.add_field(name="Kanal", value=truncate(tracks[0].get("uploader") or "bilinmiyor", 40), inline=True)
        if tracks[0].get("thumbnail"):
            result.set_thumbnail(url=tracks[0]["thumbnail"])
        await ctx.send(embed=result)

    @commands.command(name="ara", aliases=["search"], help="YouTube'da arama yapar, sonuçları listeler.")
    async def ara(self, ctx: commands.Context, *, query: str) -> None:
        state = self._state(ctx)
        async with ctx.typing():
            results = await ytdl.search(query)

        if not results:
            await ctx.send(embed=embed("Sonuç Yok", "Aramanla eşleşen şarkı bulunamadı.", color=COLOR_WARN))
            return

        state.add_search_results(results)
        listing = "\n".join(
            f"`{index}.` **{truncate(track['title'], 55)}** — {truncate(track.get('uploader') or '', 25)} "
            f"· {format_duration(track.get('duration'))}"
            for index, track in enumerate(results, start=1)
        )
        result = embed(
            f"Arama: {truncate(query, 45)}",
            f"{listing}\n\nÇalmak için `{config.PREFIX}seç <numara>` yaz.",
            url=results[0]["webpage_url"],
        )
        await ctx.send(embed=result)

    @commands.command(name="seç", aliases=["sec", "pick"], help="Son arama sonucundan birini çalar.")
    async def sec(self, ctx: commands.Context, number: int) -> None:
        state = self._state(ctx)
        results = state.get_search_results()
        if not results:
            raise MusicError(
                f"Önce `{config.PREFIX}ara <şarkı adı>` ile arama yap.",
                title="Arama Sonucu Yok",
            )
        if not 1 <= number <= len(results):
            raise MusicError(f"Numara 1 ile {len(results)} arasında olmalı.")

        track = results[number - 1]
        await ctx.invoke(self.play, query=track["webpage_url"])

    @commands.command(name="pause", aliases=["duraklat", "bekle"], help="Çalan şarkıyı duraklatır.")
    async def pause(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        await self.music.pause(ctx.guild, state)
        await ctx.send(embed=embed("Duraklatıldı", "Devam etmek için `!devam`.", color=COLOR_WARN))

    @commands.command(name="resume", aliases=["devam", "devamet", "continue"], help="Duraklatılan şarkıyı sürdürür.")
    async def resume(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        await self.music.resume(ctx.guild, state)
        await ctx.send(embed=embed("Devam ediyor", "Oynatma sürdürüldü.", color=COLOR_SUCCESS))

    @commands.command(name="stop", aliases=["dur", "kapat"], help="Oynatmayı durdurur ve kanaldan ayrılır.")
    async def stop(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        await self.music.stop(ctx.guild, state)
        await ctx.send(embed=embed("Durduruldu", "Oynatma durduruldu ve kanaldan ayrıldım.", color=COLOR_WARN))

    @commands.command(name="skip", aliases=["atla", "s", "next"], help="Şu an çalan şarkıyı atlar.")
    async def skip(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        skipping = await self.music.skip(ctx.guild, state)
        if not skipping:
            await ctx.send(embed=embed("Atlandı", "Sıradaki şarkıya geçildi.", color=COLOR_SUCCESS))
        else:
            self.music.start_playback(ctx.guild, state)

    @commands.command(name="queue", aliases=["sıra", "sira", "q", "liste"], help="Kuyruğu gösterir.")
    async def queue(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        if state.current is None and state.queue.is_empty:
            raise MusicError("Kuyruk boş.", title="Sıra Boş")

        result = embed("Kuyruk")
        if state.current:
            result.add_field(
                name="Şu an çalıyor",
                value=f"[{truncate(state.current.title, 50)}]({state.current.webpage_url}) · {state.current.duration_text}",
                inline=False,
            )

        upcoming = state.queue.as_list()
        if upcoming:
            lines = [
                f"`{index}.` {truncate(item['track'].get('title'), 50)} · {format_duration(item['track'].get('duration')) if not item['track'].get('is_live') else 'canlı'}"
                for index, item in enumerate(upcoming[:15], start=1)
            ]
            if len(upcoming) > 15:
                lines.append(f"… ve **{len(upcoming) - 15}** şarkı daha")
            result.add_field(name=f"Sıradakiler ({len(upcoming)})", value="\n".join(lines), inline=False)

        flags = []
        if state.loop:
            flags.append("🔁 tekrar açık")
        if state.repeat_queue:
            flags.append("♻️ liste tekrarı açık")
        if flags:
            result.set_footer(text=" · ".join(flags))
        await ctx.send(embed=result)

    @commands.command(name="nowplaying", aliases=["np", "şuan", "suan", "şuanki"], help="Şu an çalan şarkıyı gösterir.")
    async def nowplaying(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        current = state.current
        if current is None:
            raise MusicError("Şu an çalan bir şey yok.")
        result = current.embed()
        result.title = f"Şu an çalıyor: {result.title}"
        footer = f"Kuyrukta {len(state.queue)} şarkı · ses %{int(state.volume * 100)}"
        duration = current.track.get("duration")
        if not current.is_live and duration:
            footer += f" · {format_duration(int(state.elapsed))} / {format_duration(duration)}"
        result.set_footer(text=footer)
        await ctx.send(embed=result)

    @commands.command(name="remove", aliases=["sil", "kaldır"], help="Kuyruktaki bir şarkıyı siler.")
    async def remove(self, ctx: commands.Context, number: int) -> None:
        state = self._state(ctx)
        item = state.queue.remove_at(number - 1)
        title = truncate(item["track"].get("title"), 50)
        await ctx.send(embed=embed("Silindi", f"`{number}.` **{title}** kuyruktan çıkarıldı.", color=COLOR_SUCCESS))

    @commands.command(name="clear", aliases=["temizle"], help="Kuyruğu tamamen temizler.")
    async def clear(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        count = len(state.queue)
        state.queue.clear()
        await ctx.send(
            embed=embed("Temizlendi", f"**{count}** şarkı kuyruktan silindi.", color=COLOR_SUCCESS)
            if count
            else embed("Temizlendi", "Kuyruk zaten boştu.", color=COLOR_WARN)
        )

    @commands.command(name="shuffle", aliases=["karıştır", "karistir"], help="Kuyruğu karıştırır.")
    async def shuffle(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        if len(state.queue) < 2:
            raise MusicError("Karıştırmak için en az 2 şarkı olmalı.")
        state.queue.shuffle()
        await ctx.send(embed=embed("Karıştırıldı", f"**{len(state.queue)}** şarkı karıştırıldı.", color=COLOR_SUCCESS))

    @commands.command(name="loop", aliases=["tekrar", "repeat"], help="Tekrar modunu açar/kapatır.")
    async def loop(self, ctx: commands.Context, mode: str | None = None) -> None:
        state = self._state(ctx)
        value = (mode or "").lower()

        if value in {"", "aç", "ac", "on", "true", "1"}:
            state.loop = not state.loop
            state.repeat_queue = False
        elif value in {"kapat", "off", "false", "0", "sürekli", "surekli"}:
            state.loop = not state.loop
            state.repeat_queue = False
        elif value in {"liste", "queue", "all", "hepsi"}:
            state.repeat_queue = not state.repeat_queue
            state.loop = False
        else:
            raise MusicError("Kullanım: `!tekrar`, `!tekrar kapat` veya `!tekrar liste`")

        if state.loop:
            text = "🔁 Şu an çalan şarkı sonsuz tekrar edilecek."
        elif state.repeat_queue:
            text = "♻️ Kuyruk bittiğinde baştan sona tekrar edilecek."
        else:
            text = "Tekrar kapatıldı."
        await ctx.send(embed=embed("Tekrar", text, color=COLOR_SUCCESS))

    @commands.command(name="volume", aliases=["ses", "vol"], help="Ses seviyesini ayarlar (0-200).")
    async def volume(self, ctx: commands.Context, value: int | None = None) -> None:
        state = self._state(ctx)
        if value is None:
            await ctx.send(embed=embed("Ses Seviyesi", f"Güncel ses: **%{int(state.volume * 100)}**"))
            return

        if value > config.VOLUME_MAX * 100:
            raise MusicError(f"En fazla **%{int(config.VOLUME_MAX * 100)}** ses kullanabilirsin.")
        new_volume, applied = await self.music.set_volume(ctx.guild, state, value / 100)
        text = f"Ses seviyesi **%{int(new_volume * 100)}** olarak ayarlandı."
        if not applied:
            text += "\nŞu an çalan şarkı etkilenmedi, bir sonraki şarkıda geçerli olacak."
        await ctx.send(embed=embed("Ses Ayarlandı", text, color=COLOR_SUCCESS))

    @commands.command(name="join", aliases=["katıl", "gir"], help="Bulunduğun ses kanalına girer.")
    async def join(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        state.text_channel = ctx.channel
        client = await self.music.ensure_voice_client(ctx)
        await ctx.send(embed=embed("Bağlandım", f"**{client.channel.name}** kanalına bağlandım.", color=COLOR_SUCCESS))

    @commands.command(name="leave", aliases=["ayrıl", "ayril", "çık", "cik"], help="Ses kanalından çıkar.")
    async def leave(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        if ctx.voice_client is None:
            raise MusicError("Zaten bir ses kanalında değilim.")
        await self.music.stop(ctx.guild, state)
        await ctx.send(embed=embed("Ayrıldım", "Ses kanalından çıktım.", color=COLOR_WARN))

    @commands.command(name="yenile", aliases=["reload", "yeniden"], help="Komutları yeniden yükler (geliştirme için).")
    @commands.is_owner()
    async def reload(self, ctx: commands.Context) -> None:
        await ctx.reload_extension("cogs.music_cog")
        await ctx.send(embed=embed("Yenilendi", "Müzik komutları yeniden yüklendi.", color=COLOR_SUCCESS))

    @commands.command(name="bilgi", aliases=["info", "istatistik"], help="Bot durumu hakkında bilgi verir.")
    async def bilgi(self, ctx: commands.Context) -> None:
        await ctx.send(
            embed=embed(
                "Müzik Botu Durumu",
                f"Discord.py `{discord.__version__}`\n"
                f"yt-dlp `{yt_dlp.version.__version__}`\n"
                f"FFmpeg: `{'bulundu' if config.FFMPEG_PATH else 'BULUNAMADI'}`\n"
                f"Aktif kanal sayısı: **{sum(1 for g in self.bot.guilds if g.voice_client is not None)}**\n"
                f"Sunucu sayısı: **{len(self.bot.guilds)}**",
            )
        )

    @commands.command(name="yardım", aliases=["yardim", "help", "h", "komutlar"], help="Komut listesini gösterir.")
    async def yardim(self, ctx: commands.Context) -> None:
        prefix = config.PREFIX
        result = embed("Komutlar", f"Önek: `{prefix}`  ·  Bot: <@{self.bot.user.id}>" if self.bot.user else f"Önek: `{prefix}`")

        sections = (
            (
                "Çalma",
                (
                    (f"{prefix}play <isim|link>", "Şarkıyı çalar / kuyruğa ekler"),
                    (f"{prefix}ara <isim>", "YouTube araması yapar"),
                    (f"{prefix}seç <1-5>", "Arama sonucunu çalar"),
                    (f"{prefix}pause / {prefix}devam", "Duraklatır / sürdürür"),
                    (f"{prefix}atla", "Şarkıyı atlar"),
                    (f"{prefix}dur", "Durdurur ve ayrılır"),
                ),
            ),
            (
                "Kuyruk",
                (
                    (f"{prefix}queue", "Kuyruğu listeler"),
                    (f"{prefix}nowplaying", "Çalan şarkı"),
                    (f"{prefix}karıştır", "Kuyruğu karıştırır"),
                    (f"{prefix}sil <sıra>", "Sıradaki şarkıyı kaldırır"),
                    (f"{prefix}temizle", "Kuyruğu boşaltır"),
                    (f"{prefix}tekrar", "Tekrar modu"),
                ),
            ),
            (
                "Ayarlar",
                (
                    (f"{prefix}ses <0-200>", "Ses seviyesi"),
                    (f"{prefix}katıl / {prefix}ayrıl", "Ses kanalına gir / çık"),
                    (f"{prefix}bilgi", "Bot durumu"),
                ),
            ),
        )

        for name, entries in sections:
            result.add_field(
                name=name,
                value="\n".join(f"`{command}` — {description}" for command, description in entries),
                inline=False,
            )
        await ctx.send(embed=result)

    @commands.command(name="ping", help="Bot gecikmesini gösterir.")
    async def ping(self, ctx: commands.Context) -> None:
        latency = round(self.bot.latency * 1000)
        await ctx.send(embed=embed("Ping", f"Gecikme: **{latency} ms**", color=COLOR_SUCCESS))

    @commands.command(name="durum", aliases=["tani", "sesdurum"], help="Ses sorunlarini teshis eder.")
    async def durum(self, ctx: commands.Context) -> None:
        state = self._state(ctx)
        client = ctx.guild.voice_client
        lines = [
            f"Ses kanali: **{getattr(getattr(client, 'channel', None), 'name', 'yok')}**",
            f"Bagli: **{client is not None}**  ·  Oynatiyor: **{bool(client and client.is_playing())}**",
            f"Ses seviyesi: **%{int(state.volume * 100)}**  ·  Kuyruk: **{len(state.queue)}**",
        ]

        if client is not None:
            protocol = getattr(client, "_connection", None)
            lines += [
                f"Bot kendini susturdu: **{bool(getattr(protocol, 'self_mute', False))}**  ·  "
                f"Bot kendini sagirlastirdi: **{bool(getattr(protocol, 'self_deaf', False))}**",
                f"Gecikme: **{round(client.latency * 1000)} ms**",
            ]

        source = state.current.source if state.current is not None else None
        if source is None:
            lines.append("Su an calan kaynak: **yok**")
        else:
            data = getattr(source, "_bytes_read", None)
            packets = getattr(source, "_packets_read", None)
            lines.append(
                f"Gonderilen ses: **{data / 1_048_576:.2f} MB**"
                if data is not None
                else "Gonderilen ses: **hesaplanamiyor**"
            )
            if packets:
                lines.append(f"Gonderilen paket: **{packets}** (~{packets * 0.02:.0f} sn)")
            buffered = getattr(source, "buffered_packets", None)
            if callable(buffered):
                lines.append(f"Tampon: **{buffered() * 0.02:.1f} sn**")
            process = getattr(source, "_process", None)
            lines.append(f"FFmpeg calisiyor: **{process is not None and process.poll() is None}**")

        lines += [
            "",
            "Sessizlik surerse: bot adinin altindaki **hoparlor simgesine** bak "
            "(sessize alinmis olabilir) ve ayni ses kanalinda oldugundan emin ol.",
        ]
        await ctx.send(embed=embed("Ses Teshisi", "\n".join(lines)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
