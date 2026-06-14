"""
Konfigurasi terpusat untuk server & client.
Nilai dapat di-override lewat environment variable.
"""
import os

# -- Jaringan ---------------------------------------------------------------
SERVER_HOST = os.getenv("UNO_HOST", "0.0.0.0")   # server bind
SERVER_PORT = int(os.getenv("UNO_PORT", "5555"))
VOICE_PORT = int(os.getenv("UNO_VOICE_PORT", "5556"))
CLIENT_CONNECT_HOST = os.getenv("UNO_SERVER", "127.0.0.1")  # tujuan client

# -- Database (MariaDB) -----------------------------------------------------
DB_HOST = os.getenv("UNO_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("UNO_DB_PORT", "3306"))
DB_USER = os.getenv("UNO_DB_USER", "root")
DB_PASSWORD = os.getenv("UNO_DB_PASSWORD", "password")
DB_NAME = os.getenv("UNO_DB_NAME", "uno_online")
DB_POOL_SIZE = int(os.getenv("UNO_DB_POOL", "8"))

# -- Game -------------------------------------------------------------------
SESSION_TTL_HOURS = int(os.getenv("UNO_SESSION_TTL_HOURS", "72"))

# -- Client UI --------------------------------------------------------------
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
CARD_W = 90
CARD_H = 130
PING_INTERVAL_SECONDS = 2
