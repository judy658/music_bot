from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

import config

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def kontrol() -> int:
    token = config.DISCORD_TOKEN

    if not token:
        print("[HATA] .env dosyasinda DISCORD_TOKEN bos.")
        return 1

    if token.count(".") != 2 or len(token) < 50:
        print("[HATA] Bu bir bot tokeni degil.")
        print(f"       Uzunluk {len(token)} karakter, nokta sayisi {token.count('.')}.")
        print("       Bot tokeni 'xxx.yyy.zzz' bicimindedir (yaklasik 136 karakter).")
        print("       Uygulamanin 64 haneli anahtari bot tokeni DEGILDIR.")
        return 1

    iste = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (music-bot, 1.0)"},
    )
    try:
        with urllib.request.urlopen(iste, timeout=20) as yanit:
            veri = json.load(yanit)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("[HATA] Discord bu tokeni gecersiz sayiyor (HTTP 401).")
            print("       Genelde bu, daha once yenilenmis (eski) bir token demektir.")
            print("       Developer Portal -> Bot -> Reset Token -> yeni tokeni kopyala")
            print("       ve .env dosyasindaki DISCORD_TOKEN satirina yaz.")
            return 1
        if exc.code == 403:
            print("[HATA] Discord erisimi reddetti (HTTP 403). Tokeni kontrol et.")
            return 1
        print(f"[HATA] Discord API hatasi: HTTP {exc.code}")
        return 1
    except Exception as exc:
        print(f"[HATA] Discord'a ulasilamadi: {exc}")
        print("       Guvenlik duvari engeli olabilir: guvenlik_duvari.bat calistir.")
        return 1

    print(f"    Token gecerli: {veri.get('username')} (bot id {veri.get('id')})")
    return 0


if __name__ == "__main__":
    sys.exit(kontrol())