"""
Lapisan akses database MariaDB.

Menggunakan mysql-connector-python (pure Python, mudah di-install).
Connection pool dipakai agar aman untuk akses multi-thread dari server.
"""
import threading

import mysql.connector
from mysql.connector import pooling

import config

_pool: pooling.MySQLConnectionPool | None = None
_pool_lock = threading.Lock()


def init_pool() -> None:
    """Inisialisasi connection pool (idempoten)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            return
        _pool = pooling.MySQLConnectionPool(
            pool_name="uno_pool",
            pool_size=config.DB_POOL_SIZE,
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4",
            autocommit=False,
        )


def get_conn():
    if _pool is None:
        init_pool()
    return _pool.get_connection()


def execute(query: str, params: tuple = (), *, commit: bool = False):
    """Jalankan query non-select. Return lastrowid."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if commit:
            conn.commit()
        last = cur.lastrowid
        cur.close()
        return last
    finally:
        conn.close()


def query_one(query: str, params: tuple = ()) -> dict | None:
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        row = cur.fetchone()
        cur.close()
        return row
    finally:
        conn.close()


def query_all(query: str, params: tuple = ()) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def init_schema() -> None:
    """
    Buat database & tabel dari schema.sql.
    Dipanggil saat server start agar tidak perlu langkah manual.
    """
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()

    # Koneksi tanpa database dulu (untuk CREATE DATABASE)
    conn = mysql.connector.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )
    cur = conn.cursor()
    for statement in _split_statements(sql):
        if statement.strip():
            try:
                cur.execute(statement)
            except Exception as e:
                if _is_ignorable_schema_error(e):
                    continue
                raise
    _apply_migrations(cur)
    conn.commit()
    cur.close()
    conn.close()


def _split_statements(sql: str) -> list[str]:
    """Pisahkan statement SQL sederhana berdasarkan ';' (cukup untuk schema ini)."""
    cleaned = "\n".join(
        line for line in sql.splitlines()
        if not line.lstrip().startswith("--")
    )
    return [s for s in cleaned.split(";") if s.strip()]


def ensure_runtime_schema() -> None:
    """Tambahkan kolom ringan yang mungkin belum ada pada database lama."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        _apply_migrations(cur)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _apply_migrations(cur) -> None:
    migrations = [
        "ALTER TABLE matches ADD COLUMN match_mode VARCHAR(16) DEFAULT 'ranked' AFTER player_count",
    ]
    for statement in migrations:
        try:
            cur.execute(statement)
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column" in msg or "1060" in msg:
                continue
            raise


def _is_ignorable_schema_error(error: Exception) -> bool:
    """Allow repeated init_schema runs against an existing database."""
    msg = str(error).lower()
    return (
        "duplicate key name" in msg
        or "1061" in msg
        or "duplicate column" in msg
        or "1060" in msg
    )
