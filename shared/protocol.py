import json
import struct
import time

HEADER_SIZE = 4
MAX_PACKET_SIZE = 1 * 1024 * 1024

class ProtocolError(Exception):
    pass

def build_packet(ptype: str, payload: dict | None = None, seq: int = 0) -> bytes:
    obj = {
        "type": ptype,
        "seq": seq,
        "ts": round(time.time(), 3),
        "payload": payload or {},
    }
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_PACKET_SIZE:
        raise ProtocolError("Packet too large")
    header = struct.pack(">I", len(body))
    return header + body

def _recv_exact(sock, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)

def recv_packet(sock) -> dict | None:
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    if length <= 0 or length > MAX_PACKET_SIZE:
        raise ProtocolError(f"Invalid packet length: {length}")
    body = _recv_exact(sock, length)
    if body is None:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProtocolError(f"Malformed JSON: {e}")

def send_packet(sock, ptype: str, payload: dict | None = None, seq: int = 0) -> None:
    sock.sendall(build_packet(ptype, payload, seq))
