"""
Layanan leaderboard: memproses hasil match dengan sistem poin bertingkat,
memperbarui rank & win rate, serta menyediakan Top Global Player.
"""
from shared.constants import (
    calc_dynamic_point_delta, classify_rank,
    MATCH_MODE_RANKED, MATCH_MODE_CLASSIC,
)
from server.db import database
from server.utils import logger


def process_match_result(room_id: str, finish_order: list[int],
                         players: list[tuple[int, str]],
                         match_mode: str = MATCH_MODE_RANKED,
                         ranking_details: list[dict] | None = None) -> dict:
    """
    finish_order: list user_id terurut (posisi 1 = pemenang).
    players: semua peserta match (untuk player_count & winner).
    match_mode: "ranked" mengubah poin; "classic" hanya menyimpan hasil.
    Return dict {user_id: {point_change, total_point, rank_tier, result}}.
    """
    match_mode = match_mode if match_mode in {MATCH_MODE_RANKED, MATCH_MODE_CLASSIC} else MATCH_MODE_RANKED
    is_ranked = match_mode == MATCH_MODE_RANKED
    player_count = len(players)
    winner_id = finish_order[0] if finish_order else None
    remaining_by_user = _remaining_values(finish_order, ranking_details)
    total_remaining_value = sum(remaining_by_user.values())

    # buat record match
    match_id = _insert_match(room_id, winner_id, player_count, match_mode)

    result_map: dict[int, dict] = {}
    last_pos = len(finish_order)

    for pos, user_id in enumerate(finish_order, start=1):
        own_remaining = remaining_by_user.get(user_id, 0)
        others_remaining = total_remaining_value - own_remaining
        delta = (
            calc_dynamic_point_delta(player_count, pos, own_remaining, others_remaining)
            if is_ranked else 0
        )
        if pos == 1:
            result = "WIN"
        elif pos == last_pos:
            result = "LOSE"
        else:
            result = "MID"

        if is_ranked:
            info = _update_leaderboard(user_id, delta, result)
        else:
            info = _current_rank_info(user_id)

        database.execute(
            "INSERT INTO match_players (match_id, user_id, finish_position, point_change, result) "
            "VALUES (%s, %s, %s, %s, %s)",
            (match_id, user_id, pos, delta, result), commit=True,
        )

        result_map[user_id] = {
            "point_change": delta,
            "total_point": info["total_point"],
            "rank_tier": info["rank_tier"],
            "result": result,
            "finish_position": pos,
            "match_mode": match_mode,
            "remaining_value": own_remaining,
            "others_remaining_value": others_remaining,
        }

    logger.info(f"Match {match_id} selesai, mode={match_mode}, ranking={finish_order}, poin={result_map}")
    return result_map


def _remaining_values(finish_order: list[int],
                      ranking_details: list[dict] | None) -> dict[int, int]:
    values = {uid: 0 for uid in finish_order}
    if not ranking_details:
        return values
    for row in ranking_details:
        try:
            uid = int(row["user_id"])
        except (KeyError, TypeError, ValueError):
            continue
        values[uid] = int(row.get("remaining_value", 0) or 0)
    return values


def _insert_match(room_id: str, winner_id: int | None, player_count: int,
                  match_mode: str) -> int:
    try:
        return database.execute(
            "INSERT INTO matches (room_id, winner_id, player_count, match_mode, started_at, ended_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (room_id, winner_id, player_count, match_mode), commit=True,
        )
    except Exception as e:
        # Kompatibel dengan database lama yang belum punya kolom match_mode.
        logger.warning(f"Kolom matches.match_mode belum siap, fallback tanpa mode: {e}")
        return database.execute(
            "INSERT INTO matches (room_id, winner_id, player_count, started_at, ended_at) "
            "VALUES (%s, %s, %s, NOW(), NOW())",
            (room_id, winner_id, player_count), commit=True,
        )


def _current_rank_info(user_id: int) -> dict:
    row = database.query_one(
        "SELECT total_point, rank_tier FROM leaderboard WHERE user_id = %s", (user_id,)
    )
    if not row:
        database.execute("INSERT INTO leaderboard (user_id) VALUES (%s)", (user_id,), commit=True)
        return {"total_point": 0, "rank_tier": "Bronze"}
    total_point = row["total_point"]
    return {
        "total_point": total_point,
        "rank_tier": row.get("rank_tier") or classify_rank(total_point),
    }


def _update_leaderboard(user_id: int, delta: int, result: str) -> dict:
    row = database.query_one(
        "SELECT total_match, total_win, total_lose, total_point "
        "FROM leaderboard WHERE user_id = %s", (user_id,)
    )
    if not row:
        database.execute("INSERT INTO leaderboard (user_id) VALUES (%s)", (user_id,), commit=True)
        row = {"total_match": 0, "total_win": 0, "total_lose": 0, "total_point": 0}

    total_match = row["total_match"] + 1
    total_win = row["total_win"] + (1 if result == "WIN" else 0)
    total_lose = row["total_lose"] + (1 if result == "LOSE" else 0)
    total_point = max(0, row["total_point"] + delta)  # poin tidak negatif
    win_rate = (total_win / total_match) if total_match else 0.0
    rank_tier = classify_rank(total_point)

    database.execute(
        "UPDATE leaderboard SET total_match=%s, total_win=%s, total_lose=%s, "
        "total_point=%s, win_rate=%s, rank_tier=%s WHERE user_id=%s",
        (total_match, total_win, total_lose, total_point, win_rate, rank_tier, user_id),
        commit=True,
    )
    return {"total_point": total_point, "rank_tier": rank_tier}


def get_leaderboard(limit: int = 10) -> list[dict]:
    return database.query_all(
        "SELECT u.username, l.total_point, l.rank_tier, l.win_rate, "
        "l.total_match, l.total_win, l.total_lose "
        "FROM leaderboard l JOIN users u ON u.user_id = l.user_id "
        "ORDER BY l.total_point DESC LIMIT %s", (limit,)
    )


def get_top_global(limit: int = 10) -> list[dict]:
    rows = get_leaderboard(limit)
    for i, r in enumerate(rows, start=1):
        r["rank_pos"] = i
    return rows


def get_match_history(user_id: int, limit: int = 20) -> list[dict]:
    """Riwayat match milik satu pemain, terbaru lebih dulu.

    Mengembalikan ringkasan tiap match: mode, jumlah pemain, posisi finish,
    hasil (WIN/MID/LOSE), perubahan poin, nama pemenang, dan waktu selesai.
    """
    rows = database.query_all(
        "SELECT m.match_id, m.match_mode, m.player_count, m.ended_at, "
        "       mp.finish_position, mp.point_change, mp.result, "
        "       w.username AS winner_name "
        "FROM match_players mp "
        "JOIN matches m ON m.match_id = mp.match_id "
        "LEFT JOIN users w ON w.user_id = m.winner_id "
        "WHERE mp.user_id = %s "
        "ORDER BY m.match_id DESC LIMIT %s",
        (user_id, limit),
    )
    for r in rows:
        ended = r.get("ended_at")
        # datetime tidak bisa diserialisasi JSON; format jadi string ringkas.
        r["ended_at"] = ended.strftime("%Y-%m-%d %H:%M") if ended else None
    return rows
