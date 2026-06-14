"""ResultScene — hasil akhir match, desain premium."""
import math
import pygame

import config
from shared.packet_types import C2S
from shared.constants import MATCH_MODE_RANKED
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, Palette, draw_text,
    draw_bg_gradient, draw_shadow_rect, draw_gradient_rect,
    draw_glow, draw_particles,
)
from client.ui import sounds


class ResultScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = config.WINDOW_WIDTH // 2
        self.btn_lobby = Button((cx - 110, 610, 220, 52), "Kembali ke Lobby",
                                self._back, color=(56, 193, 114))
        self._tick = 0

    def on_enter(self):
        if self.state.voice:
            self.state.voice.leave()
        # Hentikan musik in-game, mainkan jingle menang/kalah sesuai peringkat.
        sounds.stop_music()
        res = self.state.last_result or {}
        finish_order = res.get("finish_order", [])
        my_pos = None
        for pos, uid in enumerate(finish_order, 1):
            if uid == self.state.user_id:
                my_pos = pos
        if my_pos == 1:
            sounds.play("win")
        elif my_pos is not None:
            sounds.play("lose")

    def _back(self):
        self.state.room_id = None
        self.state.game_state = None
        self.state.hand = []
        self.state.is_spectator = False
        self.state.match_mode = MATCH_MODE_RANKED
        self.state.net.send(C2S.GET_STATS, {"user_id": self.state.user_id})
        self.go("lobby")

    def handle_event(self, event):
        self.btn_lobby.handle(event)

    def update(self, dt):
        self._tick += 1

    def draw(self, surf):
        draw_bg_gradient(surf, (18, 22, 38), (8, 10, 18))

        res = self.state.last_result or {}
        finish_order = res.get("finish_order", [])
        results = res.get("results", {})
        details = {
            str(row.get("user_id")): row
            for row in res.get("ranking_details", [])
        }
        match_mode = res.get("match_mode", self.state.match_mode or MATCH_MODE_RANKED)
        is_ranked = match_mode == MATCH_MODE_RANKED

        cx = config.WINDOW_WIDTH // 2

        # Apakah saya menang?
        my_pos = None
        for pos, uid in enumerate(finish_order, 1):
            if uid == self.state.user_id:
                my_pos = pos

        if my_pos == 1:
            title = "🏆  ANDA MENANG!"
            tcol = Palette.GOLD
            # Confetti particles
            draw_particles(surf, self._tick, count=50,
                           color=(218, 180, 56))
            draw_particles(surf, self._tick + 500, count=30,
                           color=(56, 193, 114))
            draw_glow(surf, (cx, 75), 120, Palette.GOLD, intensity=1.0)
        elif my_pos == len(finish_order) and my_pos is not None:
            title = "Anda Kalah"
            tcol = Palette.ACCENT
            draw_particles(surf, self._tick, count=15, color=(80, 100, 180))
        else:
            title = "Match Selesai"
            tcol = Palette.TEXT
            draw_particles(surf, self._tick, count=20, color=(80, 100, 180))

        draw_text(surf, title, (cx, 75), 42, tcol, bold=True,
                  center=True, shadow=True)

        mode_label = "RANKED - poin leaderboard aktif" if is_ranked else "CLASSIC - poin tidak berubah"
        mode_col = Palette.GOLD if is_ranked else Palette.BLUE
        mode_rect = (cx - 170, 112, 340, 28)
        draw_gradient_rect(surf, mode_rect, mode_col,
                           tuple(max(0, c - 45) for c in mode_col),
                           border_radius=14)
        draw_text(surf, mode_label, (cx, 126), 14, Palette.BG,
                  bold=True, center=True)

        # Peringkat akhir header
        draw_text(surf, "Peringkat Akhir", (cx, 160), 22,
                  Palette.TEXT_DIM, center=True)

        # Tabel hasil
        y = 205

        # Panel background
        panel_h = len(finish_order) * 62 + 20
        panel_rect = (cx - 340, y - 10, 680, panel_h)
        draw_shadow_rect(surf, panel_rect, offset=5, alpha=40, border_radius=16)
        draw_gradient_rect(surf, panel_rect, (30, 34, 52), (22, 26, 40),
                           border_radius=16)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, panel_rect, 1, border_radius=16)

        # Gunakan player_names dari payload, fallback ke game_state
        names = res.get("player_names", {})
        if not names:
            names = {str(pl["user_id"]): pl["username"]
                     for pl in (self.state.game_state or {}).get("players", [])}

        for pos, uid in enumerate(finish_order, 1):
            r = results.get(str(uid)) or results.get(uid) or {}
            detail = details.get(str(uid), {})
            name = names.get(str(uid), f"User {uid}")
            delta = r.get("point_change", 0)
            total = r.get("total_point", "-")
            tier = r.get("rank_tier", "")
            remaining_value = r.get("remaining_value", detail.get("remaining_value", 0))
            me = uid == self.state.user_id

            # Row card
            row_rect = (cx - 320, y, 640, 50)

            if me:
                draw_gradient_rect(surf, row_rect, (40, 50, 75), (30, 38, 58),
                                   border_radius=10)
                pygame.draw.rect(surf, Palette.GOLD, row_rect, 2, border_radius=10)
            else:
                draw_gradient_rect(surf, row_rect, (34, 38, 56), (26, 30, 44),
                                   border_radius=10)

            # Position medal
            medal_colors = {1: Palette.GOLD, 2: (195, 200, 215), 3: (186, 150, 95)}
            medal_col = medal_colors.get(pos, Palette.TEXT_DIM)
            medal_x = cx - 300
            pygame.draw.circle(surf, medal_col, (medal_x + 12, y + 25), 15)
            draw_text(surf, str(pos), (medal_x + 12, y + 25), 16,
                      Palette.BG, bold=True, center=True)

            # Name
            draw_text(surf, name, (medal_x + 40, y + 14), 20, Palette.TEXT, bold=me)
            draw_text(surf, f"Value sisa: {remaining_value}", (medal_x + 40, y + 34),
                      12, Palette.TEXT_MUTED)
            if me:
                draw_text(surf, "[Anda]", (medal_x + 40 + len(name) * 11, y + 16), 14,
                          Palette.GOLD)

            # Point change
            if is_ranked:
                dcol = Palette.GREEN if delta > 0 else (Palette.ACCENT if delta < 0 else Palette.TEXT_DIM)
                delta_text = f"+{delta}" if delta > 0 else str(delta)
            else:
                dcol = Palette.BLUE
                delta_text = "Classic"
            draw_text(surf, delta_text, (cx + 140, y + 14), 20, dcol, bold=True)

            # Total & rank
            rank_col = Palette.RANK_COLORS.get(tier, Palette.TEXT_DIM)
            draw_text(surf, f"{total} pts", (cx + 220, y + 10), 16, Palette.TEXT_DIM)
            if tier:
                tier_rect = (cx + 280, y + 12, 60, 22)
                draw_gradient_rect(surf, tier_rect, rank_col,
                                   tuple(max(0, c - 40) for c in rank_col),
                                   border_radius=11)
                draw_text(surf, tier, (cx + 310, y + 23), 12,
                          Palette.BG, bold=True, center=True)

            y += 62

        self.btn_lobby.draw(surf)
