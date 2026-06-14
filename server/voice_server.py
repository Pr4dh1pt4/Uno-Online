"""UDP voice relay untuk live voice chat per room."""
import socket
import threading
import time

import config
from shared import voice_protocol as vp
from server.services import auth_service
from server.utils import logger


class VoicePeer:
    def __init__(self, user_id: int, username: str, room_id: str, addr):
        self.user_id = user_id
        self.username = username
        self.room_id = room_id
        self.addr = addr
        self.last_seq = -1
        self.last_seen = time.time()


class VoiceServer:
    """Relay UDP: validasi peer lalu broadcast audio ke peer room yang sama."""

    def __init__(self, room_manager):
        self.rm = room_manager
        self.peers_by_addr: dict[tuple[str, int], VoicePeer] = {}
        self.peers_by_user: dict[int, tuple[str, int]] = {}
        self.lock = threading.RLock()
        self._running = False
        self.sock: socket.socket | None = None

    def start_background(self) -> None:
        threading.Thread(target=self.start, daemon=True).start()

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((config.SERVER_HOST, config.VOICE_PORT))
        self._running = True
        logger.info(f"Voice UDP relay listening on {config.SERVER_HOST}:{config.VOICE_PORT}")
        threading.Thread(target=self._reap_stale_peers, daemon=True).start()
        while self._running:
            try:
                data, addr = self.sock.recvfrom(vp.MAX_VOICE_PACKET_SIZE + 1)
            except OSError:
                break
            self._handle(data, addr)

    def _handle(self, data: bytes, addr) -> None:
        try:
            pkt = vp.decode_packet(data)
        except vp.VoiceProtocolError as e:
            logger.warning(f"Invalid voice packet dari {addr}: {e}")
            return

        ptype = pkt["type"]
        payload = pkt["payload"]
        if ptype == vp.VOICE_JOIN:
            self._join(payload, addr)
        elif ptype == vp.VOICE_LEAVE:
            self._leave(addr)
        elif ptype == vp.VOICE_PING:
            self._ping(addr)
        elif ptype == vp.VOICE_AUDIO:
            self._audio(payload, addr)

    def _join(self, payload: dict, addr) -> None:
        token = payload.get("token", "")
        room_id = payload.get("room_id", "")
        username = payload.get("username", "")
        user_id = auth_service.validate_token(token)
        if not user_id:
            self._send(addr, vp.VOICE_REJECTED, {"reason": "not_authenticated"})
            return

        room = self.rm.get(room_id)
        if not room or not room.get_member(user_id):
            self._send(addr, vp.VOICE_REJECTED, {"reason": "not_in_room"})
            return

        with self.lock:
            old_addr = self.peers_by_user.get(user_id)
            if old_addr and old_addr != addr:
                self.peers_by_addr.pop(old_addr, None)
            peer = VoicePeer(user_id, username, room_id, addr)
            self.peers_by_addr[addr] = peer
            self.peers_by_user[user_id] = addr

        logger.activity(user_id, "VOICE_JOIN", {"room_id": room_id})
        self._send(addr, vp.VOICE_OK, {
            "sample_rate": vp.VOICE_SAMPLE_RATE,
            "channels": vp.VOICE_CHANNELS,
            "frame_ms": vp.VOICE_FRAME_MS,
        })

    def _leave(self, addr) -> None:
        with self.lock:
            peer = self.peers_by_addr.pop(addr, None)
            if peer:
                self.peers_by_user.pop(peer.user_id, None)
        if peer:
            logger.activity(peer.user_id, "VOICE_LEAVE", {"room_id": peer.room_id})

    def _ping(self, addr) -> None:
        with self.lock:
            peer = self.peers_by_addr.get(addr)
            if peer:
                peer.last_seen = time.time()

    def _audio(self, payload: dict, addr) -> None:
        with self.lock:
            peer = self.peers_by_addr.get(addr)
        if not peer:
            return
        room = self.rm.get(peer.room_id)
        if not room or not room.get_member(peer.user_id):
            self._leave(addr)
            return

        seq = payload.get("seq")
        if not isinstance(seq, int) or seq <= peer.last_seq:
            return
        try:
            raw = vp.decode_audio(payload.get("audio", ""))
        except vp.VoiceProtocolError as e:
            logger.activity(peer.user_id, "INVALID_VOICE_PACKET", {"reason": str(e)})
            return
        if not raw:
            return

        peer.last_seq = seq
        peer.last_seen = time.time()
        out = vp.encode_packet(vp.VOICE_AUDIO, {
            "user_id": peer.user_id,
            "username": peer.username,
            "seq": seq,
            "audio": vp.encode_audio(raw),
        })
        self._relay(peer, out)

    def _relay(self, sender: VoicePeer, data: bytes) -> None:
        room = self.rm.get(sender.room_id)
        with self.lock:
            peers = list(self.peers_by_addr.values())
        for peer in peers:
            if peer.user_id == sender.user_id or peer.room_id != sender.room_id:
                continue
            if room and not room.get_member(peer.user_id):
                continue
            try:
                self.sock.sendto(data, peer.addr)
            except OSError:
                pass

    def _send(self, addr, ptype: str, payload: dict) -> None:
        try:
            self.sock.sendto(vp.encode_packet(ptype, payload), addr)
        except OSError:
            pass

    def _reap_stale_peers(self) -> None:
        while self._running:
            time.sleep(5)
            cutoff = time.time() - 15
            with self.lock:
                stale = [addr for addr, peer in self.peers_by_addr.items()
                         if peer.last_seen < cutoff]
                for addr in stale:
                    peer = self.peers_by_addr.pop(addr, None)
                    if peer:
                        self.peers_by_user.pop(peer.user_id, None)
