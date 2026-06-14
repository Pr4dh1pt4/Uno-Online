"""
Layanan autentikasi: register, login, dan manajemen sesi/token.
Password di-hash dengan bcrypt (tidak pernah disimpan plaintext).
"""
import secrets
from datetime import datetime, timedelta

import bcrypt

import config
from server.db import database


def register(username: str, password: str) -> tuple[bool, str | int]:
    """Return (True, user_id) atau (False, reason)."""
    username = (username or "").strip()
    if not (3 <= len(username) <= 32):
        return False, "username_length"
    if len(password or "") < 4:
        return False, "password_too_short"

    existing = database.query_one(
        "SELECT user_id FROM users WHERE username = %s", (username,)
    )
    if existing:
        return False, "username_taken"

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = database.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
        (username, pw_hash), commit=True,
    )
    # buat baris leaderboard awal
    database.execute(
        "INSERT INTO leaderboard (user_id) VALUES (%s)", (user_id,), commit=True
    )
    return True, user_id


def login(username: str, password: str) -> tuple[bool, dict | str]:
    """Return (True, {user_id, username, token, stats}) atau (False, reason)."""
    row = database.query_one(
        "SELECT user_id, username, password_hash FROM users WHERE username = %s",
        (username or "",),
    )
    if not row:
        return False, "invalid_credentials"
    if not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return False, "invalid_credentials"

    token = _create_session(row["user_id"])
    stats = get_stats(row["user_id"])
    return True, {
        "user_id": row["user_id"],
        "username": row["username"],
        "token": token,
        "stats": stats,
    }


def _create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires = _session_expiry()
    database.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires), commit=True,
    )
    return token


def _session_expiry() -> datetime:
    return datetime.now() + timedelta(hours=config.SESSION_TTL_HOURS)


def _extend_session(token: str) -> None:
    database.execute(
        "UPDATE sessions SET expires_at = %s WHERE token = %s",
        (_session_expiry(), token or ""), commit=True,
    )


def validate_token(token: str) -> int | None:
    """Return user_id jika token valid & belum kedaluwarsa, else None."""
    row = database.query_one(
        "SELECT user_id FROM sessions WHERE token = %s AND expires_at >= NOW()",
        (token or "",),
    )
    if not row:
        return None
    _extend_session(token)
    return row["user_id"]


def login_with_token(token: str) -> tuple[bool, dict | str]:
    """Return session user data if token is valid."""
    row = database.query_one(
        "SELECT u.user_id, u.username "
        "FROM sessions s JOIN users u ON u.user_id = s.user_id "
        "WHERE s.token = %s AND s.expires_at >= NOW()",
        (token or "",),
    )
    if not row:
        return False, "invalid_session"
    _extend_session(token)
    return True, {
        "user_id": row["user_id"],
        "username": row["username"],
        "token": token,
        "stats": get_stats(row["user_id"]),
    }


def get_stats(user_id: int) -> dict:
    row = database.query_one(
        "SELECT total_match, total_win, total_lose, total_point, rank_tier, win_rate "
        "FROM leaderboard WHERE user_id = %s", (user_id,)
    )
    if not row:
        return {"total_match": 0, "total_win": 0, "total_lose": 0,
                "total_point": 0, "rank_tier": "Bronze", "win_rate": 0.0}
    return row
