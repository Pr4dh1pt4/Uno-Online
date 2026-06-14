"""
ClientNetwork — koneksi TCP ke server dengan thread receiver.

Paket masuk dimasukkan ke queue thread-safe agar bisa dikonsumsi oleh
game loop Pygame tanpa blocking. Ping diukur lewat PING/PONG.
"""
import socket
import threading
import time
import queue

import config
from shared import protocol
from shared.protocol import ProtocolError
from shared.packet_types import C2S, S2C


class ClientNetwork:
    def __init__(self):
        self.sock: socket.socket | None = None
        self.inbox: "queue.Queue[dict]" = queue.Queue()
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._running = False
        self.connected = False
        self.ping_ms = 0
        self._last_ping_sent = 0.0

    def connect(self, host: str | None = None, port: int | None = None) -> bool:
        host = host or config.CLIENT_CONNECT_HOST
        port = port or config.SERVER_PORT
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self.connected = True
            self._running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            threading.Thread(target=self._ping_loop, daemon=True).start()
            return True
        except OSError:
            self.connected = False
            return False

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def send(self, ptype: str, payload: dict | None = None) -> None:
        if not self.connected or not self.sock:
            return
        try:
            protocol.send_packet(self.sock, ptype, payload, self._next_seq())
        except OSError:
            self.connected = False

    def _recv_loop(self) -> None:
        while self._running:
            try:
                pkt = protocol.recv_packet(self.sock)
            except (ProtocolError, OSError):
                break
            if pkt is None:
                break
            # tangani PONG di sini untuk update ping
            if pkt.get("type") == S2C.PONG:
                cts = pkt["payload"].get("client_ts")
                if cts:
                    self.ping_ms = int((time.time() - cts) * 1000)
                continue
            self.inbox.put(pkt)
        self.connected = False

    def _ping_loop(self) -> None:
        while self._running:
            if self.connected:
                self.send(C2S.PING, {"client_ts": round(time.time(), 3)})
            time.sleep(config.PING_INTERVAL_SECONDS if hasattr(config, "PING_INTERVAL_SECONDS") else 2)

    def poll(self) -> list[dict]:
        """Ambil semua paket yang sudah masuk (dipanggil tiap frame)."""
        out = []
        while not self.inbox.empty():
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        return out

    def close(self) -> None:
        self._running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
