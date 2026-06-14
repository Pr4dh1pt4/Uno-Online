"""LeaderboardScene — leaderboard / Top Global Player, desain premium."""
import pygame

import config
from shared.packet_types import S2C
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, Palette, draw_text,
    draw_bg_gradient, draw_shadow_rect, draw_gradient_rect,
    draw_particles,
)


class LeaderboardScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.entries = []
        self.history = []
        self.mode = "leaderboard"
        self.btn_back = Button((30, 30, 120, 40), "← Kembali", self._back,
                               color=Palette.PANEL_LIGHT, font_size=16)
        self._tick = 0

    def _back(self):
        self.go("lobby")

    def handle_event(self, event):
        self.btn_back.handle(event)

    def handle_packet(self, pkt):
        if pkt["type"] in (S2C.LEADERBOARD, S2C.TOP_GLOBAL):
            self.entries = pkt["payload"].get("entries", [])
        elif pkt["type"] == S2C.MATCH_HISTORY:
            self.history = pkt["payload"].get("entries", [])
        elif pkt["type"] == S2C.FORCE_LOGOUT:
            self.go("login")

    def update(self, dt):
        self._tick += 1

    def draw(self, surf):
        draw_bg_gradient(surf, (18, 22, 38), (8, 10, 18))
        draw_particles(surf, self._tick, count=12, color=(80, 100, 180))
        if self.mode == "history":
            self._draw_history(surf)
        else:
            self._draw_leaderboard(surf)
        self.btn_back.draw(surf)

    def _draw_history(self, surf):
        cx = config.WINDOW_WIDTH // 2
        draw_text(surf, "📜  Riwayat Match", (cx, 55), 32, Palette.TEXT, bold=True,
                  center=True, shadow=True)

        table_w = 900
        hx = cx - table_w // 2 + 20

        if not self.history:
            draw_text(surf, "Belum ada match. Main satu ronde dulu!", (cx, 300), 20,
                      Palette.TEXT_DIM, center=True)
            return

        display_count = min(10, len(self.history))
        panel_rect = (cx - table_w // 2, 95, table_w, 50 + display_count * 48)
        draw_shadow_rect(surf, panel_rect, offset=5, alpha=40, border_radius=14)
        draw_gradient_rect(surf, panel_rect, (30, 34, 52), (22, 26, 40), border_radius=14)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, panel_rect, 1, border_radius=14)

        header_y = 110
        headers = [("Hasil", 0), ("Mode", 150), ("Peringkat", 280), ("Poin", 440),
                   ("Pemenang", 560), ("Waktu", 740)]
        for label, off in headers:
            draw_text(surf, label, (hx + off, header_y), 15, Palette.TEXT_MUTED, bold=True)
        pygame.draw.line(surf, Palette.PANEL_BORDER,
                         (hx, header_y + 22), (hx + table_w - 40, header_y + 22))

        result_meta = {
            "WIN": ("MENANG", Palette.GREEN),
            "LOSE": ("KALAH", Palette.ACCENT),
            "MID": ("SELESAI", Palette.TEXT_DIM),
        }
        y = header_y + 32
        for i, e in enumerate(self.history[:10]):
            if i % 2 == 0:
                row_rect = (hx - 10, y - 6, table_w - 20, 40)
                draw_gradient_rect(surf, row_rect, (34, 38, 58, 120), (28, 32, 48, 80),
                                   border_radius=8)

            result = str(e.get("result", "MID")).upper()
            label, rcol = result_meta.get(result, result_meta["MID"])
            tag_rect = (hx, y - 2, 96, 24)
            draw_gradient_rect(surf, tag_rect, rcol,
                               tuple(max(0, c - 45) for c in rcol), border_radius=12)
            draw_text(surf, label, (hx + 48, y + 10), 12, Palette.BG, bold=True, center=True)

            mode = str(e.get("match_mode", "ranked")).capitalize()
            draw_text(surf, mode, (hx + 150, y - 2), 15, Palette.TEXT_DIM)

            pos = e.get("finish_position", "-")
            total = e.get("player_count", "-")
            draw_text(surf, f"{pos} / {total}", (hx + 280, y - 2), 15, Palette.TEXT)

            is_ranked = str(e.get("match_mode", "ranked")).lower() == "ranked"
            delta = int(e.get("point_change", 0) or 0)
            if is_ranked:
                dcol = Palette.GREEN if delta > 0 else (Palette.ACCENT if delta < 0 else Palette.TEXT_DIM)
                dtext = f"+{delta}" if delta > 0 else str(delta)
            else:
                dcol = Palette.BLUE
                dtext = "Classic"
            draw_text(surf, dtext, (hx + 440, y - 2), 15, dcol, bold=True)

            winner = str(e.get("winner_name", "-") or "-")
            if len(winner) > 14:
                winner = winner[:13] + "…"
            draw_text(surf, winner, (hx + 560, y - 2), 15, Palette.GOLD)

            draw_text(surf, str(e.get("ended_at", "") or ""), (hx + 740, y - 2), 13,
                      Palette.TEXT_MUTED)
            y += 48

        if len(self.history) > 10:
            draw_text(surf, f"Menampilkan 10 dari {len(self.history)} match terakhir",
                      (cx, y + 14), 13, Palette.TEXT_MUTED, center=True)

    def _draw_leaderboard(self, surf):
        cx = config.WINDOW_WIDTH // 2
        title = "🏆  Global Ranked Leaderboard"
        draw_text(surf, title, (cx, 55), 32, Palette.TEXT, bold=True,
                  center=True, shadow=True)

        # Table panel
        table_w = 840
        hx = cx - table_w // 2 + 20

        if self.entries:
            display_count = min(10, len(self.entries))
            panel_rect = (cx - table_w // 2, 95, table_w, 50 + display_count * 48)
            draw_shadow_rect(surf, panel_rect, offset=5, alpha=40, border_radius=14)
            draw_gradient_rect(surf, panel_rect, (30, 34, 52), (22, 26, 40),
                               border_radius=14)
            pygame.draw.rect(surf, Palette.PANEL_BORDER, panel_rect, 1,
                             border_radius=14)

        # Header row
        header_y = 110
        headers = [("#", 0), ("Username", 50), ("Poin", 310), ("Rank", 420),
                   ("Win Rate", 560), ("M/W/L", 690)]
        for label, offset in headers:
            draw_text(surf, label, (hx + offset, header_y), 15,
                      Palette.TEXT_MUTED, bold=True)

        # Separator
        pygame.draw.line(surf, Palette.PANEL_BORDER,
                         (hx, header_y + 22), (hx + table_w - 40, header_y + 22))

        y = header_y + 32
        for i, e in enumerate(self.entries[:10], 1):
            # Row with alternating bg
            row_rect = (hx - 10, y - 6, table_w - 20, 40)
            if i % 2 == 0:
                draw_gradient_rect(surf, row_rect, (34, 38, 58, 120), (28, 32, 48, 80),
                                   border_radius=8)

            # Position medal (top 3)
            medal_colors = {1: Palette.GOLD, 2: (195, 200, 215), 3: (186, 150, 95)}
            if i <= 3:
                mc = medal_colors[i]
                pygame.draw.circle(surf, mc, (hx + 12, y + 8), 13)
                draw_text(surf, str(i), (hx + 12, y + 8), 14,
                          Palette.BG, bold=True, center=True)
            else:
                draw_text(surf, str(i), (hx + 6, y - 2), 16, Palette.TEXT)

            # Username
            draw_text(surf, e.get("username", "-"), (hx + 50, y - 2), 17, Palette.TEXT)

            # Points
            draw_text(surf, str(e.get("total_point", 0)), (hx + 310, y - 2), 17,
                      Palette.GOLD, bold=True)

            # Rank tier badge
            tier = e.get("rank_tier", "Bronze")
            rank_col = Palette.RANK_COLORS.get(tier, Palette.TEXT_DIM)
            tier_rect = (hx + 420, y - 2, 70, 22)
            draw_gradient_rect(surf, tier_rect, rank_col,
                               tuple(max(0, c - 40) for c in rank_col),
                               border_radius=11)
            draw_text(surf, tier, (hx + 455, y + 9), 12,
                      Palette.BG, bold=True, center=True)

            # Win rate
            wr = round(e.get("win_rate", 0) * 100)
            wr_col = Palette.GREEN if wr >= 50 else Palette.TEXT_DIM
            draw_text(surf, f"{wr}%", (hx + 560, y - 2), 17, wr_col)

            # M/W/L
            draw_text(surf, f"{e.get('total_match', 0)}/{e.get('total_win', 0)}/{e.get('total_lose', 0)}",
                      (hx + 690, y - 2), 16, Palette.TEXT_DIM)

            y += 48

        if not self.entries:
            draw_text(surf, "Belum ada data.", (cx, 300), 20,
                      Palette.TEXT_DIM, center=True)
