import sys
import types

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

db.execute = lambda *a, **k: 1

from server.core.room import Member
from server.socket_server import ClientSession, SocketServer

class FakeConn:
    def __init__(self):
        self.sent = []
        self.closed = False

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True

def test_login_takeover_keeps_player_in_match():
    srv = SocketServer()
    room = srv.rm.create_room(1)

    old = ClientSession(FakeConn(), ("old", 1))
    old.user_id = 1
    old.username = "andi"
    old.room = room
    room.add_member(Member(1, "andi", old.conn))
    room.add_member(Member(2, "budi", FakeConn()))
    room.start_match()
    srv._register_session(old)

    new = ClientSession(FakeConn(), ("new", 2))
    new.user_id = 1
    new.username = "andi"
    srv._register_session(new)

    resume = srv._takeover_playing_session(new)
    member = room.get_member(1)

    assert resume["room_id"] == room.room_id
    assert new.room is room
    assert old.room is None
    assert old._closed
    assert member.conn is new.conn
    assert member.connected is True
    assert not room.engine.game_over
    assert room.engine.get_player(1).is_active

def test_session_resume_rebinds_disconnected_player():
    srv = SocketServer()
    room = srv.rm.create_room(1)

    old = ClientSession(FakeConn(), ("old", 1))
    old.user_id = 1
    old.username = "andi"
    old.room = room
    room.add_member(Member(1, "andi", old.conn))
    room.add_member(Member(2, "budi", FakeConn()))
    room.start_match()

    member = room.get_member(1)
    member.connected = False
    member.disconnect_at = 123.0

    new = ClientSession(FakeConn(), ("new", 2))
    new.user_id = 1
    new.username = "andi"
    srv._register_session(new)

    resume = srv._resume_disconnected_session(new)

    assert resume["room_id"] == room.room_id
    assert new.room is room
    assert member.conn is new.conn
    assert member.connected is True
    assert member.disconnect_at is None
    assert not room.engine.game_over
    assert room.engine.get_player(1).is_active
