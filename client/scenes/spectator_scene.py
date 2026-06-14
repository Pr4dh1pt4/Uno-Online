"""
SpectatorScene — pemain yang sudah menang menonton match, desain premium.
"""
import pygame

import config
from shared.packet_types import C2S, S2C
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, Palette, draw_text,
    draw_shadow_rect, draw_gradient_rect, draw_glow,
)
from client.ui import assets
from client.ui import sounds


class SpectatorScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.btn_leave = Button((config.WINDOW_WIDTH - 160, 60, 130, 40),
                                "Keluar Room", self._leave, color=Palette.PANEL_LIGHT,
                                font_size=16)
        self.btn_voice = Button((config.WINDOW_WIDTH - 300, 60, 120, 40),
                                "Mic Off", self._toggle_voice,
                                color=Palette.PANEL_LIGHT, font_size=16)
        self._tick = 0

    def on_enter(self):
        sounds.play_music("game")
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

    def _leave(self):
        if self.state.voice:
            self.state.voice.leave()
        self.state.net.send(C2S.LEAVE_ROOM, {})

    def handle_event(self, event):
        self.btn_voice.handle(event)
        self.btn_leave.handle(event)

    def handle_packet(self, pkt):
        t, p = pkt["type"], pkt["payload"]
        if t == S2C.STATE_UPDATE:
            self.state.game_state = p["state"]
        elif t == S2C.LEFT_ROOM:
            if self.state.voice:
                self.state.voice.leave()
            self.state.is_spectator = False
            self.state.room_id = None
            self.state.match_mode = "ranked"
            self.go("lobby")
        elif t == S2C.MATCH_RESULT:
            self.state.last_result = p
            self.state.match_mode = p.get("match_mode", self.state.match_mode)
            self.go("result")
        elif t == S2C.FORCE_LOGOUT:
            self.go("login")

    def update(self, dt):
        self._tick += 1

    def draw(self, surf):
        bg = assets.table_background(0)
        if bg:
            surf.blit(bg, (0, 0))
        else:
            for y in range(config.WINDOW_HEIGHT):
                t = y / config.WINDOW_HEIGHT
                r = int(12 + t * 8)
                g = int(45 + t * 20)
                b = int(28 + t * 15)
                pygame.draw.line(surf, (r, g, b), (0, y), (config.WINDOW_WIDTH, y))

        # Banner mode penonton
        banner_surf = pygame.Surface((config.WINDOW_WIDTH, 50), pygame.SRCALPHA)
        draw_gradient_rect(banner_surf, (0, 0, config.WINDOW_WIDTH, 50),
                           (0, 0, 0, 160), (0, 0, 0, 60))
        surf.blit(banner_surf, (0, 0))

        # Animasi ikon mata
        import math
        pulse = 0.7 + 0.3 * math.sin(self._tick * 0.06)
        alpha = int(200 * pulse)
        eye_surf = pygame.Surface((config.WINDOW_WIDTH, 30), pygame.SRCALPHA)
        draw_text(eye_surf, "👁  MODE PENONTON — Anda sudah menang, menyaksikan sisa match",
                  (config.WINDOW_WIDTH // 2, 15), 16,
                  (*Palette.GOLD[:3], alpha), center=True)
        surf.blit(eye_surf, (0, 10))

        gs = self.state.game_state
        if not gs:
            self._draw_voice(surf)
            self.btn_leave.draw(surf)
            return

        from server.core.card import Card
        cx, cy = config.WINDOW_WIDTH // 2, config.WINDOW_HEIGHT // 2

        # Kartu teratas
        top = gs.get("top_card")
        if top:
            draw_shadow_rect(surf, (cx - config.CARD_W // 2, cy - config.CARD_H // 2,
                                     config.CARD_W, config.CARD_H),
                             offset=5, alpha=60, border_radius=10)
            surf.blit(assets.card_surface(Card.from_dict(top).asset_name),
                      (cx - config.CARD_W // 2, cy - config.CARD_H // 2))

        # Warna aktif
        ac = gs.get("active_color")
        if ac and ac in Palette.UNO_COLORS:
            ix = cx + config.CARD_W // 2 + 40
            draw_glow(surf, (ix, cy), 25, Palette.UNO_COLORS[ac], intensity=0.8)
            pygame.draw.circle(surf, Palette.UNO_COLORS[ac], (ix, cy), 16)
            pygame.draw.circle(surf, (255, 255, 255, 80), (ix, cy), 16, 2)

        # Pending draw indicator
        pending = gs.get("pending_draw", 0)
        if pending > 0:
            pd_type = gs.get("pending_draw_type", "")
            pd_color = Palette.ACCENT if pd_type == "Draw" else Palette.PURPLE
            pd_y = cy + config.CARD_H // 2 + 30
            badge_rect = (cx - 40, pd_y - 14, 80, 28)
            draw_gradient_rect(surf, badge_rect, pd_color,
                               tuple(max(0, c - 40) for c in pd_color),
                               border_radius=14)
            draw_text(surf, f"+{pending}", (cx, pd_y), 18, Palette.TEXT,
                      bold=True, center=True)

        # Pemain & jumlah kartu
        y = 100
        player_panel = (40, y - 10, 280, 40 + len(gs["players"]) * 36)
        draw_shadow_rect(surf, player_panel, offset=3, alpha=40, border_radius=12)
        draw_gradient_rect(surf, player_panel, (28, 32, 50, 200), (20, 24, 38, 160),
                           border_radius=12)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, player_panel, 1, border_radius=12)

        draw_text(surf, "Pemain", (55, y), 18, Palette.TEXT, bold=True)
        y += 30
        for pl in gs["players"]:
            is_turn = gs.get("current_turn") == pl["user_id"]
            col = Palette.GOLD if is_turn else Palette.TEXT
            status = ""
            if pl.get("has_won"):
                status = " 🏆"
            elif not pl.get("is_active", True):
                status = " (keluar)"
            mark = "▶ " if is_turn else "   "
            draw_text(surf, f"{mark}{pl['username']}: {pl['hand_count']} kartu{status}",
                      (55, y), 15, col)
            y += 32

        # Scoreboard
        self._draw_scoreboard(surf, gs)
        draw_text(surf, f"Ping: {self.state.net.ping_ms} ms",
                  (20, config.WINDOW_HEIGHT - 30), 13, Palette.TEXT_MUTED)
        self._draw_voice(surf)
        self.btn_leave.draw(surf)

    def _draw_voice(self, surf):
        if not self.state.voice:
            return
        live = self.state.voice.mic_enabled
        self.btn_voice.label = "Mic On" if live else "Mic Off"
        self.btn_voice.color = Palette.GREEN if live else Palette.PANEL_LIGHT
        self.btn_voice.hover_color = Palette.GREEN_HOVER if live else Palette.PANEL_HOVER
        self.btn_voice.draw(surf)
        draw_text(surf, self.state.voice.status,
                  (config.WINDOW_WIDTH - 300, 108), 12, Palette.TEXT_MUTED)

    def _draw_scoreboard(self, surf, gs):
        sb = gs.get("scoreboard", [])
        x = config.WINDOW_WIDTH - 300
        y = 100

        panel_rect = (x - 10, y - 10, 290, 46 + len(sb) * 30)
        draw_shadow_rect(surf, panel_rect, offset=3, alpha=40, border_radius=12)
        draw_gradient_rect(surf, panel_rect, (28, 32, 50, 200), (20, 24, 38, 160),
                           border_radius=12)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, panel_rect, 1, border_radius=12)

        draw_text(surf, "Scoreboard", (x, y), 18, Palette.TEXT, bold=True)
        y += 32
        for i, row in enumerate(sb, 1):
            pos = row.get("finish_position") or "-"
            draw_text(surf, f"{i}. {row['username']}  (sisa {row['hand_count']}, pos {pos})",
                      (x, y), 14, Palette.TEXT_DIM)
            y += 28
