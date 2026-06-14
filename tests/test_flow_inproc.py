"""Test alur lengkap in-process (tanpa socket nyata) — cepat & deterministik."""
import sys, os, threading, sqlite3, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# shim DB sqlite in-memory
if "mysql.connector" not in sys.modules:
    mysql_mod = types.ModuleType("mysql")
    connector_mod = types.ModuleType("mysql.connector")
    pooling_mod = types.ModuleType("mysql.connector.pooling")
    pooling_mod.MySQLConnectionPool = object
    connector_mod.pooling = pooling_mod
    mysql_mod.connector = connector_mod
    sys.modules["mysql"] = mysql_mod
    sys.modules["mysql.connector"] = connector_mod
    sys.modules["mysql.connector.pooling"] = pooling_mod
import server.db.database as db
_c = sqlite3.connect(":memory:", check_same_thread=False); _c.row_factory = sqlite3.Row
_lk = threading.Lock()
_c.executescript("""
CREATE TABLE users (user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE leaderboard (user_id INTEGER PRIMARY KEY, total_match INT DEFAULT 0, total_win INT DEFAULT 0, total_lose INT DEFAULT 0, total_point INT DEFAULT 0, rank_tier TEXT DEFAULT 'Bronze', win_rate REAL DEFAULT 0, updated_at TEXT);
CREATE TABLE rooms (room_id TEXT PRIMARY KEY, room_code TEXT, host_id INT, status TEXT, created_at TEXT);
CREATE TABLE matches (match_id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT, winner_id INT, player_count INT, match_mode TEXT DEFAULT 'ranked', started_at TEXT, ended_at TEXT);
CREATE TABLE match_players (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INT, user_id INT, finish_position INT, point_change INT, result TEXT);
CREATE TABLE activity_log (log_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, event_type TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id INT, expires_at TEXT);
""")
def conv(q): return q.replace('%s','?').replace('NOW()','CURRENT_TIMESTAMP')
def _ex(q,p=(),commit=False):
    with _lk:
        cur=_c.execute(conv(q),p)
        if commit:_c.commit()
        return cur.lastrowid
def _q1(q,p=()):
    with _lk:
        r=_c.execute(conv(q),p).fetchone(); return dict(r) if r else None
def _qa(q,p=()):
    with _lk:
        return [dict(r) for r in _c.execute(conv(q),p).fetchall()]
db.execute=_ex; db.query_one=_q1; db.query_all=_qa; db.init_pool=lambda:None

from server.services import auth_service, leaderboard_service
auth_service.validate_token=lambda tok:(lambda r:r["user_id"] if r else None)(_q1("SELECT user_id FROM sessions WHERE token=%s",(tok,)))
from server.core.game_engine import GameEngine
from server.core.card import Card
from shared.constants import (
    calc_dynamic_point_delta, MATCH_MODE_RANKED, MATCH_MODE_CLASSIC,
)
import random

# Register & login
ok,uid_a=auth_service.register("andi","1234"); assert ok
ok,uid_b=auth_service.register("budi","1234"); assert ok
ok,uid_c=auth_service.register("citra","1234"); assert ok
ok,res=auth_service.login("andi","1234"); assert ok and res["token"]
assert auth_service.validate_token(res["token"])==uid_a
print("Auth OK: register, login, token, password-hash")

# Simulasi match 3 pemain via engine + proses leaderboard
eng=GameEngine([(uid_a,"andi"),(uid_b,"budi"),(uid_c,"citra")],seed=3)
rng=random.Random(2)
for _ in range(2000):
    if eng.game_over: break
    cur=eng.current_player.user_id; st=eng.get_state(); top=Card.from_dict(st["top_card"])
    pl=[c for c in eng.get_player(cur).hand if c.matches(top,st["active_color"])]
    if pl: eng.play_card(cur,rng.choice(pl),chosen_color=rng.choice(["Red","Green","Blue","Yellow"]))
    else:
        d=eng.draw_card(cur); st2=eng.get_state(); top2=Card.from_dict(st2["top_card"])
        if d and isinstance(d, Card) and d.matches(top2,st2["active_color"]): eng.play_card(cur,d,chosen_color="Red")
        else: eng.pass_turn(cur)
assert eng.game_over
fo=eng.final_ranking()
print("3-player match selesai, finish_order:",fo)
players=[(uid_a,"andi"),(uid_b,"budi"),(uid_c,"citra")]
ranking_details=eng.final_ranking_details()
res_map=leaderboard_service.process_match_result("room-x",fo,players,MATCH_MODE_RANKED,ranking_details)
for pos,uid in enumerate(fo,1):
    own=next((r["remaining_value"] for r in ranking_details if r["user_id"]==uid),0)
    total=sum(r["remaining_value"] for r in ranking_details)
    exp=calc_dynamic_point_delta(3,pos,own,total-own)
    assert res_map[uid]["point_change"]==exp, f"poin salah {uid}"
    assert res_map[uid]["remaining_value"]==own
    print(f"  pos{pos} user{uid}: value {own}, {res_map[uid]['point_change']:+d} -> total {res_map[uid]['total_point']} ({res_map[uid]['rank_tier']})")

before_classic={uid:auth_service.get_stats(uid)["total_point"] for uid,_ in players}
classic_map=leaderboard_service.process_match_result("room-classic",fo,players,MATCH_MODE_CLASSIC,ranking_details)
after_classic={uid:auth_service.get_stats(uid)["total_point"] for uid,_ in players}
assert before_classic==after_classic, "classic tidak boleh mengubah poin"
assert all(r["point_change"]==0 and r["match_mode"]==MATCH_MODE_CLASSIC for r in classic_map.values())
print("Classic match OK: hasil tersimpan, poin/rank tidak berubah")

# Top global terurut poin
top=leaderboard_service.get_top_global(10)
pts=[t["total_point"] for t in top]
assert pts==sorted(pts,reverse=True), "top global tidak terurut"
print("Top global terurut by poin:",[(t['username'],t['total_point']) for t in top])

# Stats
stats=auth_service.get_stats(fo[0])
assert stats["total_match"]==1
print("Stats pemenang:",stats)
print("\n=== IN-PROCESS FLOW TEST PASSED ===")
