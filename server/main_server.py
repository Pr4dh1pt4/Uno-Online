"""
Entry point server UNO Online.

Penggunaan:
    python -m server.main_server          # jalankan server
    python -m server.main_server --init   # buat skema DB lalu jalankan

Pastikan MariaDB berjalan & kredensial di config.py / env benar.
"""
import sys

from server.db import database
from server.socket_server import SocketServer
from server.utils import logger


def main():
    if "--init" in sys.argv or "--init-db" in sys.argv:
        logger.info("Inisialisasi skema database...")
        database.init_schema()
        logger.info("Skema database siap.")
        if "--init-db" in sys.argv:
            return  # hanya init lalu keluar

    database.init_pool()
    database.ensure_runtime_schema()
    SocketServer().start()


if __name__ == "__main__":
    main()
