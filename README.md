# Discord Müzik Botu

YouTube'dan şarkı arayıp Discord ses kanalında çalan, Windows'ta çalışan kişisel müzik botu.
`ffmpeg` + `yt-dlp` + `discord.py` üzerine kurulu, tek tıkla kurulur, isteğe bağlı olarak bilgisayar açılışında kendiliğinden başlar.

---

## 1. Gereksinimler

| Gereksinim | Not |
|---|---|
| Python 3.11+ | `python --version` ile kontrol et |
| ffmpeg | `start.bat` winget ile kurmayı dener, yoksa `.env` içine yolunu yaz |
| Discord bot tokenı | Developer Portal → Bot → Reset Token |

Windows'ta hızlı kurulum:

```powershell
winget install --id Python.Python.3.11 -e
winget install --id Gyan.FFmpeg -e
```

---

## 2. Discord botu hazırlama

1. <https://discord.com/developers/applications> → **New Application** → ad ver → **Create**.
2. Soldaki **Bot** sekmesine tıkla → **Reset Token** → çıkan tokenı kopyala.
   - Bu token `xxx.yyy.zzz` biçimindedir. Paylaştığın 64 haneli uygulama anahtarı **bot tokenı değildir**.
   - Tokenı birine gönderirsen yeniden üret.
3. Aynı sayfada **Message Content Intent** → **ENABLE**.
4. **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Permissions: `Use Voice Activity`, `Connect`, `Speak`, `Send Messages`, `Embed Links`, `View Channels`
   - Üretilen davet bağlantısını aç ve botu sunucuna ekle.
   - Alternatif hazır bağlantı:
     ```
     https://discord.com/oauth2/authorize?client_id=1555838694093623336&permissions=36719616&scope=bot
     ```
     (`permissions=8` yani Administrator gerekmez.)

---

## 3. Kurulum ve çalıştırma

Projeyi indirdikten sonra klasörde bir kez:

```powershell
py -m pip install -r requirements.txt
```

`.env` dosyasını aç ve tokenı yaz:

```env
DISCORD_TOKEN=xxx.yyy.zzz
```

Sonra **`start.bat`** dosyasına çift tıkla. Doğru çalıştığında şunu yazar:

```
[1/3] Python: python
[2/3] Ayarlar okunuyor...
    Token: girdi
    FFmpeg: C:\...\ffmpeg.exe
    Onek: !
[3/3] Bot baslatiliyor...
```

Ardından konsolda:

```
Bot giriş yaptı: MüzikBotu#1234 (...)
```

`start.bat` kendisi kurulum yapmaz; eksik paket varsa ekrana `py -m pip install -r requirements.txt` komutunu yazar.
Bot Python'u bulamazsa `python` adıyla denenir; gerekirse `calistir.bat` veya `otomatik.bat` aynı sırayı kullanır.

**Windows güvenlik duvarı engeliyse** (`WinError 10013`): `guvenlik_duvari.bat` dosyasına çift tıkla,
yönetici izni ver, sonra `start.bat` çalıştır. Detay için [7. Sorun giderme](#7-sorun-giderme).

Aynı pencereyi kapatmadan ikinci kez `start.bat` çalıştırırsan **"Bota bağlanılamadı"** hatası alırsın; önce açık olan botu durdur (Ctrl+C).

Venv kuruluysa hızlıca başlatmak için: `calistir.bat`

---

## 4. Bilgisayar açılışında otomatik başlatma

### Yöntem A: Görev Zamanlayıcısı (önerilen)

1. `Win + R` → `taskschd.msc` → **Görev Zamanlayıcısı** aç.
2. Sağda **Temel Görev Oluştur...**
3. **Ad:** `Muzik Botu` → **İleri**
4. **Tetikleyiciler** → **Yeni** → **Bilgisayarı başlatır** → yalnızca **Bilgisayarı açtığımda** → **İleri**
5. **Eylem:** `Programı başlat` → yol olarak `C:\Users\alihan\Desktop\music_bot\otomatik.bat` → **İleri**
6. **Adı** boş bırak, **İleri** → **Son**.

`otomatik.bat` çıktıyı `logs\bot.log` dosyasına yazar, pencere açılmaz. Kontrol için `logs\bot.log` dosyasına bak.

Görevi "Oturum açılmasa da çalıştır" yapacaksan:
**Görev Zamanlayıcısı → Muzik Botu → Özellikler → Genel** → *"Kullanıcı oturumu açık olmasa da çalıştır"* seç, sonra parola isteyecek.

### Yöntem B: Başlangıç klasörü

`Win + R` → `shell:startup` → açılan klasöre `otomatik.bat` dosyasının kısayolunu koy.
(Aynı anda iki yöntemi kullanma, bot iki kez açılır.)

---

## 5. Komutlar

Varsayılan önek `!` (`.env` içindeki `PREFIX` ile değişir).

| Komut | Yazış | Açıklama |
|---|---|---|
| `!play` | `!çal` `!p` | Şarkı adı veya YouTube linki çalar, kuyruğa ekler |
| `!ara` | `!search` | YouTube'da arar, 5 sonuç listeler |
| `!seç` | `!sec` | Son aramadan `1`-`5` arası birini çalar |
| `!pause` | `!duraklat` | Duraklatır |
| `!resume` | `!devam` | Devam ettirir |
| `!stop` | `!dur` | Durdurur ve kanaldan ayrılır |
| `!skip` | `!atla` | Şu anki şarkıyı atlar |
| `!queue` | `!sıra` `!liste` | Kuyruğu gösterir |
| `!nowplaying` | `!np` | Çalan şarkı + geçen süre |
| `!remove` | `!sil 2` | Kuyruktaki 2. şarkıyı siler |
| `!clear` | `!temizle` | Kuyruğu boşaltır |
| `!shuffle` | `!karıştır` | Kuyruğu karıştırır |
| `!loop` | `!tekrar` | `!tekrar kapat`, `!tekrar liste` |
| `!volume` | `!ses 120` | Ses 0-200; çalarken de anında uygulanır |
| `!join` | `!gir` | Bulunduğun ses kanalına girer |
| `!leave` | `!çık` | Ses kanalından çıkar |
| `!bilgi` | `!info` | Sürümler, sunucu sayısı |
| `!durum` | `!tani` | Ses teşhisi: kanal, ses, gönderilen ses miktarı |
| `!yardım` | `!help` | Komut listesi |
| `!ping` | | Gecikme |

Örnekler:

```
!play Rick Astley - Never Gonna Give You Up
!play https://www.youtube.com/watch?v=dQw4w9WgXcQ
!ara daft punk one more time
!seç 1
!ses 80
```

---

## 6. Ayar dosyası (`.env`)

| Ayar | Varsayılan | Açıklama |
|---|---|---|
| `DISCORD_TOKEN` | – | **Zorunlu.** Bot tokenı |
| `PREFIX` | `!` | Komut ön eki |
| `FFMPEG_PATH` | otomatik | ffmpeg tam yolu |
| `PLAYER_CLIENTS` | boş | yt-dlp oynatıcı istemcileri, ör. `android,web_safari` |
| `COOKIES_FILE` | boş | `cookies.txt` yolu (yaş sınırlı/özel videolar) |
| `PROXY` | boş | `socks5://127.0.0.1:1080` gibi |
| `STREAM_FORMAT` | `bestaudio/best` | Akış formatı |
| `FALLBACK_FORMAT` | `worstaudio/worst` | Akış hatasında denenecek yedek format |
| `MAX_PLAYLIST_ITEMS` | `50` | Oynatma listesinden alınacak max şarkı |
| `MAX_SEARCH_RESULTS` | `5` | Arama sonuç sayısı |
| `MAX_DURATION_MINUTES` | `180` | Bu süreden uzun şarkı atlanır |
| `MIN_DURATION_SECONDS` | `30` | Bundan kısa şarkı atlanır |
| `ALLOW_LIVE` | `true` | Canlı yayınlara izin ver |
| `VOLUME_DEFAULT` | `0.45` | Başlangıç sesi |
| `VOLUME_MAX` | `2.0` | En yüksek ses (`!ses 200`) |
| `NORMALIZE_AUDIO` | `false` | `loudnorm` ile ses eşitleme (CPU yiyebilir) |
| `IDLE_TIMEOUT_SECONDS` | `900` | Sıra bitince kaç saniye sonra kanaldan ayrılır |
| `CACHE_DIR` | `cache/downloads` | İndirilen dosyalar |

---

## 7. Sorun giderme

**"Discord bu tokeni geçersiz sayıyor (HTTP 401)" / "Giriş başarısız"**
Token geçersiz. Token'lar bir kez gösterilir; **her "Reset Token" işlemi eskisini öldürür**, bu yüzden
daha önce kaydettiğin bir token sonradan çalışmaz. Developer Portal → **Bot** → **Reset Token** →
yeni tokeni kopyala → `.env` içindeki `DISCORD_TOKEN=` satırına yaz → `start.bat`.

Tek tek doğrulamak için: `python token_kontrol.py`

**"Windows güvenlik duvarı bu programın internet erişimini engelliyor" / `WinError 10013`**
 antivirüs/güvenlik yazılımı `python.exe` için **Outbound Block** kuralı koymuş olabilir. Bu durumda
bot Discord'a bağlanamaz. Çözüm: **`guvenlik_duvari.bat`** dosyasına çift tıkla (yönetici izni ister),
izni ekledikten sonra `start.bat` çalıştır.Elle yapmak istersen yönetici PowerShell'inde:

```powershell
New-NetFirewallRule -DisplayName "Python Discord Bot" -Direction Outbound `
  -Program "C:\Users\alihan\AppData\Local\Programs\Python\Python311\python.exe" `
  -Action Allow -Profile Any
```

Engelleyen kuralları görmek için: `Get-NetFirewallRule -Direction Outbound -Action Block | Format-Table`

**"pip / yt-dlp indirme hatası"**
Aynı sebepten olur: Python'ın çıkış bağlantısı engelliyse `pip` de çalışmaz.

**"DISCORD_TOKEN boş / geçerli görünmüyor"**
Token'ı `.env` içine yaz. Token `xxx.yyy.zzz` biçiminde olmalı; uygulamanın 64 haneli anahtarı bot tokenı değildir.

**"PrivilegedIntentsRequired" / "Mesaj içeriği izni gerekli"**
Developer Portal → Bot → **Message Content Intent** → Enable → botu sunucudan çıkarıp geri ekle.

**"Bot kanala giremiyor"**
Bot rolüne `Bağlan`, `Konuş`, `Etkinlik Kullan` izinlerini ver. Kanal için `Bağlan` izni de gerekli.

**"Bu video yaş sınırlı / bot doğrulaması istedi"**
`.env` içine `COOKIES_FILE=...` (tarayıcıdan alınan `cookies.txt`) veya `PLAYER_CLIENTS=android,web_safari` yaz. Ardından botu yeniden başlat.

**Şarkı çalmıyor, "Ses akışı alınamadı"**
yt-dlp'nin YouTube'a erişimi kısıtlı olabilir. `yt-dlp -U` ile güncelle, `PLAYER_CLIENTS` değerini değiştir.

**Ses komutu çalışmıyor gibi (eski sürüm)**
Çalarken `!ses` verildiğinde şarkı, bulunduğu konumdan başlayarak yeniden başlatılır; kısa bir takılma olabilir. Şarkının ilk 1 saniyesinde veya canlı yayınlarda ayar bir sonraki şarkıya uygulanır.

**Loglar**
`logs\bot.log` (1 MB, 3 dosya).

---

## 8. Dosya düzeni

```
bot.py            giriş, intents, komut yükleme, hata yönetimi
token_kontrol.py  Discord tokenını tek başına doğrular
config.py         .env ayarları ve ffmpeg bulma
ytdl.py           arama, çözümleme, stream/indirme kaynakları
audio_source.py   ffmpeg opus kaynağı, yeniden başlatma, sessizlik
music.py          kuyruk, oynatma döngüsü, ses ayarı
cogs/music_cog.py tüm komutlar
utils.py          gömme mesajlar, süre biçimi
start.bat         kurulum + çalıştır
calistir.bat      sadece çalıştır
otomatik.bat      pencere açmadan çalıştır (görev zamanlayıcı için)
guvenlik_duvari.bat python.exe için internet izni ekler (yönetici gerekir)
logs/bot.log      çalışma günlüğü
cache/            indirilen ses dosyaları
```

---

## 9. Render'da çalıştırma (bulut, ücretsiz katman)

Botunu kendi bilgisayarının yerine **Render**'da ücretsiz katmanda çalıştırabilirsin.

> **Önemli:** Render ücretsiz katmanı, **15 dakika gelen istek olmazsa** hizmeti uyutur.
> Discord botları sadece dışarı bağlantı açar (gelen HTTP yok), bu yüzden uyumayı engellemek için
> botun içindeki `/health` ucu düzenli olarak "ping"lenmelidir. `render.py` bu ucu sağlar.
> Bununla birlikte sürekli açık bir hizmet aylık 750 ücretsiz saatin neredeyse tamamını kullanır
> ve Render istediği an botu yeniden başlatabilir (bot otomatik yeniden bağlanır).
> 7/24 kusursuz çalışma garantisi için ücretsiz katmanda böyle bir garanti yoktur — bilgisayarın
> açık kalması ya da $7'lık Worker planı en güvenilir seçenektir.

### Adımlar

1. **Kod GitHub'da olsun.** Proje klasöründe:

   ```bash
   git init
   git add .
   git commit -m "Ilk surum"
   git branch -M main
   git remote add origin https://github.com/judy658/music_bot.git
   git push -u origin main
   ```

2. **Token'ı GitHub'a değil, Render'a yaz**: `.env` dosyası `.gitignore` içinde olduğu için itilmez.
   Render panosunda bu token Render'ın `DISCORD_TOKEN` ortam değişkenine girilecek.

3. **Render'da servisi oluştur.** ffmpeg + libopus sistem paketleri gerektiği için proje **Docker** ile
   dağıtılır (`Dockerfile` bunları kurar). Native Python ortamında `apt` izni olmadığı için Docker şart.
   - render.com → **New → Web Service** → GitHub'da `judy658/music_bot` seç
   - **Language/Environment: Docker** (Render kök dizindeki `Dockerfile`'ı otomatik seçer)
   - Plan: **Free**
   - Build/Start komutlarını Render Dockerfile'dan alır; elle yazma.
   - Environment (**Advanced** altında):
     - `DISCORD_TOKEN` = bot tokenın
     - `APP_URL` = hizmetin adresi, ör. `https://muzik-bot.onrender.com`
   - **Deploy**

   > Alternatif: repo kökündeki `render.yaml` sayesinde **New → Blueprint** diyerek de kurabilirsin;
   > Render servisi Docker olarak, doğru ayarlarla otomatik açar.

4. **Uyumayı engelle** — aşağıdaki ikisinden birini yap:
   - `APP_URL` doluysa bot kendini 4 dakikada bir ping'ler (gerektiğinde hizmet uyanır), **veya**
   - https://uptimerobot.com → ücretsiz hesap → **New monitor** → `HTTP(s)` → adres `https://muzik-bot.onrender.com/health` → 5 dakikada bir kontrol.

5. **Aynı tokenı iki yerde çalıştırma**: Render'da bot açıkken PC'de `start.bat` ile aynı bot çalışırsa
   ikisi birbirini Discord'dan düşürür. Birini kapat.

### YouTube "bot doğrulaması" hatası (önemli)

Render gibi **veri merkezi** IP'lerinden YouTube, isteği `Sign in to confirm you're not a bot` diye reddeder.
Bu bir ayar hatası değil, IP itibarı sorunudur; `PLAYER_CLIENTS` değiştirmek çözmez. Çözüm: botu **giriş
yapılmış bir YouTube oturumunun çerezleriyle** çalıştırmak.

1. Bir tarayıcıda (mümkünse **ayrı/ikinci** bir Google hesabıyla; ana hesabınızı riske atmayın) youtube.com'a gir.
2. "Get cookies.txt LOCALLY" tipi bir eklentiyle **`cookies.txt`** (Netscape biçimi) indir.
3. Dosyayı base64'e çevir:
   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.txt"))
   ```
4. Render panosu → Environment → `YOUTUBE_COOKIES_B64` = çıkan uzun metin.
   (Alternatif: `cookies.txt` içeriğini doğrudan `YOUTUBE_COOKIES` değişkenine yapıştır.)
5. Servisi yeniden başlat (`Re-deploy`/`Restart`). Bot açılışta çerezi `cookies.txt` dosyasına yazar, yt-dlp onu kullanır.

> Çerezle giriş yapılınca yt-dlp'nin varsayılan `tv_downgraded` istemcisi
> `The page needs to be reloaded` hatası verebilir; bot bu durumda istemciyi otomatik olarak
> `default,-tv_downgraded,web_embedded` yapar. Farklı bir değer denemek istersen Render'da
> `PLAYER_CLIENTS` ortam değişkenini ayarla (ör. `default,-tv_downgraded,web_embedded`).

> Çerezlerin süresi dolar; hata geri gelirse aynı adımlarla tazele.
> İmajda ayrıca `deno` (YouTube'un artık zorunlu tuttuğu JavaScript çalışma ortamı) kurulur.
> Çerez veya kararlı bir residential proxy olmadan veri merkezi IP'sinde kalıcı çözüm garanti değildir;
> en sorunsuz seçenek botu evindeki/residential IP'li bilgisayarda çalıştırmaktır.

> Render'ın dosya sistemi geçicidir; her yeniden başlatmada `cache/` temizlenir (akış modu etkilenmez).
> `Dockerfile` imajı oluştururken `ffmpeg` ve `libopus0` sistem paketlerini kurar, sonra `requirements.txt`'i yükler.