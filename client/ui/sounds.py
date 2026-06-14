"""
Modul audio untuk UNO Online.

Memuat file efek suara & musik (.mp3) dari `client/assets/sounds` yang
disediakan pengguna, lalu memetakannya ke aktivitas dalam game. Efek yang
belum punya file dilengkapi sintesis nada (numpy) agar setiap aktivitas tetap
bersuara. Musik latar (lobby & in-game) diputar lewat `pygame.mixer.music`.

Pemetaan file -> aktivitas:
    card_play.mp3        : memainkan kartu biasa
    card_play_plus.mp3   : memainkan / kena kartu +2 / +4
    click.mp3            : menekan kartu & tombol UI
    win.mp3              : menang
    lose.mp3             : kalah
    leave.mp3            : keluar room / reconnect
    lobby.mp3 (musik)    : latar lobby / room / login / leaderboard
    game_bgm.mp3 (musik) : latar saat bermain / menonton
"""
import math
import os

import pygame

try:
    import numpy as np
except Exception:  # numpy opsional (hanya untuk sintesis fallback)
    np = None


_SOUND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sounds"
)

# Aktivitas -> nama file SFX (one-shot).
_SFX_FILES = {
    "card_play": "card_play.mp3",
    "card_play_plus": "card_play_plus.mp3",
    "click": "click.mp3",
    "win": "win.mp3",
    "lose": "lose.mp3",
    "leave": "leave.mp3",
}

# Nama musik latar -> file.
_MUSIC_FILES = {
    "lobby": "lobby.mp3",
    "game": "game_bgm.mp3",
}

# Volume default tiap efek (0..1).
_SFX_VOLUME = {
    "card_play": 0.7,
    "card_play_plus": 0.8,
    "click": 0.45,
    "win": 0.8,
    "lose": 0.8,
    "leave": 0.7,
    # efek sintesis fallback
    "card_draw": 0.4,
    "uno_call": 0.6,
    "your_turn": 0.4,
    "error": 0.3,
    "penalty": 0.5,
    "catch": 0.6,
}

_sounds: dict[str, "pygame.mixer.Sound"] = {}
_initialized = False
_music_name: str | None = None
_music_volume = 0.35
_muted = False


def init():
    """Inisialisasi modul audio. Panggil setelah pygame.mixer.init()."""
    global _initialized
    if _initialized:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        # Sediakan beberapa channel agar SFX tidak saling memotong.
        try:
            pygame.mixer.set_num_channels(16)
        except Exception:
            pass
        _load_files()
        _generate_synth_fallback()
        _initialized = True
    except Exception:
        # Mis. tidak ada sound device — game tetap jalan tanpa audio.
        _initialized = False


def _load_files():
    """Muat file SFX mp3 milik pengguna bila tersedia."""
    for name, fname in _SFX_FILES.items():
        path = os.path.join(_SOUND_DIR, fname)
        if not os.path.exists(path):
            continue
        try:
            snd = pygame.mixer.Sound(path)
            snd.set_volume(_SFX_VOLUME.get(name, 0.6))
            _sounds[name] = snd
        except Exception:
            pass


def _generate_synth_fallback():
    """Lengkapi efek yang belum punya file dengan sintesis nada (numpy)."""
    if np is None:
        return
    recipes = {
        "card_play": _tone_card_play,
        "card_play_plus": _tone_penalty,
        "card_draw": _tone_card_draw,
        "uno_call": _tone_uno_call,
        "your_turn": _tone_your_turn,
        "win": _tone_win,
        "lose": _tone_penalty,
        "error": _tone_error,
        "penalty": _tone_penalty,
        "catch": _tone_catch,
        "leave": _tone_card_draw,
    }
    for name, recipe in recipes.items():
        if name in _sounds:
            continue  # sudah ada file mp3
        try:
            snd = _make_sound(recipe())
            snd.set_volume(_SFX_VOLUME.get(name, 0.5))
            _sounds[name] = snd
        except Exception:
            pass


def play(name: str, volume: float | None = None):
    """Mainkan efek suara satu kali berdasarkan nama aktivitas."""
    if not _initialized or _muted:
        return
    snd = _sounds.get(name)
    if not snd:
        return
    if volume is not None:
        snd.set_volume(max(0.0, min(1.0, volume)))
    snd.play()


# -- Musik latar -----------------------------------------------------------

def play_music(name: str, volume: float | None = None, loops: int = -1):
    """Putar musik latar (looping). Tidak melakukan apa-apa jika sudah berputar."""
    global _music_name
    if not _initialized or _muted:
        _music_name = name  # ingat agar bisa di-resume saat unmute
        return
    if _music_name == name and pygame.mixer.music.get_busy():
        return
    path = os.path.join(_SOUND_DIR, _MUSIC_FILES.get(name, ""))
    if not os.path.exists(path):
        return
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(_music_volume if volume is None else volume)
        pygame.mixer.music.play(loops)
        _music_name = name
    except Exception:
        pass


def stop_music():
    global _music_name
    _music_name = None
    if not _initialized:
        return
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass


def set_muted(muted: bool):
    """Bisukan/aktifkan semua audio."""
    global _muted
    _muted = bool(muted)
    if not _initialized:
        return
    try:
        if _muted:
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()
    except Exception:
        pass


def is_muted() -> bool:
    return _muted


# -- Waveform generators (fallback) ----------------------------------------

def _make_sound(samples) -> "pygame.mixer.Sound":
    """Konversi array numpy float ke pygame.mixer.Sound (stereo, 16-bit)."""
    peak = np.max(np.abs(samples))
    if peak > 0:
        samples = samples / peak
    int_samples = (samples * 32767 * 0.6).astype(np.int16)
    stereo = np.column_stack((int_samples, int_samples))
    return pygame.mixer.Sound(buffer=stereo)


def _sine(freq: float, duration: float, sr: int = 44100):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * math.pi * freq * t)


def _apply_envelope(samples, attack: float = 0.01, decay: float = 0.05, sr: int = 44100):
    n = len(samples)
    attack_samples = min(int(attack * sr), n)
    decay_samples = min(int(decay * sr), n)
    env = np.ones(n)
    if attack_samples > 0:
        env[:attack_samples] = np.linspace(0, 1, attack_samples)
    if decay_samples > 0:
        env[-decay_samples:] = np.linspace(1, 0, decay_samples)
    return samples * env


def _tone_card_play():
    s1 = _sine(800, 0.04) * 0.8
    s2 = _sine(600, 0.04) * 0.5
    return _apply_envelope(np.concatenate([s1, s2]), attack=0.002, decay=0.03)


def _tone_card_draw():
    s = _sine(400, 0.08) * 0.6
    s2 = _sine(300, 0.06) * 0.4
    return _apply_envelope(np.concatenate([s, s2]), attack=0.005, decay=0.04)


def _tone_uno_call():
    s1 = _sine(880, 0.1)
    gap = np.zeros(int(44100 * 0.03))
    s2 = _sine(1100, 0.15)
    return _apply_envelope(np.concatenate([s1, gap, s2]), attack=0.005, decay=0.08)


def _tone_your_turn():
    s1 = _sine(523, 0.08)
    s2 = _sine(659, 0.08)
    s3 = _sine(784, 0.12)
    return _apply_envelope(np.concatenate([s1, s2, s3]), attack=0.005, decay=0.06)


def _tone_win():
    notes = [523, 659, 784, 1047]
    parts = []
    for freq in notes:
        parts.append(_sine(freq, 0.12))
        parts.append(np.zeros(int(44100 * 0.02)))
    return _apply_envelope(np.concatenate(parts), attack=0.005, decay=0.1)


def _tone_error():
    s = _sine(200, 0.15) * 0.7
    noise = np.random.uniform(-0.15, 0.15, len(s))
    return _apply_envelope(s + noise, attack=0.005, decay=0.08)


def _tone_penalty():
    s1 = _sine(600, 0.1)
    s2 = _sine(450, 0.1)
    s3 = _sine(300, 0.15)
    return _apply_envelope(np.concatenate([s1, s2, s3]), attack=0.005, decay=0.08)


def _tone_catch():
    s1 = _sine(440, 0.06)
    s2 = _sine(880, 0.06)
    s3 = _sine(660, 0.12)
    return _apply_envelope(np.concatenate([s1, s2, s3]), attack=0.003, decay=0.06)
