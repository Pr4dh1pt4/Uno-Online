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
            return

    database.init_pool()
    database.ensure_runtime_schema()
    SocketServer().start()

if __name__ == "__main__":
    main()
