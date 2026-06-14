"""Lobby: menu utama — desain premium."""
import pygame

import config
from shared.packet_types import C2S, S2C
from shared.constants import MATCH_MODE_RANKED, MATCH_MODE_CLASSIC
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, TextInput, Palette, draw_text,
    draw_bg_gradient, draw_shadow_rect, draw_gradient_rect,
    draw_glow, draw_particles,
)
from client.ui import sounds


class LobbyScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = config.WINDOW_WIDTH // 2
        self.selected_mode = MATCH_MODE_RANKED
        self.btn_ranked = Button((cx - 170, 258, 160, 42), "Ranked", self._ranked,
                                 color=Palette.GOLD, font_size=17)
        self.btn_classic = Button((cx + 10, 258, 160, 42), "Classic", self._classic,
                                  color=Palette.PANEL_LIGHT, font_size=17)
        self.btn_quick = Button((cx - 170, 318, 340, 54), "⚡  Quick Match", self._quick,
                                color=(56, 193, 114))
        self.btn_create = Button((cx - 170, 388, 340, 54), "🏠  Buat Room", self._create,
                                 color=Palette.BLUE)
        self.join_input = TextInput((cx - 170, 462, 210, 48), "Kode Room", max_len=8)
        self.btn_join = Button((cx + 50, 462, 120, 48), "Gabung", self._join,
                               color=Palette.PURPLE)
        self.btn_board = Button((cx - 170, 538, 165, 48), "🏆  Leaderboard", self._leaderboard,
                                color=Palette.PANEL_LIGHT, font_size=16)
        self.btn_history = Button((cx + 5, 538, 165, 48), "📜  Riwayat", self._history,
                                  color=Palette.PANEL_LIGHT, font_size=16)
        self.btn_logout = Button((cx - 170, 598, 340, 48), "🚪  Keluar", self._logout,
                                 color=Palette.ACCENT)
        self.message = ""
        self._tick = 0
        self._sync_mode_buttons()

    def on_enter(self):
        sounds.play_music("lobby")
        self.state.net.send(C2S.GET_STATS, {"user_id": self.state.user_id})

    def _sync_mode_buttons(self):
        if self.selected_mode == MATCH_MODE_RANKED:
            self.btn_ranked.color = Palette.GOLD
            self.btn_ranked.hover_color = tuple(min(255, c + 25) for c in Palette.GOLD)
            self.btn_classic.color = Palette.PANEL_LIGHT
            self.btn_classic.hover_color = tuple(min(255, c + 25) for c in Palette.PANEL_LIGHT)
        else:
            self.btn_ranked.color = Palette.PANEL_LIGHT
            self.btn_ranked.hover_color = tuple(min(255, c + 25) for c in Palette.PANEL_LIGHT)
            self.btn_classic.color = Palette.BLUE
            self.btn_classic.hover_color = tuple(min(255, c + 25) for c in Palette.BLUE)

    def _ranked(self):
        self.selected_mode = MATCH_MODE_RANKED
        self._sync_mode_buttons()

    def _classic(self):
        self.selected_mode = MATCH_MODE_CLASSIC
        self._sync_mode_buttons()

    def _quick(self):
        self.state.net.send(C2S.MATCHMAKE_REQ, {"match_mode": self.selected_mode})
        self.message = "Mencari lawan ranked..." if self.selected_mode == MATCH_MODE_RANKED else "Mencari lawan classic..."

    def _create(self):
        self.state.net.send(C2S.CREATE_ROOM_REQ, {"match_mode": self.selected_mode})

    def _join(self):
        code = self.join_input.text.strip().upper()
        if code:
            self.state.net.send(C2S.JOIN_ROOM_REQ, {"room_code": code})

    def _leaderboard(self):
        self.app.scenes["leaderboard"].mode = "leaderboard"
        self.state.net.send(C2S.GET_TOP_GLOBAL, {"limit": 100})
        self.go("leaderboard")

    def _history(self):
        self.app.scenes["leaderboard"].mode = "history"
        self.state.net.send(C2S.GET_MATCH_HISTORY,
                            {"user_id": self.state.user_id, "limit": 30})
        self.go("leaderboard")

    def _logout(self):
        self.state.net.close()
        self.app.connected = self.state.net.connect(getattr(self.app, 'host', config.CLIENT_CONNECT_HOST))
        self.state.user_id = None
        self.state.username = None
        self.state.token = None
        self.state.room_id = None
        self.state.game_state = None
        self.state.hand = []
        self.state.is_spectator = False
        self.state.match_mode = MATCH_MODE_RANKED
        self.go("login")

    def handle_event(self, event):
        # Catat status fokus field kode SEBELUM TextInput memprosesnya, karena
        # menekan Enter membuat field menjadi tidak aktif di dalam handle().
        join_active = self.join_input.active
        for w in (self.btn_ranked, self.btn_classic, self.btn_quick,
                  self.btn_create, self.join_input,
                  self.btn_join, self.btn_board, self.btn_history, self.btn_logout):
            w.handle(event)
        # Enter saat mengetik kode room langsung mencoba gabung (paritas dengan web).
        if (event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                and join_active):
            self._join()

    def handle_packet(self, pkt):
        t, p = pkt["type"], pkt["payload"]
        if t == S2C.STATS:
            self.state.stats = p
        elif t in (S2C.ROOM_CREATED, S2C.JOIN_OK, S2C.MATCH_FOUND):
            self.state.room_id = p.get("room_id")
            self.state.room_code = p.get("room_code")
            self.state.host_id = p.get("host_id")
            self.state.match_mode = p.get("match_mode", self.selected_mode)
            self.state.players = p.get("players", [])
            self.state.is_spectator = False
            self.go("room")
        elif t == S2C.JOIN_FAIL:
            reason = p.get("reason", "")
            self.message = {
                "room_not_found": "Room tidak ditemukan.",
                "room_full": "Room penuh.",
                "already_started": "Match sudah dimulai.",
            }.get(reason, f"Gagal: {reason}")
        elif t == S2C.FORCE_LOGOUT:
            self.go("login")

    def update(self, dt):
        self._tick += 1

    def draw(self, surf):
        draw_bg_gradient(surf, (18, 22, 38), (8, 10, 18))
        draw_particles(surf, self._tick, count=20, color=(80, 100, 180))

        cx = config.WINDOW_WIDTH // 2
        s = self.state.stats or {}

        # ---- Header: welcome + stats dashboard ----
        rank = s.get("rank_tier", "Bronze")
        rank_col = Palette.RANK_COLORS.get(rank, Palette.TEXT)
        pts = s.get("total_point", 0)
        matches = s.get("total_match", 0)
        wins = s.get("total_win", 0)
        wr = round(s.get("win_rate", 0) * 100)

        # 1. Profile Panel
        profile_rect = (40, 30, 320, 85)
        draw_shadow_rect(surf, profile_rect, offset=4, alpha=40, border_radius=14)
        draw_gradient_rect(surf, profile_rect, (32, 36, 55), (24, 28, 42), border_radius=14)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, profile_rect, 1, border_radius=14)

        draw_text(surf, "Selamat datang,", (60, 42), 14, Palette.TEXT_DIM)
        draw_text(surf, str(self.state.username), (60, 62), 22, Palette.TEXT, bold=True)

        badge_rect = pygame.Rect(230, 59, 85, 24)
        draw_gradient_rect(surf, badge_rect, rank_col, tuple(max(0, c - 40) for c in rank_col),
                           border_radius=12)
        draw_text(surf, rank, (230 + 42.5, 59 + 12), 12, Palette.TEXT,
                  bold=True, center=True)

        # 2. Stats Dashboard Cards
        stats_data = [
            ("TOTAL POIN", f"{pts} pts", Palette.GOLD),
            ("TOTAL MATCH", str(matches), Palette.TEXT),
            ("TOTAL MENANG", str(wins), Palette.GREEN),
            ("WIN RATE", f"{wr}%", Palette.GREEN if wr >= 50 else Palette.BLUE)
        ]

        for i, (title, value, val_color) in enumerate(stats_data):
            x = 380 + i * 220
            card_rect = (x, 30, 200, 85)
            draw_shadow_rect(surf, card_rect, offset=4, alpha=40, border_radius=14)
            draw_gradient_rect(surf, card_rect, (32, 36, 55), (24, 28, 42), border_radius=14)
            pygame.draw.rect(surf, Palette.PANEL_BORDER, card_rect, 1, border_radius=14)
            
            # Subtitle
            draw_text(surf, title, (x + 100, 50), 12, Palette.TEXT_DIM, bold=True, center=True)
            # Value
            draw_text(surf, value, (x + 100, 76), 20, val_color, bold=True, center=True)

        # Ping
        draw_text(surf, f"Ping: {self.state.net.ping_ms} ms",
                  (config.WINDOW_WIDTH - 150, 12), 13, Palette.TEXT_MUTED)

        # ---- Title ----
        draw_glow(surf, (cx, 198), 60, Palette.GOLD, intensity=0.4)
        draw_text(surf, "Lobby", (cx, 198), 36, Palette.TEXT, bold=True,
                  center=True, shadow=True)

        # ---- Action panel ----
        panel_rect = (cx - 200, 238, 400, 430)
        draw_shadow_rect(surf, panel_rect, offset=5, alpha=40, border_radius=16)
        draw_gradient_rect(surf, panel_rect, (30, 34, 52), (22, 26, 40),
                           border_radius=16)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, panel_rect, 1, border_radius=16)

        draw_text(surf, "Mode Match", (cx, 246), 15, Palette.TEXT_DIM,
                  bold=True, center=True)

        for w in (self.btn_ranked, self.btn_classic, self.btn_quick,
                  self.btn_create, self.join_input,
                  self.btn_join, self.btn_board, self.btn_history, self.btn_logout):
            w.draw(surf)

        if self.message:
            draw_text(surf, self.message, (cx, 680), 17, Palette.ACCENT, center=True)
