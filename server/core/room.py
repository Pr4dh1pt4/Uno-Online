import secrets
import threading
import time

from shared.constants import (
    RoomStatus, PlayerRole, MAX_PLAYERS, MIN_PLAYERS, RECONNECT_GRACE_SECONDS,
    MATCH_MODE_RANKED, MATCH_MODES,
)
from server.core.game_engine import GameEngine

class Member:

    def __init__(self, user_id: int, username: str, conn):
        self.user_id = user_id
        self.username = username
        self.conn = conn
        self.role = PlayerRole.PLAYER
        self.connected = True
        self.disconnect_at: float | None = None

    def to_dict(self) -> dict:
        return {"user_id": self.user_id, "username": self.username,
                "role": self.role, "connected": self.connected}

def normalize_match_mode(value: str | None) -> str:
    value = (value or MATCH_MODE_RANKED).lower()
    return value if value in MATCH_MODES else MATCH_MODE_RANKED

class Room:
    def __init__(self, host_id: int, match_mode: str = MATCH_MODE_RANKED):
        self.room_id = secrets.token_hex(8)
        self.room_code = secrets.token_hex(2).upper()
        self.host_id = host_id
        self.match_mode = normalize_match_mode(match_mode)
        self.status = RoomStatus.WAITING
        self.members: list[Member] = []
        self.engine: GameEngine | None = None
        self.lock = threading.RLock()
        self.created_at = time.time()

    def add_member(self, member: Member) -> bool:
        with self.lock:
            existing = self.get_member(member.user_id)
            if existing:
                existing.conn = member.conn
                existing.connected = True
                existing.disconnect_at = None
                return True
            if len([m for m in self.members if m.role == PlayerRole.PLAYER]) >= MAX_PLAYERS:
                return False
            self.members.append(member)
            return True

    def get_member(self, user_id: int) -> Member | None:
        for m in self.members:
            if m.user_id == user_id:
                return m
        return None

    def remove_member(self, user_id: int) -> None:
        with self.lock:
            self.members = [m for m in self.members if m.user_id != user_id]
            if self.host_id == user_id and self.members:
                self.host_id = self.members[0].user_id

    def players(self) -> list[Member]:
        return [m for m in self.members if m.role == PlayerRole.PLAYER]

    def is_empty(self) -> bool:
        return len(self.members) == 0

    def can_start(self, user_id: int) -> tuple[bool, str]:
        if user_id != self.host_id:
            return False, "not_host"
        if self.status != RoomStatus.WAITING:
            return False, "already_started"
        if len(self.players()) < MIN_PLAYERS:
            return False, "not_enough_players"
        return True, ""

    def start_match(self) -> None:
        with self.lock:
            seats = [(m.user_id, m.username) for m in self.players()]
            self.engine = GameEngine(seats)
            self.status = RoomStatus.PLAYING

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "room_code": self.room_code,
            "host_id": self.host_id,
            "match_mode": self.match_mode,
            "status": self.status,
            "players": [m.to_dict() for m in self.members],
        }

class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.lock = threading.RLock()

    def create_room(self, host_id: int, match_mode: str = MATCH_MODE_RANKED) -> Room:
        with self.lock:
            room = Room(host_id, match_mode)
            self.rooms[room.room_id] = room
            return room

    def find_by_code(self, code: str) -> Room | None:
        code = (code or "").upper()
        with self.lock:
            for room in self.rooms.values():
                if room.room_code == code:
                    return room
            return None

    def get(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def remove(self, room_id: str) -> None:
        with self.lock:
            self.rooms.pop(room_id, None)

    def cleanup_empty(self) -> None:
        with self.lock:
            for rid in [r for r, room in self.rooms.items() if room.is_empty()]:
                self.rooms.pop(rid, None)

class Matchmaker:

    def __init__(self, room_manager: RoomManager):
        self.rm = room_manager
        self.lock = threading.RLock()

    def find_or_create(self, user_id: int, match_mode: str = MATCH_MODE_RANKED) -> Room:
        match_mode = normalize_match_mode(match_mode)
        with self.lock:
            for room in self.rm.rooms.values():
                if (room.status == RoomStatus.WAITING
                        and room.match_mode == match_mode
                        and len(room.players()) < MAX_PLAYERS):
                    return room
            return self.rm.create_room(user_id, match_mode)
