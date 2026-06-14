import queue
import socket
import threading
import time

import config
from shared import voice_protocol as vp

try:
    import numpy as np
    import sounddevice as sd
except Exception as e:
    np = None
    sd = None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None

def _resample_int16(samples, src_rate: int, dst_rate: int):
    if src_rate == dst_rate or samples.size == 0:
        return samples
    n_src = samples.size
    n_dst = max(1, int(round(n_src * dst_rate / src_rate)))
    x_src = np.linspace(0.0, 1.0, n_src, endpoint=False)
    x_dst = np.linspace(0.0, 1.0, n_dst, endpoint=False)
    out = np.interp(x_dst, x_src, samples.astype(np.float32))
    return out.astype(np.int16)

class VoiceClient:
    def __init__(self, host: str):
        self.host = host
        self.port = config.VOICE_PORT
        self.sock: socket.socket | None = None
        self.running = False
        self.joined = False
        self.mic_enabled = False
        self.status = "Voice off"
        self.room_id = None
        self.user_id = None
        self.username = None
        self._seq = 0
        self._send_lock = threading.Lock()
        self._playback: "queue.Queue[bytes]" = queue.Queue(maxsize=24)
        self._input_stream = None
        self._output_stream = None
        self._in_rate = vp.VOICE_SAMPLE_RATE
        self._out_rate = vp.VOICE_SAMPLE_RATE

    @property
    def available(self) -> bool:
        return sd is not None and np is not None

    def join(self, token: str, room_id: str, user_id: int, username: str) -> None:
        if not self.available:
            self.status = f"Voice unavailable: {_IMPORT_ERROR}"
            return
        if self.joined and self.room_id == room_id:
            return

        self.leave()
        self.room_id = room_id
        self.user_id = user_id
        self.username = username
        self.mic_enabled = False

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.5)
            self.running = True
            self._start_audio_streams()
            threading.Thread(target=self._recv_loop, daemon=True).start()
            threading.Thread(target=self._keepalive_loop, daemon=True).start()
            self._send(vp.VOICE_JOIN, {
                "token": token,
                "room_id": room_id,
                "username": username,
            })
            self.joined = True
            if self._input_stream is None and self._output_stream is None:
                self.status = "Voice: device audio tidak tersedia"
            elif self._input_stream is None:
                self.status = "Voice connected (dengar saja, mic gagal)"
            else:
                self.status = "Voice connected"
        except Exception as e:
            self._cleanup()
            self.status = f"Voice error: {e}"

    def set_mic_enabled(self, enabled: bool) -> None:
        has_mic = self._input_stream is not None
        self.mic_enabled = bool(enabled and self.joined and self.available and has_mic)
        if self.joined:
            if enabled and not has_mic:
                self.status = "Mic tidak tersedia di perangkat ini"
            else:
                self.status = "Mic live" if self.mic_enabled else "Mic muted"

    def toggle_mic(self) -> None:
        self.set_mic_enabled(not self.mic_enabled)

    def leave(self) -> None:
        if self.sock and self.joined:
            self._send(vp.VOICE_LEAVE, {})
        self._cleanup()
        self.status = "Voice off"

    def _cleanup(self) -> None:
        self.joined = False
        self.mic_enabled = False
        self.room_id = None
        self._stop_audio_streams()
        self._drain_playback()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.running = False

    def close(self) -> None:
        self.leave()

    def _device_rate(self, kind: str) -> int:
        try:
            rate = sd.query_devices(kind=kind).get("default_samplerate")
            if rate:
                return int(rate)
        except Exception:
            pass
        return 48000

    def _start_audio_streams(self) -> None:
        self._input_stream = self._open_input()
        self._output_stream = self._open_output()

    def _open_input(self):
        frame_ms = vp.VOICE_FRAME_MS
        for rate in (vp.VOICE_SAMPLE_RATE, self._device_rate("input")):
            try:
                block = int(round(rate * frame_ms / 1000))
                stream = sd.InputStream(
                    samplerate=rate,
                    channels=vp.VOICE_CHANNELS,
                    dtype="int16",
                    blocksize=block,
                    callback=self._input_callback,
                )
                stream.start()
                self._in_rate = rate
                return stream
            except Exception:
                continue
        return None

    def _open_output(self):
        frame_ms = vp.VOICE_FRAME_MS
        for rate in (vp.VOICE_SAMPLE_RATE, self._device_rate("output")):
            try:
                block = int(round(rate * frame_ms / 1000))
                stream = sd.OutputStream(
                    samplerate=rate,
                    channels=vp.VOICE_CHANNELS,
                    dtype="int16",
                    blocksize=block,
                    callback=self._output_callback,
                )
                stream.start()
                self._out_rate = rate
                return stream
            except Exception:
                continue
        return None

    def _stop_audio_streams(self) -> None:
        for stream in (self._input_stream, self._output_stream):
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._input_stream = None
        self._output_stream = None

    def _input_callback(self, indata, frames, time_info, status) -> None:
        if not self.mic_enabled or not self.joined or not self.sock:
            return
        samples = np.asarray(indata, dtype=np.int16).reshape(-1)
        if self._in_rate != vp.VOICE_SAMPLE_RATE:
            samples = _resample_int16(samples, self._in_rate, vp.VOICE_SAMPLE_RATE)
        raw = samples.tobytes()
        if len(raw) > vp.MAX_AUDIO_BYTES:
            raw = raw[:vp.MAX_AUDIO_BYTES]
        with self._send_lock:
            self._seq += 1
            seq = self._seq
        try:
            self._send(vp.VOICE_AUDIO, {
                "seq": seq,
                "audio": vp.encode_audio(raw),
            })
        except Exception:
            self.status = "Voice send error"

    def _output_callback(self, outdata, frames, time_info, status) -> None:
        outdata.fill(0)
        try:
            raw = self._playback.get_nowait()
        except queue.Empty:
            return
        samples = np.frombuffer(raw, dtype=np.int16)
        if self._out_rate != vp.VOICE_SAMPLE_RATE:
            samples = _resample_int16(samples, vp.VOICE_SAMPLE_RATE, self._out_rate)
        need = frames * vp.VOICE_CHANNELS
        if samples.size < need:
            padded = np.zeros(need, dtype=np.int16)
            padded[:samples.size] = samples
            samples = padded
        outdata[:] = samples[:need].reshape(frames, vp.VOICE_CHANNELS)

    def _recv_loop(self) -> None:
        while self.running and self.sock:
            try:
                data, _ = self.sock.recvfrom(vp.MAX_VOICE_PACKET_SIZE + 1)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                pkt = vp.decode_packet(data)
            except vp.VoiceProtocolError:
                continue
            ptype = pkt["type"]
            payload = pkt["payload"]
            if ptype == vp.VOICE_OK:
                self.status = "Mic muted"
            elif ptype == vp.VOICE_REJECTED:
                self.status = f"Voice rejected: {payload.get('reason', '-')}"
            elif ptype == vp.VOICE_AUDIO:
                try:
                    raw = vp.decode_audio(payload.get("audio", ""))
                except vp.VoiceProtocolError:
                    continue
                if self._playback.full():
                    try:
                        self._playback.get_nowait()
                    except queue.Empty:
                        pass
                self._playback.put_nowait(raw)

    def _keepalive_loop(self) -> None:
        while self.running and self.sock:
            if self.joined:
                try:
                    self._send(vp.VOICE_PING, {})
                except OSError:
                    break
            time.sleep(5)

    def _send(self, ptype: str, payload: dict) -> None:
        if not self.sock:
            return
        self.sock.sendto(vp.encode_packet(ptype, payload), (self.host, self.port))

    def _drain_playback(self) -> None:
        while not self._playback.empty():
            try:
                self._playback.get_nowait()
            except queue.Empty:
                break
