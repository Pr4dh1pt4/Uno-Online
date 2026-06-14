"""
SocketServer — server TCP authoritative dengan satu thread per client.

Bertanggung jawab atas: menerima koneksi, autentikasi, routing paket ke
handler, broadcast state, spectator mode, reconnect handling, dan logging.
"""
import socket
import threading
import time

import config
from shared import protocol
from shared.protocol import ProtocolError
from shared.packet_types import C2S, S2C, RejectReason
from shared.constants import (
    RoomStatus, PlayerRole, MIN_PLAYERS, RECONNECT_GRACE_SECONDS,
)
from server.core.card import Card
from server.core.room import RoomManager, Matchmaker, Member, normalize_match_mode
from server.packet import validator
from server.services import auth_service, leaderboard_service
from server.utils import logger
from server.voice_server import VoiceServer


class ClientSession:
    """State per koneksi client."""

    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.user_id: int | None = None
        self.username: str | None = None
        self.room = None                      # Room saat ini
        self.seq_tracker = validator.ConnSeqTracker()
        self.send_lock = threading.Lock()
        self._closed = False

    @property
    def authenticated(self) -> bool:
        return self.user_id is not None

    def send(self, ptype: str, payload: dict | None = None) -> None:
        with self.send_lock:
            try:
                if not self._closed:
                    protocol.send_packet(self.conn, ptype, payload)
            except OSError:
                pass

    def force_close(self) -> None:
        """Force close the connection (used when kicking duplicate sessions)."""
        self._closed = True
        try:
            self.conn.close()
        except OSError:
            pass


class SocketServer:
    def __init__(self):
        self.rm = RoomManager()
        self.matchmaker = Matchmaker(self.rm)
        # registry user_id -> semua koneksi login aktif.
        # Broadcast room memilih session yang memang sedang terikat ke room tersebut.
        self.sessions: dict[int, set[ClientSession]] = {}
        self.sessions_lock = threading.Lock()
        self.voice_server = VoiceServer(self.rm)
        self._running = False

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((config.SERVER_HOST, config.SERVER_PORT))
        srv.listen(64)
        self._running = True
        logger.info(f"Server UNO listening on {config.SERVER_HOST}:{config.SERVER_PORT}")
        self.voice_server.start_background()
        threading.Thread(target=self._reconnect_reaper, daemon=True).start()
        try:
            while self._running:
                conn, addr = srv.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            logger.info("Server dihentikan.")
        finally:
            srv.close()

    # -- loop per client ----------------------------------------------------
    def _handle_client(self, conn, addr):
        sess = ClientSession(conn, addr)
        logger.info(f"Koneksi baru dari {addr}")
        try:
            while True:
                try:
                    pkt = protocol.recv_packet(conn)
                except ProtocolError as e:
                    logger.warning(f"Invalid packet dari {addr}: {e}")
                    sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.INVALID_PACKET})
                    continue
                if pkt is None:
                    break  # koneksi tertutup
                self._route(sess, pkt)
        except OSError:
            pass
        finally:
            self._on_disconnect(sess)
            conn.close()
            logger.info(f"Koneksi {addr} ditutup")

    # -- routing ------------------------------------------------------------
    def _route(self, sess: ClientSession, pkt: dict):
        result = validator.run_pipeline(pkt, sess.authenticated, sess.seq_tracker)
        if not result.ok:
            logger.activity(sess.user_id, "INVALID_PACKET", {"reason": result.reason})
            sess.send(S2C.ACTION_REJECTED, {"reason": result.reason})
            return

        ptype = pkt["type"]
        payload = pkt["payload"]
        handler = {
            C2S.REGISTER_REQ: self._h_register,
            C2S.LOGIN_REQ: self._h_login,
            C2S.SESSION_LOGIN_REQ: self._h_session_login,
            C2S.PING: self._h_ping,
            C2S.CREATE_ROOM_REQ: self._h_create_room,
            C2S.JOIN_ROOM_REQ: self._h_join_room,
            C2S.MATCHMAKE_REQ: self._h_matchmake,
            C2S.START_MATCH_REQ: self._h_start_match,
            C2S.PLAY_CARD: self._h_play_card,
            C2S.DRAW_CARD: self._h_draw_card,
            C2S.CALL_UNO: self._h_call_uno,
            C2S.LEAVE_ROOM: self._h_leave_room,
            C2S.RECONNECT_REQ: self._h_reconnect,
            C2S.GET_LEADERBOARD: self._h_get_leaderboard,
            C2S.GET_TOP_GLOBAL: self._h_get_top_global,
            C2S.GET_STATS: self._h_get_stats,
            C2S.GET_MATCH_HISTORY: self._h_get_match_history,
        }.get(ptype)
        if handler:
            handler(sess, payload)

    # -- handlers: auth -----------------------------------------------------
    def _h_register(self, sess, payload):
        ok, res = auth_service.register(payload.get("username", ""), payload.get("password", ""))
        if ok:
            logger.activity(res, "REGISTER", {"username": payload.get("username")})
            sess.send(S2C.REGISTER_OK, {"user_id": res})
        else:
            sess.send(S2C.REGISTER_FAIL, {"reason": res})

    def _h_login(self, sess, payload):
        ok, res = auth_service.login(payload.get("username", ""), payload.get("password", ""))
        if not ok:
            sess.send(S2C.LOGIN_FAIL, {"reason": res})
            return
        sess.user_id = res["user_id"]
        sess.username = res["username"]

        self._register_session(sess)
        resume = self._takeover_playing_session(sess)
        logger.activity(sess.user_id, "LOGIN", {"username": sess.username})
        if resume:
            res["resume"] = resume
        sess.send(S2C.LOGIN_OK, res)

    def _h_session_login(self, sess, payload):
        ok, res = auth_service.login_with_token(payload.get("token", ""))
        if not ok:
            sess.send(S2C.LOGIN_FAIL, {"reason": res})
            return
        sess.user_id = res["user_id"]
        sess.username = res["username"]

        self._register_session(sess)
        resume = self._takeover_playing_session(sess) or self._resume_disconnected_session(sess)
        logger.activity(sess.user_id, "SESSION_LOGIN", {"username": sess.username})
        if resume:
            res["resume"] = resume
        sess.send(S2C.LOGIN_OK, res)

    def _h_ping(self, sess, payload):
        sess.send(S2C.PONG, {"client_ts": payload.get("client_ts"),
                             "server_ts": round(time.time(), 3)})

    # -- handlers: room -----------------------------------------------------
    def _h_create_room(self, sess, payload):
        if sess.room:
            self._leave_room(sess)
        match_mode = normalize_match_mode(payload.get("match_mode"))
        room = self.rm.create_room(sess.user_id, match_mode)
        member = Member(sess.user_id, sess.username, sess.conn)
        room.add_member(member)
        sess.room = room
        logger.activity(sess.user_id, "CREATE_ROOM", {
            "room_code": room.room_code,
            "match_mode": room.match_mode,
        })
        sess.send(S2C.ROOM_CREATED, {
            "room_id": room.room_id,
            "room_code": room.room_code,
            "match_mode": room.match_mode,
        })
        self._broadcast_room(room, S2C.ROOM_UPDATE, room.to_dict())

    def _h_join_room(self, sess, payload):
        room = self.rm.find_by_code(payload.get("room_code", ""))
        if not room:
            sess.send(S2C.JOIN_FAIL, {"reason": RejectReason.ROOM_NOT_FOUND})
            return
        if room.status != RoomStatus.WAITING:
            sess.send(S2C.JOIN_FAIL, {"reason": "already_started"})
            return
        # Keluar dari room lama dulu bila berpindah, supaya satu akun tidak
        # tampil di dua room sekaligus.
        if sess.room and sess.room is not room:
            self._leave_room(sess)
        member = Member(sess.user_id, sess.username, sess.conn)
        if not room.add_member(member):
            sess.send(S2C.JOIN_FAIL, {"reason": RejectReason.ROOM_FULL})
            return
        sess.room = room
        logger.activity(sess.user_id, "JOIN_ROOM", {"room_code": room.room_code})
        sess.send(S2C.JOIN_OK, room.to_dict())
        self._broadcast_room(room, S2C.ROOM_UPDATE, room.to_dict())

    def _h_matchmake(self, sess, payload):
        if sess.room:
            self._leave_room(sess)
        match_mode = normalize_match_mode(payload.get("match_mode"))
        room = self.matchmaker.find_or_create(sess.user_id, match_mode)
        member = Member(sess.user_id, sess.username, sess.conn)
        room.add_member(member)
        sess.room = room
        logger.activity(sess.user_id, "MATCHMAKE", {
            "room_code": room.room_code,
            "match_mode": room.match_mode,
        })
        sess.send(S2C.MATCH_FOUND, room.to_dict())
        self._broadcast_room(room, S2C.ROOM_UPDATE, room.to_dict())

    def _h_start_match(self, sess, payload):
        room = sess.room
        if not room:
            return
        can, reason = room.can_start(sess.user_id)
        if not can:
            sess.send(S2C.ACTION_REJECTED, {"reason": reason})
            return
        room.start_match()
        logger.activity(sess.user_id, "START_MATCH", {"room_id": room.room_id})
        # kirim GAME_START dgn tangan masing-masing
        for m in room.players():
            s = self._sess_of(m.user_id, room)
            if s:
                s.send(S2C.GAME_START, {
                    "hand": room.engine.get_hand(m.user_id),
                    "state": room.engine.get_state(),
                })

    # -- handlers: gameplay -------------------------------------------------
    def _h_play_card(self, sess, payload):
        room = sess.room
        if not room or not room.engine:
            return
        member = room.get_member(sess.user_id)
        # validasi role (spectator tidak boleh aksi)
        if member and member.role == PlayerRole.SPECTATOR:
            sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.SPECTATOR_CANNOT_ACT})
            return
        raw_cards = payload.get("cards")
        if isinstance(raw_cards, list) and raw_cards:
            cards = [Card.from_dict(c) for c in raw_cards]
        else:
            cards = [Card.from_dict(payload.get("card", {}))]
        card = cards[0]
        chosen = payload.get("chosen_color")
        ok, reason = room.engine.is_valid_multi_play(sess.user_id, cards)
        if not ok:
            reason_map = {
                "not_your_turn": RejectReason.NOT_YOUR_TURN,
                "must_stack_or_draw": RejectReason.MUST_STACK_OR_DRAW,
            }
            rj = reason_map.get(reason, RejectReason.INVALID_CARD)
            sess.send(S2C.ACTION_REJECTED, {"reason": rj})
            return
        if len(cards) == 1:
            room.engine.play_card(sess.user_id, card, chosen)
            logger.activity(sess.user_id, "PLAY_CARD", {"card": card.to_dict()})
        else:
            effect = room.engine.play_cards(sess.user_id, cards)
            logger.activity(sess.user_id, "PLAY_CARDS", effect)

        # cek pemenang
        player = room.engine.get_player(sess.user_id)
        if player and player.has_won:
            if member:
                member.role = PlayerRole.SPECTATOR
            sess.send(S2C.PLAYER_WIN, {"user_id": sess.user_id})
            sess.send(S2C.ENTER_SPECTATOR, {"scoreboard": room.engine.get_state()["scoreboard"]})

        self._broadcast_state(room)
        if room.engine.game_over:
            self._finish_match(room)

    def _h_draw_card(self, sess, payload):
        room = sess.room
        if not room or not room.engine:
            return
        member = room.get_member(sess.user_id)
        if member and member.role == PlayerRole.SPECTATOR:
            sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.SPECTATOR_CANNOT_ACT})
            return
        if room.engine.current_player.user_id != sess.user_id:
            sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.NOT_YOUR_TURN})
            return

        result = room.engine.draw_card(sess.user_id)

        if result is None:
            # Sudah menarik kartu di giliran ini -> tolak draw kedua.
            sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.ALREADY_DREW})
            return

        logger.activity(sess.user_id, "DRAW_CARD", {})

        if isinstance(result, list):
            # Stacked draw: pemain mengambil semua akumulasi, giliran sudah di-skip oleh engine
            sess.send(S2C.DRAW_STACK_RESULT, {
                "cards": [c.to_dict() for c in result],
                "count": len(result),
            })
        elif isinstance(result, Card):
            # Draw biasa 1 kartu
            sess.send(S2C.DRAW_RESULT, {"card": result.to_dict()})
            # jika kartu hasil draw tidak bisa dimainkan -> auto pass
            st = room.engine.get_state()
            top = Card.from_dict(st["top_card"])
            if not result.matches(top, st["active_color"]):
                room.engine.pass_turn(sess.user_id)

        self._broadcast_state(room)

    def _h_call_uno(self, sess, payload):
        room = sess.room
        if not room or not room.engine:
            return
        mode = "catch" if payload.get("mode") == "catch" else "self"
        ok, action, target_uid, penalty = room.engine.call_uno(sess.user_id, mode)

        if action == "noop":
            # Tombol UNO ditekan saat belum waktunya — tidak ada efek.
            return

        if action == "self_call":
            # Pemain berhasil memanggil UNO untuk dirinya sendiri
            sess.send(S2C.UNO_OK, {})
            self._broadcast_room(room, S2C.UNO_ANNOUNCE, {"user_id": sess.user_id})

        elif action == "catch":
            # Pemain menangkap lawan yang lupa call UNO
            # Kirim penalti ke pemain yang tertangkap
            caught_sess = self._sess_of(target_uid, room)
            if caught_sess:
                caught_sess.send(S2C.UNO_PENALTY, {
                    "cards": [c.to_dict() for c in penalty],
                    "reason": "caught",
                })
            # Beritahu semua pemain tentang tangkapan UNO
            caught_name = ""
            for p in room.engine.players:
                if p.user_id == target_uid:
                    caught_name = p.username
                    break
            self._broadcast_room(room, S2C.UNO_CATCH, {
                "catcher_id": sess.user_id,
                "caught_id": target_uid,
                "caught_name": caught_name,
            })
            self._broadcast_state(room)

        elif action == "false_call":
            # Pemanggil kena penalti karena call UNO sembarangan
            sess.send(S2C.UNO_PENALTY, {
                "cards": [c.to_dict() for c in penalty],
                "reason": "false_call",
            })
            self._broadcast_state(room)

        logger.activity(sess.user_id, "CALL_UNO", {
            "action": action, "target": target_uid,
        })

    def _h_leave_room(self, sess, payload):
        self._leave_room(sess)
        sess.send(S2C.LEFT_ROOM, {})

    # -- handlers: reconnect ------------------------------------------------
    def _h_reconnect(self, sess, payload):
        token = payload.get("token", "")
        room_id = payload.get("room_id", "")
        user_id = auth_service.validate_token(token)
        if not user_id:
            sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.NOT_AUTHENTICATED})
            return
        room = self.rm.get(room_id)
        if not room:
            sess.send(S2C.ACTION_REJECTED, {"reason": RejectReason.ROOM_NOT_FOUND})
            return
        member = room.get_member(user_id)
        if not member:
            sess.send(S2C.ACTION_REJECTED, {"reason": "not_in_room"})
            return
        # rebind koneksi
        sess.user_id = user_id
        sess.username = member.username
        sess.room = room
        member.conn = sess.conn
        member.connected = True
        member.disconnect_at = None
        self._register_session(sess)
        logger.activity(user_id, "RECONNECT", {"room_id": room_id})
        hand = room.engine.get_hand(user_id) if room.engine else []
        sess.send(S2C.RECONNECT_OK, {
            "full_state": room.engine.get_state() if room.engine else None,
            "hand": hand,
            "role": member.role,
        })
        self._broadcast_state(room)

    # -- handlers: leaderboard/stats ---------------------------------------
    def _h_get_leaderboard(self, sess, payload):
        limit = int(payload.get("limit", 10))
        sess.send(S2C.LEADERBOARD, {"entries": leaderboard_service.get_leaderboard(limit)})

    def _h_get_top_global(self, sess, payload):
        limit = int(payload.get("limit", 10))
        sess.send(S2C.TOP_GLOBAL, {"entries": leaderboard_service.get_top_global(limit)})

    def _h_get_stats(self, sess, payload):
        uid = payload.get("user_id") or sess.user_id
        sess.send(S2C.STATS, auth_service.get_stats(uid))

    def _h_get_match_history(self, sess, payload):
        uid = payload.get("user_id") or sess.user_id
        limit = max(1, min(50, int(payload.get("limit", 20))))
        sess.send(S2C.MATCH_HISTORY, {
            "entries": leaderboard_service.get_match_history(uid, limit),
        })

    # -- akhir match --------------------------------------------------------
    def _finish_match(self, room):
        if room.status == RoomStatus.FINISHED:
            return
        room.status = RoomStatus.FINISHED
        finish_order = room.engine.final_ranking()
        ranking_details = room.engine.final_ranking_details()
        players = [(p.user_id, p.username) for p in room.engine.players]
        result_map = leaderboard_service.process_match_result(
            room.room_id, finish_order, players, room.match_mode, ranking_details
        )
        # Konversi key ke string untuk konsistensi JSON serialization
        result_map_str = {str(k): v for k, v in result_map.items()}
        # Sertakan nama pemain agar client tidak perlu bergantung pada game_state
        player_names = {str(uid): uname for uid, uname in players}
        # kirim hasil ke semua member (player + spectator)
        payload = {
            "finish_order": finish_order,
            "ranking_details": ranking_details,
            "player_count": len(players),
            "match_mode": room.match_mode,
            "results": result_map_str,
            "player_names": player_names,
            "leaderboard": leaderboard_service.get_leaderboard(10),
        }
        self._broadcast_room(room, S2C.MATCH_RESULT, payload)
        logger.activity(None, "MATCH_END", {
            "room_id": room.room_id,
            "match_mode": room.match_mode,
            "ranking": finish_order,
        })

    # -- broadcast helpers --------------------------------------------------
    def _broadcast_room(self, room, ptype: str, payload: dict):
        for m in list(room.members):
            s = self._sess_of(m.user_id, room)
            if s and m.connected:
                s.send(ptype, payload)

    def _broadcast_state(self, room):
        if not room.engine:
            return
        state = room.engine.get_state()
        for m in list(room.members):
            s = self._sess_of(m.user_id, room)
            if not s or not m.connected:
                continue
            # player menerima tangannya sendiri; spectator hanya state
            data = {"state": state}
            if m.role == PlayerRole.PLAYER:
                data["hand"] = room.engine.get_hand(m.user_id)
            s.send(S2C.STATE_UPDATE, data)

    def _register_session(self, sess: ClientSession) -> None:
        if sess.user_id is None:
            return
        with self.sessions_lock:
            self.sessions.setdefault(sess.user_id, set()).add(sess)

    def _unregister_session(self, sess: ClientSession) -> None:
        if sess.user_id is None:
            return
        with self.sessions_lock:
            sessions = self.sessions.get(sess.user_id)
            if not sessions:
                return
            sessions.discard(sess)
            if not sessions:
                self.sessions.pop(sess.user_id, None)

    def _sessions_of(self, user_id: int) -> list[ClientSession]:
        with self.sessions_lock:
            return list(self.sessions.get(user_id, set()))

    def _sess_of(self, user_id: int, room=None):
        sessions = self._sessions_of(user_id)
        if room is not None:
            for s in sessions:
                if s.room is room and not s._closed:
                    return s
            return None
        for s in sessions:
            if not s._closed:
                return s
        return None

    def _takeover_playing_session(self, new_sess: ClientSession) -> dict | None:
        """Pindahkan kontrol match dari session lama ke session login baru."""
        old_sessions = [
            s for s in self._sessions_of(new_sess.user_id)
            if s is not new_sess
            and s.room is not None
            and s.room.status == RoomStatus.PLAYING
            and s.room.engine is not None
        ]
        if not old_sessions:
            return None

        old = old_sessions[0]
        room = old.room
        member = room.get_member(new_sess.user_id)
        if not member:
            return None

        member.conn = new_sess.conn
        member.connected = True
        member.disconnect_at = None
        new_sess.room = room

        # Putuskan sesi lama tanpa memanggil _leave_room, supaya player tidak kalah.
        old.room = None
        logger.activity(new_sess.user_id, "SESSION_TAKEOVER", {"room_id": room.room_id})
        old.send(S2C.FORCE_LOGOUT, {
            "reason": "Akun ini login dari perangkat lain dan mengambil alih match."
        })
        old.force_close()

        for extra in old_sessions[1:]:
            extra.room = None
            extra.send(S2C.FORCE_LOGOUT, {
                "reason": "Akun ini login dari perangkat lain."
            })
            extra.force_close()

        self._broadcast_state(room)
        return self._resume_payload(room, member)

    def _resume_payload(self, room, member: Member) -> dict:
        hand = room.engine.get_hand(member.user_id) if room.engine else []
        return {
            "room": room.to_dict(),
            "room_id": room.room_id,
            "room_code": room.room_code,
            "host_id": room.host_id,
            "match_mode": room.match_mode,
            "role": member.role,
            "state": room.engine.get_state() if room.engine else None,
            "hand": hand,
        }

    def _resume_disconnected_session(self, sess: ClientSession) -> dict | None:
        """Resume a playing room after browser refresh or short network drop."""
        for room in list(self.rm.rooms.values()):
            if room.status != RoomStatus.PLAYING or not room.engine:
                continue
            member = room.get_member(sess.user_id)
            if not member:
                continue
            member.conn = sess.conn
            member.connected = True
            member.disconnect_at = None
            sess.room = room
            logger.activity(sess.user_id, "SESSION_RESUME", {"room_id": room.room_id})
            self._broadcast_state(room)
            return self._resume_payload(room, member)
        return None

    # -- disconnect & reconnect grace --------------------------------------
    def _on_disconnect(self, sess: ClientSession):
        if not sess.user_id:
            return
        room = sess.room
        if room:
            member = room.get_member(sess.user_id)
            if member:
                member.connected = False
                member.disconnect_at = time.time()
                logger.activity(sess.user_id, "DISCONNECT", {"room_id": room.room_id})
                if room.status == RoomStatus.PLAYING and room.engine:
                    self._broadcast_state(room)
                elif room.status == RoomStatus.WAITING:
                    # di lobby, langsung keluarkan
                    self._leave_room(sess)
        self._unregister_session(sess)

    def _leave_room(self, sess: ClientSession):
        room = sess.room
        if not room:
            return
        uid = sess.user_id
        if room.engine and room.status == RoomStatus.PLAYING:
            room.engine.remove_player(uid)
        room.remove_member(uid)
        sess.room = None
        logger.activity(uid, "LEAVE_ROOM", {"room_id": room.room_id})
        if room.is_empty():
            self.rm.remove(room.room_id)
        else:
            self._broadcast_room(room, S2C.ROOM_UPDATE, room.to_dict())
            if room.status == RoomStatus.PLAYING and room.engine:
                self._broadcast_state(room)
            if room.engine and room.engine.game_over:
                self._finish_match(room)

    def _reconnect_reaper(self):
        """Thread: keluarkan pemain yang melewati grace period reconnect."""
        while self._running:
            time.sleep(2)
            now = time.time()
            for room in list(self.rm.rooms.values()):
                if room.status != RoomStatus.PLAYING or not room.engine:
                    continue
                for m in list(room.members):
                    if (not m.connected and m.disconnect_at
                            and now - m.disconnect_at > RECONNECT_GRACE_SECONDS):
                        logger.activity(m.user_id, "RECONNECT_TIMEOUT", {"room_id": room.room_id})
                        room.engine.remove_player(m.user_id)
                        room.remove_member(m.user_id)
                        self._broadcast_room(room, S2C.ROOM_UPDATE, room.to_dict())
                        self._broadcast_state(room)
                        if room.engine.game_over:
                            self._finish_match(room)
