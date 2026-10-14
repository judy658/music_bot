from __future__ import annotations

import io
import logging
import subprocess
import threading
import time
from collections import deque
from typing import Any

import discord
from discord.player import CREATE_NO_WINDOW, OPUS_SILENCE, OggStream

log = logging.getLogger("music_bot.audio")

PACKET_SECONDS = 0.02
BUFFER_PACKETS = 150
PRIME_PACKETS = 60
STALL_TIMEOUT = 15.0
NETWORK_ERROR_MARKERS = (
    "error in the pull function",
    "io error",
    "error number -",
    "connection reset",
    "session has been invalidated",
    "read error",
    "partial file",
    "error during demuxing",
    "broken pipe",
    "getaddrinfo failed",
    "connection refused",
    "connection timed out",
    "server returned 4",
)


class MusicAudioSource(discord.AudioSource):
    BLOCKSIZE = io.DEFAULT_BUFFER_SIZE
    SILENCE = OPUS_SILENCE

    def __init__(
        self,
        source: str,
        *,
        volume: float = 1.0,
        filters: list[str] | None = None,
        executable: str = "ffmpeg",
        bitrate: int = 128,
        seek: float = 0.0,
    ) -> None:
        super().__init__()
        self._volume = max(0.0, float(volume))
        self._filters = [f for f in (filters or []) if f]
        self._source = source
        self._executable = executable
        self._bitrate = bitrate
        self._seek = max(0.0, float(seek))
        self._current_error: BaseException | None = None
        self._stderr_tail = bytearray()
        self._closed = False
        self._retired = False

        command: list[str] = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostats",
            "-nostdin",
        ]
        if self._seek > 0:
            command += ["-ss", f"{self._seek:.2f}"]
        if source.startswith(("http://", "https://")):
            command += [
                "-reconnect",
                "1",
                "-reconnect_at_eof",
                "0",
                "-reconnect_streamed",
                "1",
                "-reconnect_on_network_error",
                "1",
                "-reconnect_delay_max",
                "5",
                "-reconnect_max_retries",
                "8",
                "-rw_timeout",
                "15000000",
            ]
        command += ["-i", source]
        filters = self._filters + [f"volume={self._volume:.4f}"]
        if filters:
            command += ["-af", ",".join(filters)]
        command += [
            "-map_metadata",
            "-1",
            "-vn",
            "-sn",
            "-dn",
            "-f",
            "opus",
            "-c:a",
            "libopus",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            f"{bitrate}k",
            "-vbr",
            "on",
            "-application",
            "audio",
            "-fec",
            "true",
            "-packet_loss",
            "15",
            "-blocksize",
            str(self.BLOCKSIZE),
            "pipe:1",
        ]

        try:
            self._process: subprocess.Popen[bytes] = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise discord.ClientException(f"{executable} bulunamadı.") from exc
        except OSError as exc:
            raise discord.ClientException(f"ffmpeg başlatılamadı: {exc}") from exc

        self._stdout = self._process.stdout
        self._packet_iter = OggStream(self._stdout).iter_packets()
        self._bytes_read = 0
        self._packets_read = 0
        self._started = False
        self._buffer: deque[bytes] = deque()
        self._buffer_cond = threading.Condition()
        self._source_eof = False
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True, name="ffmpeg-stderr")
        self._stderr_thread.start()
        self._pump_thread = threading.Thread(target=self._pump, daemon=True, name="audio-pump")
        self._pump_thread.start()
        log.info(
            "ffmpeg baslatildi: ses=%%%d filtre=%s konum=%.1fs kaynak=%s",
            int(self._volume * 100),
            ",".join(self._filters) or "-",
            self._seek,
            source[:120],
        )

    def _read_stderr(self) -> None:
        stream = self._process.stderr
        if stream is None:
            return
        try:
            for line in iter(stream.readline, b""):
                self._stderr_tail.extend(line)
                if len(self._stderr_tail) > 1024:
                    del self._stderr_tail[:-1024]
        except (ValueError, OSError):
            pass

    def _pump(self) -> None:
        """ffmpeg'den paketleri arka planda çekip tampona doldurur.

        Windows'ta pipe tamponu ~4 KB (0.25 sn ses). Oynatıcı beklemeden
        çekebilmesi için paketler ayrı bir iş parçacığında biriktirilir.
        """
        try:
            while True:
                if self._closed or self._retired:
                    break
                with self._buffer_cond:
                    while len(self._buffer) >= BUFFER_PACKETS and not self._closed and not self._retired:
                        self._buffer_cond.wait(0.2)
                    if self._closed or self._retired:
                        break
                data = next(self._packet_iter, b"")
                if not data:
                    break
                self._bytes_read += len(data)
                self._packets_read += 1
                if not self._started:
                    self._started = True
                    log.info("ffmpeg ses akisi basladi: ilk paket %d bayt", len(data))
                elif self._packets_read % 2500 == 0:
                    log.info(
                        "ffmpeg akisi devam ediyor: %d paket (%.1f sn), %.2f MB",
                        self._packets_read,
                        self._packets_read * PACKET_SECONDS,
                        self._bytes_read / 1_048_576,
                    )
                with self._buffer_cond:
                    self._buffer.append(data)
                    self._buffer_cond.notify_all()
        except (ValueError, OSError):
            pass
        finally:
            with self._buffer_cond:
                self._source_eof = True
                self._buffer_cond.notify_all()

    def prime(self, packets: int = PRIME_PACKETS, timeout: float = 8.0) -> int:
        """Oynatma başlamadan önce paketlerin birikmesini bekler."""
        deadline = time.monotonic() + timeout
        with self._buffer_cond:
            while len(self._buffer) < packets and not self._source_eof and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._buffer_cond.wait(min(0.1, remaining))
            return len(self._buffer)

    def buffered_packets(self) -> int:
        with self._buffer_cond:
            return len(self._buffer)

    def ended_with_network_error(self) -> bool:
        """FFmpeg'in ag kaynakli bir hatayla erken kapandigini soyler.

        Oynatici bitiste cleanup cagirdigi icin _closed durumuna bakilmaz;
        cikti/kuyruk bilgisi korunur.
        """
        if self._current_error is not None:
            return True
        text = bytes(self._stderr_tail).decode("utf-8", "ignore").lower()
        return any(marker in text for marker in NETWORK_ERROR_MARKERS)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def url(self) -> str:
        return self._source

    @property
    def retired(self) -> bool:
        return self._retired

    def clone(self, *, volume: float | None = None, seek: float = 0.0) -> MusicAudioSource:
        """Ayni kaynaktan, farkli ses seviyesi ve konumla yeni bir kaynak olusturur."""
        return MusicAudioSource(
            self._source,
            volume=self._volume if volume is None else volume,
            filters=self._filters,
            executable=self._executable,
            bitrate=self._bitrate,
            seek=seek,
        )

    def retire(self) -> None:
        """Kaynak degistirildiginde cagrilir; okuma sessizlik dondurur."""
        self._retired = True
        with self._buffer_cond:
            self._buffer_cond.notify_all()

    def is_opus(self) -> bool:
        return True

    def read(self) -> bytes:
        """20 ms'lik TEK bir Opus paketi döndürür (discord.py sözleşmesi).

        Ham Ogg sayfaları okunursa Discord 512 ms'lik paketi 20 ms'de gönderir,
        ses 25 kat hızlı iletilir ve hiç duyulmaz. Bu yüzden paket ayrıştırılır.
        """
        if self._retired:
            if not self._closed:
                self.cleanup()
            return self.SILENCE
        if self._closed:
            return b""
        stalled = False
        deadline = time.monotonic() + STALL_TIMEOUT
        with self._buffer_cond:
            while not self._buffer and not self._source_eof and not self._closed and not self._retired:
                if time.monotonic() >= deadline:
                    stalled = True
                    break
                self._buffer_cond.wait(0.2)
            if self._buffer:
                data = self._buffer.popleft()
                self._buffer_cond.notify_all()
                return data

        if stalled:
            log.warning("Ses akisi durakladi (%.0f sn veri gelmedi), kaynak kapatiliyor.", STALL_TIMEOUT)
            self._current_error = discord.FFmpegProcessError(
                f"Ses akışı {STALL_TIMEOUT:.0f} saniye boyunca veri üretmedi."
            )
            self.cleanup()
            return b""
        if self._retired:
            return self.SILENCE
        if self._closed:
            return b""
        self._check_exit()
        return b""

    def _check_exit(self) -> None:
        if self._current_error is not None:
            return
        returncode = self._process.poll()
        if returncode is None:
            try:
                returncode = self._process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                return
        detail = bytes(self._stderr_tail).decode("utf-8", "ignore").strip()
        if detail:
            log.info("ffmpeg cikti (kod %s): %s", returncode, detail[:300])
        if returncode == 0 or self._closed:
            log.info("ffmpeg bitti (kod %s, %d bayt)", returncode, self._bytes_read)
            return
        message = f"ffmpeg {returncode} ile kapandı"
        if detail:
            message = f"{message}: {detail[:300]}"
        self._current_error = discord.FFmpegProcessError(message)

    def cleanup(self) -> None:
        self._closed = True
        with self._buffer_cond:
            self._buffer.clear()
            self._buffer_cond.notify_all()
        self._kill()

    def _kill(self) -> None:
        process = getattr(self, "_process", None)
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
        except OSError:
            pass

        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def __repr__(self) -> str:
        return f"<MusicAudioSource vol={self._volume:.2f} filters={self._filters}>"

    def __getstate__(self) -> dict[str, Any]:
        return {"volume": self._volume}
