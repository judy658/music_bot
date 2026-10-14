from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal
import sys
from typing import Any

import discord
from discord.ext import commands

import config
from music import Music
from utils import COLOR_WARN, embed

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)-22s  %(message)s"

handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    handlers.append(
        logging.handlers.RotatingFileHandler(
            config.LOG_DIR / "bot.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    )
except OSError:
    pass

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S", handlers=handlers)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
log = logging.getLogger("music_bot")
log.info("Log dosyasi: %s", config.LOG_DIR / "bot.log")

PLACEHOLDER_TOKENS = {"", "buraya", "token", "x", "your_token_here"}


def validate_environment() -> None:
    problems: list[str] = []

    if not config.DISCORD_TOKEN:
        problems.append(
            "DISCORD_TOKEN boş. Discord Geliştirici Portalı → Bot → Reset Token ile aldığın tokeni "
            "`.env` dosyasındaki DISCORD_TOKEN satırına yaz."
        )
    elif config.DISCORD_TOKEN.lower() in PLACEHOLDER_TOKENS:
        problems.append("DISCORD_TOKEN hâlâ örnek değer. Gerçek bot tokenını yaz.")
    elif "." not in config.DISCORD_TOKEN or len(config.DISCORD_TOKEN) < 50:
        problems.append(
            "DISCORD_TOKEN geçerli görünmüyor. Discord bot tokenları 'xxx.yyy.zzz' biçimindedir. "
            f"Şu anki değer ({len(config.DISCORD_TOKEN)} karakter) bir bot tokenı olamaz."
        )

    if not config.FFMPEG_PATH:
        problems.append(
            "ffmpeg bulunamadı. winget ile kur: `winget install Gyan.FFmpeg` "
            "veya `.env` içine FFMPEG_PATH yaz."
        )

    try:
        import nacl  # noqa: F401
    except ImportError:
        problems.append("PyNaCl yüklü değil (ses kanalları için şart). Kurulum için `start.bat` çalıştır.")

    if problems:
        print("=" * 68, file=sys.stderr)
        print("BAŞLATILAMADI - kurulum eksik:", file=sys.stderr)
        for index, problem in enumerate(problems, start=1):
            print(f"  {index}. {problem}", file=sys.stderr)
        print("=" * 68, file=sys.stderr)
        sys.exit(1)


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )
        self.music = Music()
        self.music.bot = self

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.music_cog")
        log.info("Komutlar yüklendi.")

    async def on_ready(self) -> None:
        activity = discord.Activity(type=discord.ActivityType.listening, name=f"{config.PREFIX}yardım")
        await self.change_presence(activity=activity)
        log.info("Bot giriş yaptı: %s (%s)", self.user, self.user.id if self.user else "?")
        log.info("Sunucu sayısı: %d | komut: %d | önek: %s", len(self.guilds), len(self.commands), config.PREFIX)
        log.info("FFmpeg: %s", config.FFMPEG_PATH or "BULUNAMADI")

    async def on_message(self, message: discord.Message) -> None:
        await self.process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Bu komutu kullanmak için **{error.retry_after:.1f}** saniye bekle.", delete_after=5)
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=embed("Yetki Hatası", "Bu komut için gerekli izne sahip değilsin.", color=COLOR_WARN))
            return
        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(f"`{name}`" for name in sorted(error.missing_permissions or []))
            await ctx.send(
                embed=embed(
                    "Bot Yetkisi Eksik",
                    f"Şu izinler verilmeli: {missing}\nSunucu Ayarları → Roller → bot rolü → İzinler.",
                    color=COLOR_WARN,
                )
            )
            return
        if isinstance(error, commands.NoPrivateMessage):
            return

        from music import MusicError
        from ytdl import YTDLException

        original = getattr(error, "original", error)
        if isinstance(original, (MusicError, YTDLException)):
            return

        log.error("Komut hatası (%s): %s", ctx.command.qualified_name if ctx.command else "?", error, exc_info=error)
        try:
            await ctx.send(
                embed=embed(
                    "Beklenmeyen Hata",
                    "Komut çalıştırılırken sorun oluştu. Ayrıntılar için konsolu kontrol et.",
                    color=COLOR_WARN,
                ),
                delete_after=10,
            )
        except discord.HTTPException:
            pass

    async def on_error(self, event: str, *args, **kwargs) -> None:
        log.exception("Olay hatası: %s", event)


def _application_id() -> str:
    """Tokenin ilk bolumunden uygulama ID'sini cikarir (portal linki icin)."""
    try:
        import base64

        segment = config.DISCORD_TOKEN.split(".")[0]
        return base64.b64decode(segment + "===").decode("ascii")
    except Exception:
        return "0"


def _is_blocked_by_firewall(exc: BaseException) -> bool:
    """aioview / aiohttp hatalari gercek soket hatasini sarar; zinciri tarayarak bulur."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, PermissionError):
            return True
        if getattr(current, "winerror", None) == 10013:
            return True
        if "Erişim engellendi" in str(current) or "access is denied" in str(current).lower():
            return True
        nxt = getattr(current, "os_error", None) or current.__cause__ or current.__context__
        current = nxt if isinstance(nxt, BaseException) else None
    return False


def _raise_timer_resolution() -> Any:
    """Windows'ta time.sleep hassasiyetini 1 ms'e cikarir.

    Varsayilan cozunurluk 15.6 ms'dir; oynatici 20 ms'de bir paket gonderdiginde
    bu sapma duyulur takilmalara yol acar.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        winmm = ctypes.WinDLL("winmm")
        winmm.timeBeginPeriod(1)
        return winmm
    except (OSError, AttributeError):
        return None


async def main() -> None:
    validate_environment()
    winmm = _raise_timer_resolution()
    if winmm is not None:
        log.info("Windows zamanlayici hassasiyeti 1 ms yapildi.")
    bot = MusicBot()

    async def shutdown() -> None:
        log.info("Kapatılıyor, kanallardan ayrılıyorum...")
        await bot.music.leave_all()
        await bot.close()

    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        signal_value = getattr(signal, signal_name, None)
        if signal_value is None:
            continue
        try:
            loop.add_signal_handler(signal_value, lambda: asyncio.create_task(shutdown()))
        except (NotImplementedError, RuntimeError):
            pass

    log.info("Discord'a bağlanılıyor...")
    try:
        await bot.start(config.DISCORD_TOKEN)
    except discord.LoginFailure:
        log.error("Giriş başarısız: DISCORD_TOKEN geçersiz. Bot tokenını yeniden üret.")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        log.error("Mesaj icerigi izni (Message Content Intent) kapali.")
        log.error("Ac: https://discord.com/developers/applications/%s/bot", _application_id())
        log.error("  'Message Content Intent' anahtarini AC ve 'Save Changes'a bas.")
        log.error("  Sonra botu yeniden baslat. (Sunucuya tekrar eklemen gerekmez.)")
        sys.exit(1)
    except OSError as exc:
        if _is_blocked_by_firewall(exc):
            log.error("Windows guvenlik duvari bu programin internet erisimini engelliyor.")
            log.error("Cozum: Yonetici olarak PowerShell ac ve su komutu calistir:")
            log.error(
                '  New-NetFirewallRule -DisplayName "Python (discord bot)" -Direction Outbound '
                '-Program "%s" -Action Allow -Profile Any' % sys.executable
            )
            log.error("Engelleyen kurallar: Get-NetFirewallRule -Direction Outbound -Action Block")
            sys.exit(1)
        log.error("Baglanti kurulamadi: %s", exc)
        sys.exit(1)
    except (asyncio.TimeoutError, discord.HTTPException) as exc:
        log.error("Baglanti kurulamadi: %s", exc)
        sys.exit(1)
    finally:
        if not bot.is_closed():
            await bot.music.leave_all()
            await bot.close()
        if winmm is not None:
            try:
                winmm.timeEndPeriod(1)
            except (OSError, AttributeError):
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Kapatıldı.")
