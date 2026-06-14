"""Room: ruang tunggu — desain premium."""
import math
import pygame

import config
from shared.packet_types import C2S, S2C
from shared.constants import MIN_PLAYERS, MAX_PLAYERS, MATCH_MODE_RANKED
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, Palette, draw_text,
    draw_bg_gradient, draw_shadow_rect, draw_gradient_rect,
    draw_glow, draw_particles,
)
from client.ui import sounds


class RoomScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = config.WINDOW_WIDTH // 2
        self.btn_start = Button((cx - 170, 570, 160, 52), "🎮  Mulai", self._start,
                                color=(56, 193, 114))
        self.btn_leave = Button((cx + 10, 570, 160, 52), "Keluar Room", self._leave,
                                color=Palette.PANEL_LIGHT)
        self.btn_voice = Button((30, 30, 120, 38), "Mic Off", self._toggle_voice,
                                color=Palette.PANEL_LIGHT, font_size=15)
        self.message = ""
        self._tick = 0

    def on_enter(self):
        sounds.play_music("lobby")
        self._join_voice()

    def _join_voice(self):
        if self.state.voice and self.state.token and self.state.room_id:
            self.state.voice.join(
                self.state.token,
                self.state.room_id,
                self.state.user_id,
                self.state.username,
            )

    def _toggle_voice(self):
        if self.state.voice:
            if not self.state.voice.joined:
                self._join_voice()
            self.state.voice.toggle_mic()

    def _start(self):
        self.state.net.send(C2S.START_MATCH_REQ, {})

    def _leave(self):
        if self.state.voice:
            self.state.voice.leave()
        self.state.net.send(C2S.LEAVE_ROOM, {})

    def handle_event(self, event):
        self.btn_voice.handle(event)
        self.btn_leave.handle(event)
        if self._is_host():
            self.btn_start.handle(event)

    def _is_host(self):
        return self.state.host_id == self.state.user_id

    def handle_packet(self, pkt):
        t, p = pkt["type"], pkt["payload"]
        if t == S2C.ROOM_UPDATE:
            self.state.players = p.get("players", [])
            self.state.host_id = p.get("host_id")
            self.state.match_mode = p.get("match_mode", self.state.match_mode)
        elif t == S2C.GAME_START:
            self.state.hand = p.get("hand", [])
            self.state.game_state = p.get("state")
            self.state.is_spectator = False
            self.go("game")
        elif t == S2C.LEFT_ROOM:
            if self.state.voice:
                self.state.voice.leave()
            self.state.room_id = None
            self.state.match_mode = MATCH_MODE_RANKED
            self.go("lobby")
        elif t == S2C.ACTION_REJECTED:
            reason = p.get("reason", "")
            self.message = {
                "not_host": "Hanya host yang bisa memulai.",
                "not_enough_players": f"Minimal {MIN_PLAYERS} pemain untuk mulai.",
            }.get(reason, f"Gagal: {reason}")
        elif t == S2C.FORCE_LOGOUT:
            self.go("login")

    def update(self, dt):
        self._tick += 1

    def draw(self, surf):
        draw_bg_gradient(surf, (18, 22, 38), (8, 10, 18))
        draw_particles(surf, self._tick, count=15, color=(80, 100, 180))

        cx = config.WINDOW_WIDTH // 2

        # Title
        draw_glow(surf, (cx, 60), 60, Palette.GOLD, intensity=0.4)
        draw_text(surf, "Ruang Tunggu", (cx, 60), 34, Palette.TEXT, bold=True,
                  center=True, shadow=True)

        # Room code badge
        mode = self.state.match_mode or MATCH_MODE_RANKED
        mode_label = "RANKED" if mode == MATCH_MODE_RANKED else "CLASSIC"
        mode_col = Palette.GOLD if mode == MATCH_MODE_RANKED else Palette.BLUE

        code_rect = (cx - 155, 100, 180, 42)
        draw_gradient_rect(surf, code_rect, Palette.GOLD,
                           tuple(max(0, c - 50) for c in Palette.GOLD),
                           border_radius=21)
        draw_text(surf, f"Kode: {self.state.room_code}", (cx - 65, 121), 20,
                  Palette.BG, bold=True, center=True)

        mode_rect = (cx + 35, 100, 120, 42)
        draw_gradient_rect(surf, mode_rect, mode_col,
                           tuple(max(0, c - 50) for c in mode_col),
                           border_radius=21)
        draw_text(surf, mode_label, (cx + 95, 121), 17,
                  Palette.BG, bold=True, center=True)

        # Player count
        player_count = len(self.state.players)
        draw_text(surf, f"Pemain ({player_count}/{MAX_PLAYERS})",
                  (cx, 165), 18, Palette.TEXT_DIM, center=True)

        if self.state.voice:
            live = self.state.voice.mic_enabled
            self.btn_voice.label = "Mic On" if live else "Mic Off"
            self.btn_voice.color = Palette.GREEN if live else Palette.PANEL_LIGHT
            self.btn_voice.hover_color = Palette.GREEN_HOVER if live else Palette.PANEL_HOVER
            self.btn_voice.draw(surf)
            draw_text(surf, self.state.voice.status, (160, 40), 13,
                      Palette.TEXT_MUTED)

        # Player cards
        y = 200
        for i, m in enumerate(self.state.players):
            is_host = m["user_id"] == self.state.host_id
            is_me = m["user_id"] == self.state.user_id
            connected = m.get("connected", True)

            # Card
            card_rect = (cx - 210, y, 420, 58)
            draw_shadow_rect(surf, card_rect, offset=3, alpha=35, border_radius=12)

            if is_me:
                draw_gradient_rect(surf, card_rect, (40, 50, 75), (30, 38, 58),
                                   border_radius=12)
                pygame.draw.rect(surf, Palette.GOLD, card_rect, 2, border_radius=12)
            else:
                draw_gradient_rect(surf, card_rect, (32, 38, 56), (24, 30, 46),
                                   border_radius=12)
                pygame.draw.rect(surf, Palette.PANEL_BORDER, card_rect, 1,
                                 border_radius=12)

            # Avatar circle
            avatar_col = Palette.GREEN if connected else Palette.TEXT_MUTED
            pygame.draw.circle(surf, avatar_col, (cx - 180, y + 29), 16)
            draw_text(surf, m["username"][0].upper(), (cx - 180, y + 29), 16,
                      Palette.BG, bold=True, center=True)

            # Name
            col = Palette.TEXT if connected else Palette.TEXT_DIM
            label = m["username"]
            draw_text(surf, label, (cx - 155, y + 17), 20, col, bold=is_me)

            # Badges
            badge_x = cx + 100
            if is_host:
                badge_r = pygame.Rect(badge_x, y + 16, 56, 24)
                draw_gradient_rect(surf, badge_r, Palette.GOLD,
                                   tuple(max(0, c - 40) for c in Palette.GOLD),
                                   border_radius=12)
                draw_text(surf, "Host", (badge_r.centerx, badge_r.centery), 13,
                          Palette.BG, bold=True, center=True)
                badge_x += 66
            if is_me:
                badge_r = pygame.Rect(badge_x, y + 16, 56, 24)
                draw_gradient_rect(surf, badge_r, Palette.BLUE,
                                   tuple(max(0, c - 30) for c in Palette.BLUE),
                                   border_radius=12)
                draw_text(surf, "Anda", (badge_r.centerx, badge_r.centery), 13,
                          Palette.TEXT, bold=True, center=True)

            y += 70

        # Empty slots
        for j in range(player_count, MAX_PLAYERS):
            card_rect = (cx - 210, y, 420, 58)
            # Dashed outline effect
            pygame.draw.rect(surf, Palette.PANEL_BORDER, card_rect, 1,
                             border_radius=12)
            # Pulsing dots for waiting
            dot_alpha = int(128 + 127 * math.sin(self._tick * 0.05 + j))
            ds = pygame.Surface((420, 58), pygame.SRCALPHA)
            draw_text(ds, "Menunggu pemain...", (210, 29), 16,
                      (*Palette.TEXT_MUTED[:3], dot_alpha), center=True)
            surf.blit(ds, (cx - 210, y))
            y += 70

        # Buttons
        self.btn_leave.draw(surf)
        if self._is_host():
            self.btn_start.enabled = player_count >= MIN_PLAYERS
            self.btn_start.draw(surf)
        else:
            # Waiting indicator with pulse
            alpha = int(180 + 75 * math.sin(self._tick * 0.06))
            ws = pygame.Surface((config.WINDOW_WIDTH, 30), pygame.SRCALPHA)
            draw_text(ws, "Menunggu host memulai match...",
                      (config.WINDOW_WIDTH // 2, 15), 17,
                      (*Palette.TEXT_DIM[:3], alpha), center=True)
            surf.blit(ws, (0, 565))

        if self.message:
            draw_text(surf, self.message, (cx, 640), 17, Palette.ACCENT, center=True)
