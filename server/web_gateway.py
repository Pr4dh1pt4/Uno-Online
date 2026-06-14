import base64
import hashlib
import json
import mimetypes
import os
import socket
import struct
import threading
import urllib.parse
from pathlib import Path

import config
from shared import protocol
from shared import voice_protocol as vp
from shared.protocol import ProtocolError
from server.services import auth_service

WEB_HOST = os.getenv("UNO_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("UNO_WEB_PORT", "8080"))
GAME_HOST = os.getenv("UNO_GATEWAY_GAME_HOST", "127.0.0.1")
GAME_PORT = int(os.getenv("UNO_GATEWAY_GAME_PORT", str(config.SERVER_PORT)))
STATIC_DIR = Path(__file__).resolve().parent.parent / "web"
ASSET_DIR = Path(__file__).resolve().parent.parent / "client" / "assets"

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

class WebSocketClosed(Exception):
    pass

class BrowserVoiceHub:

    def __init__(self):
        self.lock = threading.Lock()
        self.peers: dict[int, dict] = {}

    def handle(self, peer: dict, ptype: str, payload: dict) -> None:
        if ptype == vp.VOICE_JOIN:
            self.join(peer, payload)
        elif ptype == vp.VOICE_LEAVE:
            self.leave(peer)
        elif ptype == vp.VOICE_PING:
            safe_ws_send(peer["ws"], peer["send_lock"], {"type": "VOICE_PONG", "payload": {}})
        elif ptype == vp.VOICE_AUDIO:
            self.audio(peer, payload)
        elif ptype == "WEBRTC_JOIN":
            self.webrtc_join(peer, payload)
        elif ptype == "WEBRTC_LEAVE":
            self.webrtc_leave(peer)
        elif ptype == "WEBRTC_SIGNAL":
            self.webrtc_signal(peer, payload)

    def join(self, peer: dict, payload: dict) -> None:
        token = payload.get("token", "")
        user_id = auth_service.validate_token(token)
        if not user_id or int(payload.get("user_id") or 0) != user_id:
            safe_ws_send(peer["ws"], peer["send_lock"], {
                "type": vp.VOICE_REJECTED,
                "payload": {"reason": "not_authenticated"},
            })
            return
        room_id = str(payload.get("room_id") or "")
        if not room_id:
            safe_ws_send(peer["ws"], peer["send_lock"], {
                "type": vp.VOICE_REJECTED,
                "payload": {"reason": "not_in_room"},
            })
            return
        with self.lock:
            peer.update({
                "joined": True,
                "room_id": room_id,
                "user_id": user_id,
                "username": str(payload.get("username") or f"Player {user_id}")[:32],
            })
            self.peers[id(peer)] = peer
        safe_ws_send(peer["ws"], peer["send_lock"], {
            "type": vp.VOICE_OK,
            "payload": {"room_id": room_id, "sample_rate": vp.VOICE_SAMPLE_RATE},
        })

    def leave(self, peer: dict) -> None:
        self.webrtc_leave(peer)
        with self.lock:
            self.peers.pop(id(peer), None)
        peer["joined"] = False

    def audio(self, peer: dict, payload: dict) -> None:
        if not peer.get("joined"):
            return
        try:
            vp.decode_audio(payload.get("audio", ""))
        except vp.VoiceProtocolError:
            safe_ws_send(peer["ws"], peer["send_lock"], {
                "type": vp.VOICE_REJECTED,
                "payload": {"reason": "bad_audio"},
            })
            return
        outgoing = {
            "type": vp.VOICE_AUDIO,
            "payload": {
                "user_id": peer.get("user_id"),
                "username": peer.get("username"),
                "seq": payload.get("seq", 0),
                "audio": payload.get("audio", ""),
            },
        }
        with self.lock:
            targets = [
                p for p in self.peers.values()
                if p is not peer and p.get("room_id") == peer.get("room_id")
            ]
        for target in targets:
            safe_ws_send(target["ws"], target["send_lock"], outgoing)

    def webrtc_join(self, peer: dict, payload: dict) -> None:
        token = payload.get("token", "")
        user_id = auth_service.validate_token(token)
        if not user_id or int(payload.get("user_id") or 0) != user_id:
            safe_ws_send(peer["ws"], peer["send_lock"], {
                "type": "WEBRTC_REJECTED",
                "payload": {"reason": "not_authenticated"},
            })
            return
        room_id = str(payload.get("room_id") or "")
        if not room_id:
            safe_ws_send(peer["ws"], peer["send_lock"], {
                "type": "WEBRTC_REJECTED",
                "payload": {"reason": "not_in_room"},
            })
            return

        self.webrtc_leave(peer)
        peer_id = str(id(peer))
        username = str(payload.get("username") or f"Player {user_id}")[:32]
        with self.lock:
            existing = [
                {
                    "peer_id": p["peer_id"],
                    "user_id": p["user_id"],
                    "username": p["username"],
                }
                for p in self.peers.values()
                if p.get("webrtc") and p.get("room_id") == room_id
            ]
            peer.update({
                "webrtc": True,
                "peer_id": peer_id,
                "room_id": room_id,
                "user_id": user_id,
                "username": username,
            })
            self.peers[id(peer)] = peer
            targets = [
                p for p in self.peers.values()
                if p is not peer and p.get("webrtc") and p.get("room_id") == room_id
            ]

        safe_ws_send(peer["ws"], peer["send_lock"], {
            "type": "WEBRTC_READY",
            "payload": {"peer_id": peer_id, "peers": existing},
        })
        joined = {
            "type": "WEBRTC_PEER_JOINED",
            "payload": {"peer_id": peer_id, "user_id": user_id, "username": username},
        }
        for target in targets:
            safe_ws_send(target["ws"], target["send_lock"], joined)

    def webrtc_leave(self, peer: dict) -> None:
        peer_id = peer.get("peer_id")
        room_id = peer.get("room_id")
        if not peer_id or not peer.get("webrtc"):
            return
        with self.lock:
            self.peers.pop(id(peer), None)
            targets = [
                p for p in self.peers.values()
                if p.get("webrtc") and p.get("room_id") == room_id
            ]
        peer["webrtc"] = False
        left = {"type": "WEBRTC_PEER_LEFT", "payload": {"peer_id": peer_id}}
        for target in targets:
            safe_ws_send(target["ws"], target["send_lock"], left)

    def webrtc_signal(self, peer: dict, payload: dict) -> None:
        if not peer.get("webrtc"):
            return
        target_id = str(payload.get("target") or "")
        data = payload.get("data")
        if not target_id or not isinstance(data, dict):
            return
        with self.lock:
            target = next(
                (
                    p for p in self.peers.values()
                    if p.get("webrtc")
                    and p.get("peer_id") == target_id
                    and p.get("room_id") == peer.get("room_id")
                ),
                None,
            )
        if not target:
            return
        safe_ws_send(target["ws"], target["send_lock"], {
            "type": "WEBRTC_SIGNAL",
            "payload": {
                "from": peer.get("peer_id"),
                "user_id": peer.get("user_id"),
                "username": peer.get("username"),
                "data": data,
            },
        })

class WebGateway:
    def __init__(self):
        self.voice = BrowserVoiceHub()

    def start(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((WEB_HOST, WEB_PORT))
        srv.listen(128)
        print(f"Web client listening on http://{WEB_HOST}:{WEB_PORT}", flush=True)
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn, addr) -> None:
        try:
            request = self._read_http_request(conn)
            if not request:
                return
            method, path, headers = request
            if headers.get("upgrade", "").lower() == "websocket":
                self._handle_websocket(conn, headers)
            else:
                self._serve_static(conn, method, path)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _read_http_request(self, conn):
        data = bytearray()
        while b"\r\n\r\n" not in data and len(data) < 16_384:
            chunk = conn.recv(1024)
            if not chunk:
                return None
            data.extend(chunk)
        head = data.decode("iso-8859-1", errors="replace").split("\r\n")
        if not head:
            return None
        parts = head[0].split()
        if len(parts) < 2:
            return None
        headers = {}
        for line in head[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        return parts[0], parts[1], headers

    def _serve_static(self, conn, method: str, path: str) -> None:
        if method != "GET":
            self._http_response(conn, 405, b"Method Not Allowed", "text/plain")
            return
        clean = urllib.parse.unquote(path.split("?", 1)[0]).strip("/")
        if clean in ("", "/"):
            clean = "index.html"
        base = ASSET_DIR if clean.startswith("assets/") else STATIC_DIR
        rel = clean[len("assets/"):] if clean.startswith("assets/") else clean
        target = (base / rel).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.is_file():
            self._http_response(conn, 404, b"Not Found", "text/plain")
            return
        body = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        cache = "public, max-age=86400" if clean.startswith("assets/") else "no-cache"
        self._http_response(conn, 200, body, ctype, cache)

    def _http_response(self, conn, status: int, body: bytes, ctype: str, cache: str = "no-cache") -> None:
        reason = {200: "OK", 404: "Not Found", 405: "Method Not Allowed"}.get(status, "OK")
        header = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Cache-Control: {cache}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        conn.sendall(header + body)

    def _handle_websocket(self, conn, headers: dict) -> None:
        key = headers.get("sec-websocket-key")
        if not key:
            return
        accept = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()).decode("ascii")
        conn.sendall(
            ("HTTP/1.1 101 Switching Protocols\r\n"
             "Upgrade: websocket\r\n"
             "Connection: Upgrade\r\n"
             f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode("ascii")
        )

        game = socket.create_connection((GAME_HOST, GAME_PORT), timeout=10)
        game.settimeout(None)
        stop = threading.Event()
        send_lock = threading.Lock()
        peer = {"ws": conn, "send_lock": send_lock, "joined": False}
        threading.Thread(
            target=self._game_to_ws,
            args=(game, conn, send_lock, stop),
            daemon=True,
        ).start()
        seq = 0
        try:
            while not stop.is_set():
                msg = ws_recv_text(conn)
                pkt = json.loads(msg)
                if not isinstance(pkt, dict):
                    continue
                ptype = pkt.get("type", "")
                payload = pkt.get("payload", {})
                if ptype in (
                    vp.VOICE_JOIN,
                    vp.VOICE_LEAVE,
                    vp.VOICE_PING,
                    vp.VOICE_AUDIO,
                    "WEBRTC_JOIN",
                    "WEBRTC_LEAVE",
                    "WEBRTC_SIGNAL",
                ):
                    self.voice.handle(peer, ptype, payload if isinstance(payload, dict) else {})
                    continue
                seq += 1
                protocol.send_packet(game, ptype, payload if isinstance(payload, dict) else {}, seq)
        except (OSError, WebSocketClosed, ProtocolError, json.JSONDecodeError):
            pass
        finally:
            stop.set()
            self.voice.leave(peer)
            try:
                game.close()
            except OSError:
                pass

    def _game_to_ws(self, game, ws, send_lock: threading.Lock, stop: threading.Event) -> None:
        try:
            while not stop.is_set():
                pkt = protocol.recv_packet(game)
                if pkt is None:
                    break
                safe_ws_send(ws, send_lock, pkt)
        except (OSError, ProtocolError):
            pass
        finally:
            stop.set()

def _recv_exact(sock, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise WebSocketClosed()
        buf.extend(chunk)
    return bytes(buf)

def ws_recv_text(sock) -> str:
    b1, b2 = _recv_exact(sock, 2)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if opcode == 0x8:
        raise WebSocketClosed()
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else b""
    payload = bytearray(_recv_exact(sock, length))
    if masked:
        for i in range(len(payload)):
            payload[i] ^= mask[i % 4]
    if opcode != 0x1:
        return ""
    return payload.decode("utf-8")

def ws_send_text(sock, text: str) -> None:
    data = text.encode("utf-8")
    header = bytearray([0x81])
    if len(data) < 126:
        header.append(len(data))
    elif len(data) <= 0xFFFF:
        header.append(126)
        header.extend(struct.pack(">H", len(data)))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", len(data)))
    sock.sendall(bytes(header) + data)

def safe_ws_send(sock, lock: threading.Lock, pkt: dict) -> None:
    with lock:
        ws_send_text(sock, json.dumps(pkt, separators=(",", ":")))

def main():
    WebGateway().start()

if __name__ == "__main__":
    main()
