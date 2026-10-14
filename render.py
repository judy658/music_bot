from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    """Render'in saglik kontrolu ve uyutmamasi icin HTTP cevabi verir."""

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}\n')

    do_HEAD = do_GET


def _self_ping(url: str) -> None:
    import time
    import urllib.request

    target = url.rstrip("/") + "/health"
    while True:
        time.sleep(240)
        try:
            urllib.request.urlopen(target, timeout=10)
        except Exception:
            pass


def main() -> None:
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="render-health").start()

    app_url = os.getenv("APP_URL", "").strip()
    if app_url:
        threading.Thread(target=_self_ping, args=(app_url,), daemon=True, name="self-ping").start()

    import asyncio

    import bot

    try:
        asyncio.run(bot.main())
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()