"""
Konstanta bersama antara server dan client.
Berisi definisi kartu UNO, sistem poin bertingkat, dan klasifikasi rank.
"""

# ---------------------------------------------------------------------------
# Warna & tipe kartu
# ---------------------------------------------------------------------------
COLORS = ["Red", "Green", "Blue", "Yellow"]
WILD_COLOR = "Wild"

# Tipe kartu angka 0-9 disimpan sebagai string angka.
ACTION_TYPES = ["Skip", "Reverse", "Draw"]      # Draw = Draw Two
WILD_TYPES = ["Wild", "Wild_Draw"]              # Wild_Draw = Wild Draw Four

# ---------------------------------------------------------------------------
# Konfigurasi room & match
# ---------------------------------------------------------------------------
MIN_PLAYERS = 2
MAX_PLAYERS = 4
INITIAL_HAND_SIZE = 7
RECONNECT_GRACE_SECONDS = 30
PING_INTERVAL_SECONDS = 2

MATCH_MODE_RANKED = "ranked"
MATCH_MODE_CLASSIC = "classic"
MATCH_MODES = {MATCH_MODE_RANKED, MATCH_MODE_CLASSIC}

# ---------------------------------------------------------------------------
# Sistem poin ranked.
# Base point tetap ditentukan posisi, lalu dimodifikasi oleh value kartu tersisa.
# ---------------------------------------------------------------------------
POINT_TABLE = {
    2: [15, -10],
    3: [20, 10, -10],
    4: [25, 15, 5, -10],
}

ACTION_CARD_POINT_VALUE = 15
WILD_CARD_POINT_VALUE = 20


def calc_point_delta(player_count: int, finish_position: int) -> int:
    """Hitung base point berdasarkan jumlah pemain & posisi finish (1-indexed)."""
    table = POINT_TABLE.get(player_count)
    if not table:
        return 0
    idx = finish_position - 1
    if idx < 0 or idx >= len(table):
        return 0
    return table[idx]


def card_score_value(card) -> int:
    """Nilai kartu untuk scoring ranked: angka nominal, aksi 15, wild 20."""
    ctype = card.get("ctype") if isinstance(card, dict) else getattr(card, "ctype", "")
    color = card.get("color") if isinstance(card, dict) else getattr(card, "color", "")
    if color == WILD_COLOR or ctype in WILD_TYPES:
        return WILD_CARD_POINT_VALUE
    if ctype in ACTION_TYPES:
        return ACTION_CARD_POINT_VALUE
    if isinstance(ctype, str) and ctype.isdigit():
        return int(ctype)
    return 0


def calc_dynamic_point_delta(
    player_count: int,
    finish_position: int,
    own_remaining_value: int,
    others_remaining_value: int,
) -> int:
    """
    Ranked dynamic point:
    - Posisi finish memberi base point.
    - Rank 1 mendapat bonus kecil dari total value kartu lawan yang tersisa.
    - Pemain lain mendapat penalty kecil dari value kartu sendiri yang tersisa.
    """
    base = calc_point_delta(player_count, finish_position)
    if finish_position == 1:
        return base + min(15, max(0, others_remaining_value) // 20)
    return base - min(10, max(0, own_remaining_value) // 20)


# ---------------------------------------------------------------------------
# Klasifikasi rank berdasarkan total poin
# ---------------------------------------------------------------------------
def classify_rank(total_point: int) -> str:
    if total_point >= 2000:
        return "Platinum"
    if total_point >= 1500:
        return "Gold"
    if total_point >= 1000:
        return "Silver"
    return "Bronze"


# ---------------------------------------------------------------------------
# Status room & game
# ---------------------------------------------------------------------------
class RoomStatus:
    WAITING = "WAITING"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class PlayerRole:
    PLAYER = "PLAYER"
    SPECTATOR = "SPECTATOR"


# Arah permainan
DIRECTION_CW = 1     # searah jarum jam
DIRECTION_CCW = -1   # berlawanan
