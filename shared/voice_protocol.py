"""Protokol voice chat UDP berbasis JSON + base64 PCM16."""
import base64
import json
import time

VOICE_JOIN = "VOICE_JOIN"
VOICE_OK = "VOICE_OK"
VOICE_LEAVE = "VOICE_LEAVE"
VOICE_PING = "VOICE_PING"
VOICE_AUDIO = "VOICE_AUDIO"
VOICE_REJECTED = "VOICE_REJECTED"

VOICE_SAMPLE_RATE = 16000
VOICE_CHANNELS = 1
VOICE_FRAME_MS = 40
VOICE_FRAME_SAMPLES = VOICE_SAMPLE_RATE * VOICE_FRAME_MS // 1000
MAX_VOICE_PACKET_SIZE = 4096
MAX_AUDIO_BYTES = VOICE_FRAME_SAMPLES * VOICE_CHANNELS * 2


class VoiceProtocolError(Exception):
    pass


def encode_packet(ptype: str, payload: dict | None = None) -> bytes:
    obj = {
        "type": ptype,
        "ts": round(time.time(), 3),
        "payload": payload or {},
    }
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_VOICE_PACKET_SIZE:
        raise VoiceProtocolError("voice packet too large")
    return raw


def decode_packet(data: bytes) -> dict:
    if not data or len(data) > MAX_VOICE_PACKET_SIZE:
        raise VoiceProtocolError("invalid voice packet size")
    try:
        pkt = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise VoiceProtocolError(f"bad json: {e}")
    if not isinstance(pkt, dict):
        raise VoiceProtocolError("packet is not object")
    ptype = pkt.get("type")
    payload = pkt.get("payload")
    if not isinstance(ptype, str) or not isinstance(payload, dict):
        raise VoiceProtocolError("bad packet shape")
    return pkt


def encode_audio(raw_pcm: bytes) -> str:
    if len(raw_pcm) > MAX_AUDIO_BYTES:
        raise VoiceProtocolError("audio frame too large")
    return base64.b64encode(raw_pcm).decode("ascii")


def decode_audio(value: str) -> bytes:
    if not isinstance(value, str):
        raise VoiceProtocolError("audio payload is not string")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as e:
        raise VoiceProtocolError(f"bad audio payload: {e}")
    if len(raw) > MAX_AUDIO_BYTES:
        raise VoiceProtocolError("audio frame too large")
    return raw
