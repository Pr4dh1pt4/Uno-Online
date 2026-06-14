"""Scene login & register — desain premium."""
import pygame

import config
from shared.packet_types import C2S, S2C
from shared.constants import PlayerRole
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, TextInput, Palette, draw_text,
    draw_bg_gradient, draw_shadow_rect, draw_gradient_rect,
    draw_glow, draw_particles,
)
from client.ui import assets
from client.ui import sounds


class LoginScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = config.WINDOW_WIDTH // 2
        self.username = TextInput((cx - 160, 320, 320, 48), "Username")
        self.password = TextInput((cx - 160, 384, 320, 48), "Password", password=True)
        self.btn_login = Button((cx - 160, 460, 152, 50), "Masuk", self._login,
                                color=(56, 193, 114))
        self.btn_register = Button((cx + 2, 460, 152, 50), "Daftar", self._register,
                                   color=Palette.BLUE)
        self.message = ""
        self.msg_color = Palette.ACCENT
        self._tick = 0

    def on_enter(self):
        sounds.play_music("lobby")

    def _login(self):
        self.state.net.send(C2S.LOGIN_REQ, {
            "username": self.username.text, "password": self.password.text})
        self.message = "Menghubungkan..."
        self.msg_color = Palette.TEXT_DIM

    def _register(self):
        self.state.net.send(C2S.REGISTER_REQ, {
            "username": self.username.text, "password": self.password.text})
        self.message = "Mendaftar..."
        self.msg_color = Palette.TEXT_DIM

    def handle_event(self, event):
        for w in (self.username, self.password, self.btn_login, self.btn_register):
            w.handle(event)
        # Enter pada salah satu field langsung mencoba masuk (paritas dengan web).
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.username.text and self.password.text:
                self._login()

    def handle_packet(self, pkt):
        t, p = pkt["type"], pkt["payload"]
        if t == S2C.LOGIN_OK:
            self.state.user_id = p["user_id"]
            self.state.username = p["username"]
            self.state.token = p["token"]
            self.state.stats = p.get("stats", {})
            resume = p.get("resume")
            if resume:
                room = resume.get("room", {})
                self.state.room_id = resume.get("room_id") or room.get("room_id")
                self.state.room_code = resume.get("room_code") or room.get("room_code")
                self.state.host_id = resume.get("host_id") or room.get("host_id")
                self.state.match_mode = resume.get("match_mode") or room.get("match_mode", "ranked")
                self.state.players = room.get("players", [])
                self.state.game_state = resume.get("state")
                self.state.hand = resume.get("hand", [])
                self.state.is_spectator = resume.get("role") == PlayerRole.SPECTATOR
                self.go("spectator" if self.state.is_spectator else "game")
            else:
                self.go("lobby")
        elif t == S2C.LOGIN_FAIL:
            self.message = "Login gagal: username atau password salah."
            self.msg_color = Palette.ACCENT
        elif t == S2C.REGISTER_OK:
            self.message = "Akun dibuat. Silakan masuk."
            self.msg_color = Palette.GREEN
        elif t == S2C.REGISTER_FAIL:
            reason = p.get("reason", "")
            mapping = {
                "username_taken": "Username sudah dipakai.",
                "username_length": "Username harus 3-32 karakter.",
                "password_too_short": "Password minimal 4 karakter.",
            }
            self.message = mapping.get(reason, f"Gagal daftar: {reason}")
            self.msg_color = Palette.ACCENT
        elif t == S2C.FORCE_LOGOUT:
            self.message = p.get("reason", "Anda dikeluarkan dari sesi lain.")
            self.msg_color = Palette.ACCENT

    def update(self, dt):
        self._tick += 1

    def draw(self, surf):
        # Background gradient + partikel
        draw_bg_gradient(surf, (18, 22, 38), (8, 10, 18))
        draw_particles(surf, self._tick, count=25, color=(100, 120, 200))

        cx = config.WINDOW_WIDTH // 2
        cy = config.WINDOW_HEIGHT // 2

        # Logo / banner
        ban = assets.banner()
        if ban:
            ban = pygame.transform.smoothscale(ban, (200, 160))
            surf.blit(ban, ban.get_rect(center=(cx, 140)))

        # Title dengan glow
        draw_glow(surf, (cx, 252), 80, Palette.ACCENT, intensity=0.5)
        draw_text(surf, "UNO Online", (cx, 252), 44, Palette.TEXT, bold=True,
                  center=True, shadow=True)

        # Card form panel
        form_rect = (cx - 190, 300, 380, 234)
        draw_shadow_rect(surf, form_rect, offset=6, alpha=50, border_radius=16)
        draw_gradient_rect(surf, form_rect, (30, 34, 52), (22, 26, 40),
                           border_radius=16)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, form_rect, 1, border_radius=16)

        # Input fields & buttons
        for w in (self.username, self.password, self.btn_login, self.btn_register):
            w.draw(surf)

        # Pesan
        if self.message:
            draw_text(surf, self.message, (cx, 530), 17, self.msg_color, center=True)

        # Footer
        draw_text(surf, f"Server: {config.CLIENT_CONNECT_HOST}:{config.SERVER_PORT}",
                  (cx, config.WINDOW_HEIGHT - 30), 13, Palette.TEXT_MUTED, center=True)
