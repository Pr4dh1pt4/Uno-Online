import json
import logging
import os

from server.db import database

_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(_LOG_DIR, "server.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

_log = logging.getLogger("uno")

def info(msg: str) -> None:
    _log.info(msg)

def warning(msg: str) -> None:
    _log.warning(msg)

def error(msg: str) -> None:
    _log.error(msg)

def activity(user_id: int | None, event_type: str, detail: dict | None = None) -> None:
    detail_json = json.dumps(detail or {}, ensure_ascii=False)
    _log.info(f"ACTIVITY user={user_id} {event_type} {detail_json}")
    try:
        database.execute(
            "INSERT INTO activity_log (user_id, event_type, detail) VALUES (%s, %s, %s)",
            (user_id, event_type, detail_json),
            commit=True,
        )
    except Exception as e:
        _log.warning(f"Gagal simpan activity_log: {e}")
