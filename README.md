# UNO Online Multiplayer

> Game kartu **UNO** multiplayer berbasis jaringan — server Python *authoritative*, client web (browser) & Pygame, transport **TCP** untuk game state, **UDP/WebRTC** untuk live voice, dan **MariaDB** untuk persistensi.

Proyek mata kuliah **Pemrograman Jaringan** — Institut Teknologi Sepuluh Nopember (ITS).

---

## Daftar Isi

1. [Deskripsi Project](#1-deskripsi-project)
2. [Fitur](#2-fitur)
3. [Tech Stack](#3-tech-stack)
4. [Arsitektur Sistem](#4-arsitektur-sistem)
5. [Protokol Jaringan](#5-protokol-jaringan)
6. [Pipeline Anti Invalid-Packet](#6-pipeline-anti-invalid-packet)
7. [Sistem Poin & Rank](#7-sistem-poin--rank)
8. [Struktur Kode](#8-struktur-kode)
9. [Skema Database](#9-skema-database)
10. [Instalasi & Menjalankan](#10-instalasi--menjalankan)
11. [Konfigurasi](#11-konfigurasi)
12. [Testing](#12-testing)
13. [Cara Bermain](#13-cara-bermain)
14. [Catatan Operasional](#14-catatan-operasional)

---

## 1. Deskripsi Project

UNO Online adalah implementasi lengkap permainan kartu UNO yang dapat dimainkan **2–4 pemain** secara real-time melalui jaringan. Arsitektur memisahkan dengan tegas antara **server** dan **client**:

- **Server bersifat *authoritative*** — seluruh aturan main, state permainan, pembagian kartu, dan validasi langkah diproses di server. Client hanya merender state dan mengirim input. Client **tidak dipercaya**, sehingga kecurangan (memainkan kartu ilegal, beraksi di luar giliran, dsb.) tidak mungkin karena ditolak oleh engine server.
- **Dua jenis client**: client **web** (HTML/CSS/JS, jalan langsung di browser tanpa instalasi) sebagai client utama, dan client **Pygame** native opsional untuk demo desktop.
- **Komunikasi multi-kanal**: TCP untuk game state yang andal & berurutan, UDP/WebRTC terpisah untuk live voice yang sensitif latency, serta WebSocket gateway sebagai jembatan browser ke server TCP.

Server berjalan multi-threaded (satu thread per koneksi client) dan menyimpan akun, statistik, leaderboard, serta riwayat match ke MariaDB.

---

## 2. Fitur

### Fitur Wajib
| Fitur | Penjelasan |
|---|---|
| Real-time state sync | Setiap perubahan state disiarkan ke seluruh pemain & penonton via `STATE_UPDATE`. |
| Room system | Buat room (dapat kode unik), gabung via kode, atau matchmaking otomatis. |
| Matchmaking | Quick Match memasangkan pemain ke room yang tersedia sesuai mode. |
| 2–4 pemain | Mendukung 2, 3, atau 4 pemain dengan tata letak meja menyesuaikan. |
| Reconnect handling | Putus koneksi saat match memberi **grace 30 detik** untuk kembali sebelum dianggap keluar. |
| Indikator ping | Ping diukur tiap 2 detik (echo `PING`/`PONG`) dan ditampilkan real-time. |
| Logging aktivitas | Semua event penting dicatat ke `data/logs/server.log` dan tabel `activity_log`. |
| Anti invalid-packet | Pipeline validasi berlapis menolak paket cacat, replay, atau aksi ilegal. |

### Fitur Tambahan
| Fitur | Penjelasan |
|---|---|
| Mode **Ranked** & **Classic** | Ranked mengubah poin/rank/statistik; Classic hanya menyimpan hasil match. |
| Sistem poin & rank bertingkat | Poin dinamis berbasis posisi finish + value kartu tersisa; rank Bronze→Platinum. |
| Global Ranked Leaderboard | Peringkat global diurutkan dari total poin tertinggi (Top Global Player). |
| Statistik pemain | Total match, total menang, win rate, total poin, dan tier rank. |
| **Riwayat match (Match History)** | Daftar match terakhir tiap pemain: hasil (Menang/Kalah/Selesai), mode, peringkat, perubahan poin, pemenang, dan waktu. |
| Spectator mode | Pemain yang kartunya habis otomatis **menang** dan jadi penonton hingga match selesai. |
| Live voice communication | Bicara langsung dalam room — UDP relay untuk client native, WebRTC/Opus + TURN untuk browser. |
| Manajemen sesi (session takeover) | Akun boleh login dari banyak client; jika sedang di match aktif lalu login lagi, sesi lama dipaksa logout dan sesi baru **mengambil alih match** tanpa membuat player kalah. |
| House rule multi-card | Boleh memainkan beberapa kartu angka sekaligus selama angkanya sama. |
| Draw stacking (+2/+4) | Tumpukan kartu +2/+4 terakumulasi (`pending_draw`); pemain berikut wajib menumpuk atau menarik semua. |
| UI/UX premium | Kartu *playable* terangkat & berbingkai emas, indikator warna aktif berwarna, animasi, sound effect & musik latar. |

---

## 3. Tech Stack

| Komponen | Teknologi |
|---|---|
| Bahasa | Python 3.10+ |
| Client web | HTML / CSS / JavaScript murni (tanpa framework, tanpa build step) |
| Client native | Pygame (opsional, untuk demo desktop) |
| Transport game state | `socket` TCP custom (length-prefix framing) |
| Transport voice | UDP relay (native) + WebRTC/Opus dengan TURN relay (browser) |
| Jembatan browser | WebSocket gateway (browser ⇄ Python ⇄ TCP server) |
| Concurrency | `threading` — satu thread per koneksi client |
| Database | MariaDB via `mysql-connector-python` (connection pool) |
| Keamanan | `bcrypt` (hash password) + pipeline validasi paket |
| Deployment | Docker Compose (server, MariaDB, Caddy reverse-proxy HTTPS, coturn TURN) |

### Mengapa pilihan transport ini?

- **TCP untuk game state** — UNO bersifat *turn-based* dan butuh pengiriman aksi yang **andal & berurutan**. Kehilangan satu paket aksi merusak konsistensi state semua pemain, sehingga jaminan *reliable-ordered* TCP lebih penting daripada keunggulan latency UDP.
- **UDP/WebRTC untuk voice** — audio live lebih sensitif terhadap delay daripada kehilangan frame kecil. Frame voice yang telat tidak perlu dikirim ulang, sehingga kanal voice dipisah agar sinkronisasi game di TCP tetap stabil.
- **WebSocket gateway** — browser tidak bisa membuka raw TCP socket. Gateway menjadi adapter transport: browser berbicara WebSocket, gateway meneruskan paket ke server TCP custom yang sama.

---

## 4. Arsitektur Sistem

```text
┌─────────────────┐         ┌─────────────────┐
│  Client Pygame  │         │  Browser (Web)  │
│  (native)       │         │  HTML/CSS/JS    │
└───┬─────────┬───┘         └───┬─────────┬───┘
    │ TCP     │ UDP             │ WebSocket│ WebRTC/Opus
    │ 5555    │ 5556            │ 8080     │ (via TURN 3478)
    │         │                 │          │
    │         │            ┌────▼──────────▼────┐
    │         │            │   Caddy (HTTPS)    │  reverse proxy + Let's Encrypt
    │         │            │   :80 / :443       │
    │         │            └────┬───────────────┘
    │         │                 │
    │         │            ┌────▼───────────────┐
    │         │            │   Web Gateway      │  web_gateway.py
    │         │            │ - static file web/ │  (WS ⇄ TCP bridge)
    │         │            │ - WebRTC signaling │
    │         │            └────┬───────────────┘
    │         │                 │ TCP 5555 (paket sama)
    ▼         ▼                 ▼
┌───────────────────────────────────────────────┐
│            Dedicated Game Server               │  socket_server.py
│  ┌──────────────┐  ┌────────────────────────┐  │
│  │ GameEngine   │  │ Services               │  │
│  │ (authoritative) │ auth / leaderboard     │  │
│  │ card/deck/room  │ + match history        │  │
│  └──────────────┘  └────────────────────────┘  │
│  Voice UDP relay (voice_server.py) :5556       │
└──────────────────────┬────────────────────────┘
                       │ mysql-connector (pool)
                ┌──────▼───────┐
                │   MariaDB    │  users, leaderboard, rooms,
                │              │  matches, match_players,
                │              │  activity_log, sessions
                └──────────────┘
```

**Alur singkat:** client → (TCP / WebSocket) → server → `PacketValidator` → handler → `GameEngine` (proses aturan) → broadcast `STATE_UPDATE` ke semua member room → client render.

---

## 5. Protokol Jaringan

Semua paket game adalah **JSON** dengan struktur:

```json
{ "type": "PLAY_CARD", "seq": 42, "payload": { "card": {"color": "Red", "ctype": "5"} } }
```

- **`type`** — tipe paket (lihat tabel di bawah).
- **`seq`** — nomor urut monoton naik per koneksi (anti-replay).
- **`payload`** — data spesifik tiap tipe.

### Framing TCP (`shared/protocol.py`)
Karena TCP adalah stream tanpa batas pesan, tiap paket dibungkus **length-prefix**: 4 byte big-endian panjang body + body JSON UTF-8. Penerima membaca panjang dulu, lalu membaca tepat sejumlah byte tersebut — sehingga pesan tidak tercampur (*framing*).

### Tipe Paket (ringkas)

**Client → Server (C2S)**
`REGISTER_REQ`, `LOGIN_REQ`, `SESSION_LOGIN_REQ`, `CREATE_ROOM_REQ`, `JOIN_ROOM_REQ`, `MATCHMAKE_REQ`, `START_MATCH_REQ`, `PLAY_CARD`, `DRAW_CARD`, `CALL_UNO`, `RECONNECT_REQ`, `LEAVE_ROOM`, `PING`, `GET_LEADERBOARD`, `GET_TOP_GLOBAL`, `GET_STATS`, `GET_MATCH_HISTORY`

**Server → Client (S2C)**
`REGISTER_OK/FAIL`, `LOGIN_OK/FAIL`, `ROOM_CREATED`, `JOIN_OK/FAIL`, `MATCH_FOUND`, `ROOM_UPDATE`, `GAME_START`, `STATE_UPDATE`, `DRAW_RESULT`, `DRAW_STACK_RESULT`, `UNO_OK/ANNOUNCE/PENALTY/CATCH`, `ACTION_REJECTED`, `PLAYER_WIN`, `ENTER_SPECTATOR`, `RECONNECT_OK`, `MATCH_RESULT`, `PONG`, `LEADERBOARD`, `STATS`, `TOP_GLOBAL`, `MATCH_HISTORY`, `LEFT_ROOM`, `FORCE_LOGOUT`, `ERROR`

> Definisi lengkap ada di [`shared/packet_types.py`](shared/packet_types.py).

---

## 6. Pipeline Anti Invalid-Packet

Setiap paket masuk melewati pipeline berlapis di server sebelum diproses ([`server/packet/validator.py`](server/packet/validator.py) + handler):

1. **Struktur** — field wajib (`type`, `seq`, `payload`) bertipe benar, `type` dikenal, ukuran wajar.
2. **Auth** — aksi non-publik (semua selain register/login/ping/reconnect) wajib dari koneksi terautentikasi.
3. **Sequence (anti-replay)** — `seq` harus monoton naik per koneksi; paket duplikat/lama dibuang (kecuali `PING`).
4. **Giliran** — `PLAY_CARD` / `DRAW_CARD` hanya diterima dari pemain yang sedang giliran (dicek di engine).
5. **Role** — spectator ditolak untuk semua aksi gameplay.
6. **Aturan main** — kartu harus valid menurut state engine (`is_valid_play` / `is_valid_multi_play`).

Paket yang gagal divalidasi ditolak dengan `ACTION_REJECTED` + alasan, dan dicatat ke activity log.

---

## 7. Sistem Poin & Rank

Mode **Ranked** mengubah poin, statistik ranked, dan leaderboard global. Mode **Classic** tetap menyimpan hasil match (termasuk ke riwayat) tetapi tidak mengubah poin/rank.

Poin Ranked memakai **base posisi** lalu dimodifikasi oleh **value kartu** yang tersisa saat match selesai. Total poin tidak pernah turun di bawah 0.

**Base point per posisi finish:**

| Jumlah Pemain | Rank 1 | Rank 2 | Rank 3 | Rank 4 |
|---|---|---|---|---|
| 2 | +15 | −10 | – | – |
| 3 | +20 | +10 | −10 | – |
| 4 | +25 | +15 | +5 | −10 |

**Value kartu (untuk modifier):**

| Kartu | Value |
|---|---:|
| Angka 0–9 | sesuai angka |
| Skip / Reverse / Draw Two | 15 |
| Wild / Wild Draw Four | 20 |

**Formula modifier dinamis** (`calc_dynamic_point_delta`):

```text
Rank 1     : base + min(15, total value kartu lawan tersisa // 20)
Rank 2 dst : base − min(10, value kartu sendiri tersisa // 20)
```

**Klasifikasi rank** (`classify_rank`):

| Rank | Total Poin |
|---|---|
| Bronze | 0 – 999 |
| Silver | 1000 – 1499 |
| Gold | 1500 – 1999 |
| Platinum | 2000+ |

---

## 8. Struktur Kode

```text
uno-online/
├── config.py                      # Konfigurasi terpusat (jaringan, DB, UI) via env var
├── requirements.txt               # Dependencies client (Pygame, dll.)
├── requirements-server.txt        # Dependencies server (mysql-connector, bcrypt)
├── Dockerfile                     # Image server (bundle: server/, web/, client/assets/)
├── docker-compose.yml             # Orkestrasi: db, server, caddy, turn
├── docker/
│   ├── entrypoint.sh              # Tunggu DB → init schema → game server + web gateway
│   └── Caddyfile                  # Reverse proxy HTTPS (Let's Encrypt)
│
├── shared/                        # Dipakai bersama server & client
│   ├── constants.py               # Kartu, POINT_TABLE, rank, status, role, arah
│   ├── packet_types.py            # Definisi tipe paket C2S / S2C + RejectReason
│   ├── protocol.py                # Length-prefix framing TCP (send/recv packet)
│   └── voice_protocol.py          # Encoding/protokol paket voice UDP
│
├── server/
│   ├── main_server.py             # Entry point (--init-db | jalankan server)
│   ├── socket_server.py           # TCP threading + semua handler & routing
│   ├── voice_server.py            # UDP relay live voice per room
│   ├── web_gateway.py             # HTTP static web/ + WebSocket bridge + WebRTC signaling
│   ├── core/
│   │   ├── card.py                # Representasi kartu & aturan kecocokan (matches)
│   │   ├── deck.py                # Deck standar, shuffle, draw, discard
│   │   ├── game_engine.py         # Inti aturan UNO authoritative (giliran, efek, menang)
│   │   └── room.py                # Room, member, host, status, role
│   ├── services/
│   │   ├── auth_service.py        # Register, login (bcrypt), token sesi, stats
│   │   └── leaderboard_service.py # Proses hasil match, poin, leaderboard, match history
│   ├── packet/
│   │   └── validator.py           # Pipeline anti invalid-packet (struktur/auth/sequence)
│   ├── db/
│   │   ├── database.py            # Connection pool MariaDB + query helper
│   │   └── schema.sql             # DDL seluruh tabel
│   └── utils/
│       └── logger.py              # Logging aktivitas (file + tabel activity_log)
│
├── client/                        # Client Pygame native (opsional)
│   ├── main_client.py             # Entry point + scene manager + poll jaringan
│   ├── network/
│   │   ├── client_network.py      # TCP client, framing, ping
│   │   └── voice_client.py        # UDP voice client
│   ├── scenes/                    # Satu file per layar
│   │   ├── base.py                # Scene base & AppState (state global client)
│   │   ├── login_scene.py         # Login & register
│   │   ├── lobby_scene.py         # Menu utama, mode, matchmaking, leaderboard, riwayat
│   │   ├── room_scene.py          # Ruang tunggu (daftar pemain, start)
│   │   ├── game_scene.py          # Papan permainan (tangan, deck, discard, UNO, wild)
│   │   ├── spectator_scene.py     # Mode penonton
│   │   ├── result_scene.py        # Hasil akhir match & peringkat
│   │   └── leaderboard_scene.py   # Leaderboard global & riwayat match
│   ├── ui/
│   │   ├── widgets.py             # Button, TextInput, palet, util gambar
│   │   ├── assets.py              # Loader gambar kartu & banner
│   │   └── sounds.py              # SFX + musik latar (mp3 + sintesis fallback)
│   └── assets/                    # PNG kartu + sound (juga dipakai web)
│
├── web/                           # Client browser (tanpa instalasi)
│   ├── index.html                 # Struktur semua view (auth/lobby/room/game/result)
│   ├── style.css                  # Tema dark premium, layout, animasi
│   └── app.js                     # Logika client: WS, render, input, voice WebRTC
│
├── data/logs/                     # File log server
└── tests/                         # test_game_engine, test_flow_inproc, test_session_takeover
```

### Modul inti yang perlu diketahui

- **`server/core/game_engine.py`** — jantung permainan. Mengelola giliran (`_advance`), arah, efek kartu aksi/wild, draw stacking (`pending_draw`), UNO call/penalty/catch, deteksi pemenang & urutan finish, serta snapshot state (`get_state`). Semua keputusan final ada di sini.
- **`server/socket_server.py`** — menerima koneksi (1 thread/client), routing paket ke handler, mengelola room/matchmaking, broadcast state, reconnect, dan **session takeover**.
- **`web/app.js`** — client web lengkap: koneksi WebSocket, render seluruh view, input kartu (termasuk *playable highlight* & multi-select angka), pemilih warna wild, voice WebRTC, dan riwayat match.

---

## 9. Skema Database

MariaDB dengan tujuh tabel utama ([`server/db/schema.sql`](server/db/schema.sql)):

| Tabel | Fungsi |
|---|---|
| `users` | Akun: `user_id`, `username` (unik), `password_hash` (bcrypt). |
| `leaderboard` | Statistik 1:1 dengan user: total match/win/lose/point, `win_rate`, `rank_tier`. |
| `rooms` | Metadata room: kode, host, status. |
| `matches` | Satu baris per match selesai: pemenang, jumlah pemain, mode, waktu. |
| `match_players` | Detail tiap pemain per match: posisi finish, perubahan poin, hasil (WIN/MID/LOSE). |
| `activity_log` | Log aktivitas untuk audit (login, match end, invalid packet, dll.). |
| `sessions` | Token sesi untuk auto-login & reconnect, dengan masa berlaku. |

`matches` + `match_players` inilah sumber **Riwayat Match** (di-join saat `GET_MATCH_HISTORY`).

---

## 10. Instalasi & Menjalankan

### Prasyarat
1. Python 3.10+
2. MariaDB / MySQL berjalan (default `127.0.0.1:3306`) — **atau** gunakan Docker Compose (sudah termasuk MariaDB).

### A. Deploy Server dengan Docker Compose (rekomendasi untuk VPS)

Satu perintah menjalankan MariaDB + game server TCP/UDP + web gateway + Caddy (HTTPS) + coturn (TURN). Pemain cukup membuka browser, **tanpa instalasi**.

```bash
# 1. Salin env contoh lalu ubah password DB
cp .env.example .env
nano .env

# 2. Build & jalankan seluruh stack
docker compose up -d --build

# 3. Lihat log server
docker compose logs -f server
```

Port firewall yang perlu dibuka di VPS:

```bash
sudo ufw allow 5555/tcp          # game state TCP
sudo ufw allow 5556/udp          # live voice UDP (client native)
sudo ufw allow 8080/tcp          # web client HTTP/WebSocket
sudo ufw allow 80/tcp            # HTTP challenge untuk HTTPS
sudo ufw allow 443/tcp           # HTTPS/WSS (wajib untuk mic di browser)
sudo ufw allow 3478/tcp          # TURN relay voice web
sudo ufw allow 3478/udp
sudo ufw allow 49160:49200/udp   # port relay TURN
```

Akses client via browser: `http://IP_VPS:8080` atau `https://<domain>` (Caddy otomatis menerbitkan sertifikat).

### B. Menjalankan Manual (development lokal)

```bash
# 1. Virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate         # Linux/Mac

# 2. Dependencies
pip install -r requirements.txt

# 3. Inisialisasi database (sekali saja)
python -m server.main_server --init-db

# 4. Jalankan game server (TCP 5555 + voice UDP 5556)
python -m server.main_server

# 5. (opsional) Jalankan web gateway untuk client browser (port 8080)
python -m server.web_gateway

# 6. (opsional) Jalankan client Pygame native
python -m client.main_client                    # default localhost
python -m client.main_client --server IP_SERVER # tentukan host server
```

---

## 11. Konfigurasi

Semua nilai dapat di-override lewat environment variable ([`config.py`](config.py)):

| Variabel | Default | Keterangan |
|---|---|---|
| `UNO_HOST` | `0.0.0.0` | Bind address server |
| `UNO_PORT` | `5555` | Port game TCP |
| `UNO_VOICE_PORT` | `5556` | Port voice UDP |
| `UNO_SERVER` | `127.0.0.1` | Host tujuan client (atau argumen `--server`) |
| `UNO_DB_HOST` / `UNO_DB_PORT` | `127.0.0.1` / `3306` | Koneksi MariaDB |
| `UNO_DB_USER` / `UNO_DB_PASSWORD` | `root` / `password` | Kredensial DB |
| `UNO_DB_NAME` | `uno_online` | Nama database |
| `UNO_DB_POOL` | `8` | Ukuran connection pool |
| `UNO_SESSION_TTL_HOURS` | `72` | Masa berlaku token sesi |

Contoh (Linux/Mac):

```bash
export UNO_DB_USER=root
export UNO_DB_PASSWORD=passwordmu
export UNO_DB_NAME=uno_online
```

> Catatan voice: live voice butuh mikrofon/speaker. Akses mic dari domain/IP publik di browser umumnya **wajib HTTPS** — Docker Compose menyertakan Caddy untuk itu, dan coturn (TURN) agar voice tetap tersambung di balik NAT.

---

## 12. Testing

```bash
# Seluruh unit test
pytest tests/ -v

# Test alur cepat in-process (tanpa MariaDB)
python tests/test_flow_inproc.py
```

| File test | Cakupan |
|---|---|
| `tests/test_game_engine.py` | Aturan engine: giliran, efek kartu, draw stacking, UNO, menang. |
| `tests/test_flow_inproc.py` | Alur end-to-end in-process (login → room → main → hasil). |
| `tests/test_session_takeover.py` | Logika pengambilalihan sesi saat login ganda. |

---

## 13. Cara Bermain

1. **Daftar** akun baru, lalu **Masuk**.
2. Di lobby: pilih mode **Ranked** atau **Classic**, lalu **Matchmaking** (otomatis), **Create Room** (dapat kode), atau **Join** dengan kode room. Lobby juga menampilkan **statistik**, **leaderboard global**, dan **riwayat match** Anda.
3. Host menekan **Start Match** setelah minimal 2 pemain.
4. Saat giliran Anda, kartu yang bisa dimainkan **terangkat & berbingkai emas**. Klik untuk memainkan. Klik **deck** di tengah untuk menarik kartu.
5. Untuk memainkan beberapa kartu angka sama sekaligus, klik kartu-kartunya lalu tekan **Mainkan**.
6. Kartu **Wild** memunculkan pemilih warna (bisa dibatalkan dengan **Esc**/**Batal**).
7. Saat ada tumpukan **+2/+4**, Anda wajib menumpuk kartu + atau menarik semua kartu akumulasi.
8. Tekan **UNO!** saat kartu tersisa 1 (boleh saat sisa 2 di giliran sendiri). Lupa menekan berisiko penalti — lawan bisa **Lapor UNO**.
9. Tombol **Mic** mengaktifkan live voice dalam room yang sama.
10. Pemain yang kartunya habis **menang** dan otomatis jadi **penonton** hingga match selesai.

---

## 14. Catatan Operasional

- **Logging** tersimpan di `data/logs/server.log` dan tabel `activity_log`.
- **Reconnect** — putus koneksi saat match memberi **30 detik** untuk kembali sebelum dianggap keluar.
- **Operasi Docker umum:**

  ```bash
  docker compose ps                 # status container
  docker compose logs -f server     # ikuti log server
  docker compose up -d --build server  # rebuild & restart hanya server
  docker compose restart server
  docker compose down               # hentikan semua
  docker compose down -v            # hentikan + hapus data MariaDB (hati-hati)
  ```

- **Redeploy hanya perubahan web/server** cukup `docker compose up -d --build server` (image membundle `web/`, `server/`, `shared/`, `client/assets/`).

---

<p align="center"><i>Network Programming Final Project — Institut Teknologi Sepuluh Nopember (ITS)</i></p>
