import math
import pygame

import config
from shared.packet_types import C2S, S2C
from shared.constants import PlayerRole
from client.scenes.base import Scene
from client.ui.widgets import (
    Button, Palette, draw_text,
    draw_shadow_rect, draw_gradient_rect, draw_glow,
)
from client.ui import assets
from client.ui import sounds

class GameScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.card_rects: list[tuple[pygame.Rect, dict, int]] = []
        self.deck_rect = pygame.Rect(0, 0, config.CARD_W, config.CARD_H)
        self.btn_uno = Button((config.WINDOW_WIDTH - 170, 480, 130, 52), "UNO!",
                              self._uno_self, color=Palette.ACCENT)
        self.btn_accuse_uno = Button((config.WINDOW_WIDTH - 170, 410, 130, 52), "Lapor UNO!",
                                     self._uno_accuse, color=Palette.PURPLE)
        self.btn_leave = Button((config.WINDOW_WIDTH - 150, 20, 120, 38), "Keluar",
                                self._leave, color=Palette.PANEL_LIGHT, font_size=16)
        self.btn_voice = Button((config.WINDOW_WIDTH - 285, 20, 120, 38), "Mic Off",
                                self._toggle_voice, color=Palette.PANEL_LIGHT,
                                font_size=16)
        self.btn_play_selected = Button((config.WINDOW_WIDTH // 2 - 150, 505, 140, 40),
                                        "Mainkan", self._play_selected,
                                        color=Palette.GREEN, font_size=16)
        self.btn_clear_selected = Button((config.WINDOW_WIDTH // 2 + 10, 505, 140, 40),
                                         "Batal", self._clear_selection,
                                         color=Palette.PANEL_LIGHT, font_size=16)
        self.selected_cards: list[dict] = []
        self.selected_indices: list[int] = []
        self.choosing_color_card: dict | None = None
        self.color_buttons: list[tuple[pygame.Rect, str]] = []
        self.message = ""
        self.message_timer = 0.0
        self._tick = 0
        self._hover_card_idx = -1
        self._prev_turn = None

    def on_enter(self):
        self.choosing_color_card = None
        self.selected_cards = []
        self.selected_indices = []
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

    def _uno_self(self):
        self.state.net.send(C2S.CALL_UNO, {"mode": "self"})

    def _uno_accuse(self):
        self.state.net.send(C2S.CALL_UNO, {"mode": "catch"})

    def _leave(self):
        sounds.play("leave")
        if self.state.voice:
            self.state.voice.leave()
        self.state.net.send(C2S.LEAVE_ROOM, {})

    def _play(self, card: dict, chosen_color: str | None = None, cards: list[dict] | None = None):
        payload = {"card": card, "chosen_color": chosen_color}
        if cards and len(cards) > 1:
            payload["cards"] = cards
        self.state.net.send(C2S.PLAY_CARD, payload)
        if card.get("ctype") in ("Draw", "Wild_Draw"):
            sounds.play("card_play_plus")
        else:
            sounds.play("card_play")

    def _draw(self):
        self.selected_cards = []
        self.state.net.send(C2S.DRAW_CARD, {})

    def _set_message(self, text):
        self.message = text
        self.message_timer = 2.5

    def handle_event(self, event):
        self.btn_voice.handle(event)
        self.btn_leave.handle(event)
        if self.state.is_spectator:
            return
        if getattr(self, "show_uno_button", False):
            self.btn_uno.handle(event)
        if getattr(self, "show_accuse_button", False):
            self.btn_accuse_uno.handle(event)
        if self.selected_cards:
            self.btn_play_selected.handle(event)
            self.btn_clear_selected.handle(event)

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.choosing_color_card is not None:
                self.choosing_color_card = None
                sounds.play("click")
            elif self.selected_cards:
                self._clear_selection()
            return

        if event.type == pygame.MOUSEMOTION:
            self._hover_card_idx = -1
            if self.choosing_color_card is None:
                for i, (rect, _, _) in enumerate(reversed(self.card_rects)):
                    if rect.collidepoint(event.pos):
                        self._hover_card_idx = len(self.card_rects) - 1 - i
                        break

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.choosing_color_card is not None:
                for rect, color in self.color_buttons:
                    if rect.collidepoint(event.pos):
                        self._play(self.choosing_color_card, color)
                        self.choosing_color_card = None
                        self.selected_cards = []
                        return
                self.choosing_color_card = None
                sounds.play("click")
                return
            if self.deck_rect.collidepoint(event.pos) and self._is_my_turn():
                self._draw()
                return
            for rect, card, idx in reversed(self.card_rects):
                if rect.collidepoint(event.pos):
                    self._click_card(card, idx)
                    return

    def _click_card(self, card: dict, hand_index: int):
        sounds.play("click")
        if not self._is_my_turn():
            self._set_message("Bukan giliran Anda")
            return
        if card["color"] == "Wild":
            self.selected_cards = []
            self.selected_indices = []
            self.choosing_color_card = card
        else:
            self._toggle_selected_card(card, hand_index)

    def _toggle_selected_card(self, card: dict, hand_index: int):
        if not str(card.get("ctype", "")).isdigit():
            self._play(card)
            self.selected_cards = []
            self.selected_indices = []
            return
        gs = self.state.game_state or {}
        if gs.get("pending_draw", 0) > 0:
            self._play(card)
            self.selected_cards = []
            self.selected_indices = []
            return

        if self.selected_cards and self.selected_cards[0].get("ctype") != card.get("ctype"):
            self.selected_cards = []
            self.selected_indices = []

        if hand_index in self.selected_indices:
            pos = self.selected_indices.index(hand_index)
            self.selected_indices.pop(pos)
            self.selected_cards.pop(pos)
        else:
            self.selected_indices.append(hand_index)
            self.selected_cards.append(card)

    def _clear_selection(self):
        self.selected_cards = []
        self.selected_indices = []

    def _play_selected(self):
        if not self.selected_cards:
            return
        cards = list(self.selected_cards)
        self._play(cards[0], cards=cards)
        if len(cards) > 1:
            self._set_message(f"Memainkan {len(cards)} kartu angka {cards[0]['ctype']}")
        self.selected_cards = []
        self.selected_indices = []

    def _is_my_turn(self):
        gs = self.state.game_state
        return gs and gs.get("current_turn") == self.state.user_id

    def handle_packet(self, pkt):
        t, p = pkt["type"], pkt["payload"]
        if t == S2C.STATE_UPDATE:
            old_turn = (self.state.game_state or {}).get("current_turn")
            self.state.game_state = p["state"]
            if "hand" in p:
                self.state.hand = p["hand"]
                kept = [
                    (idx, card)
                    for idx, card in zip(self.selected_indices, self.selected_cards)
                    if idx < len(self.state.hand) and self.state.hand[idx] == card
                ]
                self.selected_indices = [idx for idx, _ in kept]
                self.selected_cards = [card for _, card in kept]
            new_turn = p["state"].get("current_turn")
            if new_turn == self.state.user_id and old_turn != new_turn:
                sounds.play("your_turn", 0.4)
            if new_turn != self.state.user_id:
                self.selected_cards = []
                self.selected_indices = []
        elif t == S2C.DRAW_RESULT:
            self.state.hand.append(p["card"])
            sounds.play("card_draw", 0.4)
        elif t == S2C.DRAW_STACK_RESULT:
            count = p.get("count", len(p.get("cards", [])))
            self._set_message(f"Anda mengambil {count} kartu!")
            sounds.play("card_play_plus")
        elif t == S2C.PLAYER_WIN:
            if p["user_id"] == self.state.user_id:
                self._set_message("Anda menang! Beralih ke mode penonton.")
                sounds.play("win", 0.7)
        elif t == S2C.ENTER_SPECTATOR:
            self.state.is_spectator = True
            self.go("spectator")
        elif t == S2C.UNO_ANNOUNCE:
            self._set_message("Pemain memanggil UNO!")
            sounds.play("uno_call", 0.6)
        elif t == S2C.UNO_PENALTY:
            self.state.hand.extend(p.get("cards", []))
            reason = p.get("reason", "")
            if reason == "caught":
                self._set_message("Anda tertangkap! Lupa UNO: +2 kartu")
            else:
                self._set_message("Belum waktunya UNO! Penalti +2 kartu")
            sounds.play("penalty", 0.5)
        elif t == S2C.UNO_CATCH:
            caught_name = p.get("caught_name", "Pemain")
            if p.get("caught_id") == self.state.user_id:
                self._set_message(f"Anda tertangkap lupa UNO! +2 kartu")
            elif p.get("catcher_id") == self.state.user_id:
                self._set_message(f"Anda menangkap {caught_name} lupa UNO!")
                sounds.play("catch", 0.6)
            else:
                self._set_message(f"{caught_name} tertangkap lupa UNO!")
        elif t == S2C.ACTION_REJECTED:
            self.selected_cards = []
            self.selected_indices = []
            reason = p.get("reason", "")
            self._set_message({
                "not_your_turn": "Bukan giliran Anda",
                "invalid_card": "Kartu tidak valid",
                "must_stack_or_draw": "Harus tumpuk kartu + atau ambil kartu!",
                "spectator_cannot_act": "Penonton tidak bisa beraksi",
                "already_drew": "Anda sudah menarik 1 kartu giliran ini",
            }.get(reason, reason))
            sounds.play("error", 0.3)
        elif t == S2C.MATCH_RESULT:
            self.selected_cards = []
            self.selected_indices = []
            self.state.last_result = p
            self.state.match_mode = p.get("match_mode", self.state.match_mode)
            self.go("result")
        elif t == S2C.LEFT_ROOM:
            if self.state.voice:
                self.state.voice.leave()
            self.state.room_id = None
            self.state.match_mode = "ranked"
            self.go("lobby")
        elif t == S2C.FORCE_LOGOUT:
            self.go("login")

    def _update_uno_flags(self):
        gs = self.state.game_state
        self.show_uno_button = False
        self.show_accuse_button = False
        if not self.state.is_spectator and gs:
            me = None
            for pl in gs.get("players", []):
                if pl["user_id"] == self.state.user_id:
                    me = pl
                    break
            if me and me.get("is_active", True) and not me.get("called_uno", False) \
                    and len(self.state.hand) >= 1:
                self.show_uno_button = True

            for pl in gs.get("players", []):
                if pl["user_id"] != self.state.user_id and pl.get("is_active", True):
                    if pl.get("hand_count") == 1 and not pl.get("called_uno", False):
                        self.show_accuse_button = True
                        break

    def update(self, dt):
        self._tick += 1
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""
        self._update_uno_flags()

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

        gs = self.state.game_state
        if not gs:
            draw_text(surf, "Memuat...", (config.WINDOW_WIDTH // 2, config.WINDOW_HEIGHT // 2),
                      24, Palette.TEXT, center=True)
            return

        self._draw_opponents(surf, gs)
        self._draw_center(surf, gs)
        self._draw_hand(surf, gs)
        self._draw_hud(surf, gs)
        if self.choosing_color_card is not None:
            self._draw_color_picker(surf)
        self.btn_leave.draw(surf)

    def _draw_opponents(self, surf, gs):
        others = [pl for pl in gs["players"] if pl["user_id"] != self.state.user_id]
        count = len(others)
        if count == 1:
            slots = [(config.WINDOW_WIDTH // 2, 90)]
        elif count == 2:
            slots = [(300, 95), (config.WINDOW_WIDTH - 300, 95)]
        else:
            slots = [(150, config.WINDOW_HEIGHT // 2 - 80),
                     (config.WINDOW_WIDTH // 2, 90),
                     (config.WINDOW_WIDTH - 150, config.WINDOW_HEIGHT // 2 - 80)]
        for i, pl in enumerate(others[:3]):
            x, y = slots[i]
            is_turn = gs.get("current_turn") == pl["user_id"]

            if is_turn:
                draw_glow(surf, (x, y - 10), 60, Palette.GOLD, intensity=0.8)

            plate_w = 140
            plate_rect = (x - plate_w // 2, y - 55, plate_w, 28)
            draw_gradient_rect(surf, plate_rect,
                               (0, 0, 0, 140) if not is_turn else (*Palette.GOLD[:3], 180),
                               (0, 0, 0, 100) if not is_turn else (*Palette.GOLD[:3], 120),
                               border_radius=14)

            name = pl["username"]
            name_col = Palette.TEXT if not is_turn else Palette.BG
            if pl.get("has_won"):
                name += " 🏆"
            elif not pl.get("is_active", True):
                name += " (keluar)"
            draw_text(surf, name, (x, y - 41), 15, name_col, bold=is_turn, center=True)

            back = assets.card_back(42, 60)
            hand_count = min(pl["hand_count"], 10)
            fan_w = hand_count * 6 + 42
            sx = x - fan_w // 2
            for c in range(hand_count):
                surf.blit(back, (sx + c * 6, y - 30))

            badge_rect = (x - 16, y + 34, 32, 20)
            draw_gradient_rect(surf, badge_rect, (0, 0, 0, 160), (0, 0, 0, 100),
                               border_radius=10)
            draw_text(surf, str(pl["hand_count"]), (x, y + 44), 13,
                      Palette.TEXT, bold=True, center=True)

            if pl.get("called_uno"):
                uno_rect = (x - 25, y + 58, 50, 18)
                draw_gradient_rect(surf, uno_rect, Palette.ACCENT,
                                   tuple(max(0, c - 45) for c in Palette.ACCENT),
                                   border_radius=9)
                draw_text(surf, "UNO", (x, y + 67), 11, Palette.TEXT, bold=True, center=True)

    def _draw_center(self, surf, gs):
        cx, cy = config.WINDOW_WIDTH // 2, config.WINDOW_HEIGHT // 2

        self.deck_rect = pygame.Rect(cx - 140, cy - config.CARD_H // 2,
                                     config.CARD_W, config.CARD_H)
        if self._is_my_turn():
            draw_glow(surf, self.deck_rect.center, 70, Palette.BLUE, intensity=0.5)
        draw_shadow_rect(surf, self.deck_rect, offset=4, alpha=60, border_radius=10)
        surf.blit(assets.card_back(), self.deck_rect.topleft)

        draw_text(surf, f"Deck: {gs.get('draw_pile_count', 0)}",
                  (self.deck_rect.centerx, self.deck_rect.bottom + 16), 13,
                  Palette.TEXT_DIM, center=True)

        top = gs.get("top_card")
        if top:
            from server.core.card import Card
            asset = Card.from_dict(top).asset_name
            discard_x = cx + 50
            discard_y = cy - config.CARD_H // 2
            discard_rect = pygame.Rect(discard_x, discard_y, config.CARD_W, config.CARD_H)
            draw_shadow_rect(surf, discard_rect, offset=5, alpha=70, border_radius=10)
            surf.blit(assets.card_surface(asset), (discard_x, discard_y))

        ac = gs.get("active_color")
        if ac and ac in Palette.UNO_COLORS:
            indicator_x = cx + 50 + config.CARD_W + 35
            draw_glow(surf, (indicator_x, cy), 30, Palette.UNO_COLORS[ac], intensity=0.8)
            pygame.draw.circle(surf, Palette.UNO_COLORS[ac], (indicator_x, cy), 18)
            pygame.draw.circle(surf, (255, 255, 255, 80), (indicator_x, cy), 18, 2)
            draw_text(surf, ac, (indicator_x, cy + 30), 12,
                      Palette.TEXT_DIM, center=True)

        direction = gs.get("direction", 1)
        arrow_y = cy - 100
        pulse = 0.5 + 0.5 * math.sin(self._tick * 0.08)
        arrow_alpha = int(140 + 115 * pulse)
        arrow_surf = pygame.Surface((200, 30), pygame.SRCALPHA)
        if direction == 1:
            arrow_text = "→  Searah Jarum Jam"
        else:
            arrow_text = "←  Berlawanan Jarum Jam"
        draw_text(arrow_surf, arrow_text, (100, 15), 15,
                  (*Palette.TEXT_DIM[:3], arrow_alpha), center=True)
        surf.blit(arrow_surf, (cx - 100, arrow_y))

        pending = gs.get("pending_draw", 0)
        if pending > 0:
            pd_type = gs.get("pending_draw_type", "")
            pd_label = f"+{pending}"
            pd_color = Palette.ACCENT if pd_type == "Draw" else Palette.PURPLE

            pd_x = cx
            pd_y = cy + config.CARD_H // 2 + 40
            draw_glow(surf, (pd_x, pd_y), 50, pd_color, intensity=1.0)

            badge_w = 100
            badge_rect = (pd_x - badge_w // 2, pd_y - 18, badge_w, 36)
            draw_gradient_rect(surf, badge_rect, pd_color,
                               tuple(max(0, c - 40) for c in pd_color),
                               border_radius=18)
            draw_text(surf, pd_label, (pd_x, pd_y), 22, Palette.TEXT,
                      bold=True, center=True)
            draw_text(surf, "Tumpukan!", (pd_x, pd_y + 26), 12,
                      pd_color, center=True)

    def _draw_hand(self, surf, gs):
        self.card_rects = []
        hand = self.state.hand
        if not hand:
            return
        from server.core.card import Card
        top = Card.from_dict(gs["top_card"]) if gs.get("top_card") else None
        ac = gs.get("active_color", "")
        pending = gs.get("pending_draw", 0)
        pending_type = gs.get("pending_draw_type", "")
        n = len(hand)
        total_w = min(n * (config.CARD_W + 8), config.WINDOW_WIDTH - 100)
        gap = (total_w - config.CARD_W) / max(1, n - 1) if n > 1 else 0
        start_x = (config.WINDOW_WIDTH - total_w) // 2
        y = config.WINDOW_HEIGHT - config.CARD_H - 28
        my_turn = self._is_my_turn()

        for i, card in enumerate(hand):
            x = int(start_x + i * gap)
            cobj = Card.from_dict(card)

            if pending > 0:
                playable = my_turn and cobj.is_any_draw
            else:
                playable = my_turn and top and cobj.matches(top, ac)

            is_hover = (i == self._hover_card_idx)
            is_selected = i in self.selected_indices
            y_offset = 0
            if playable:
                y_offset = -14
            if is_selected:
                y_offset -= 18
            if is_hover:
                y_offset -= 10

            yy = y + y_offset
            rect = pygame.Rect(x, yy, config.CARD_W, config.CARD_H)

            if is_hover:
                draw_shadow_rect(surf, rect, offset=6, alpha=80, border_radius=10)
            else:
                draw_shadow_rect(surf, rect, offset=3, alpha=40, border_radius=10)

            surf.blit(assets.card_surface(cobj.asset_name), rect.topleft)

            if playable:
                glow_col = Palette.GOLD if not cobj.is_any_draw else Palette.ACCENT
                glow_rect = rect.inflate(6, 6)
                pygame.draw.rect(surf, (*glow_col[:3], 100), glow_rect, 3,
                                 border_radius=10)
                if is_hover:
                    pygame.draw.rect(surf, glow_col, rect, 3, border_radius=8)

            if is_selected:
                selected_rect = rect.inflate(10, 10)
                pygame.draw.rect(surf, Palette.GREEN, selected_rect, 4, border_radius=12)
                badge_rect = (rect.right - 28, rect.top + 8, 22, 22)
                draw_gradient_rect(surf, badge_rect, Palette.GREEN,
                                   tuple(max(0, c - 40) for c in Palette.GREEN),
                                   border_radius=11)
                draw_text(surf, str(self.selected_indices.index(i) + 1),
                          (rect.right - 17, rect.top + 19), 12,
                          Palette.BG, bold=True, center=True)

            self.card_rects.append((rect, card, i))

    def _draw_hud(self, surf, gs):
        cx = config.WINDOW_WIDTH // 2

        cur = gs.get("current_turn")
        if cur == self.state.user_id:
            bar_surf = pygame.Surface((config.WINDOW_WIDTH, 44), pygame.SRCALPHA)
            draw_gradient_rect(bar_surf, (0, 0, config.WINDOW_WIDTH, 44),
                               (*Palette.GOLD[:3], 40), (*Palette.GOLD[:3], 0))
            surf.blit(bar_surf, (0, 0))
            draw_text(surf, "🎯  Giliran ANDA", (cx, 24), 22,
                      Palette.GOLD, bold=True, center=True, shadow=True)
        else:
            bar_surf = pygame.Surface((config.WINDOW_WIDTH, 38), pygame.SRCALPHA)
            bar_surf.fill((0, 0, 0, 60))
            surf.blit(bar_surf, (0, 0))
            draw_text(surf, "Menunggu giliran lawan...", (cx, 20), 17,
                      Palette.TEXT_DIM, center=True)

        draw_text(surf, f"Ping: {self.state.net.ping_ms} ms", (20, 22), 13,
                  Palette.TEXT_MUTED)
        self._draw_voice(surf)

        if getattr(self, "show_uno_button", False):
            draw_glow(surf, self.btn_uno.rect.center, 50, Palette.ACCENT, intensity=0.6)
            self.btn_uno.draw(surf)

        if getattr(self, "show_accuse_button", False):
            draw_glow(surf, self.btn_accuse_uno.rect.center, 50, Palette.PURPLE, intensity=0.6)
            self.btn_accuse_uno.draw(surf)

        me = None
        for pl in gs.get("players", []):
            if pl["user_id"] == self.state.user_id:
                me = pl
                break
        if me and me.get("called_uno"):
            uno_status_rect = (config.WINDOW_WIDTH - 170, 550, 130, 30)
            draw_gradient_rect(surf, uno_status_rect, Palette.GREEN,
                               tuple(max(0, c - 40) for c in Palette.GREEN),
                               border_radius=15)
            draw_text(surf, "SUDAH UNO", (config.WINDOW_WIDTH - 105, 565), 14,
                      Palette.TEXT, bold=True, center=True)

        if self.selected_cards:
            number = self.selected_cards[0].get("ctype", "")
            draw_text(surf, f"{len(self.selected_cards)} kartu angka {number} dipilih",
                      (cx, 485), 15, Palette.GREEN, bold=True, center=True)
            self.btn_play_selected.label = "Mainkan"
            self.btn_play_selected.draw(surf)
            self.btn_clear_selected.draw(surf)

        if self.message:
            msg_w = max(300, len(self.message) * 10 + 40)
            msg_rect = (cx - msg_w // 2, config.WINDOW_HEIGHT - 178, msg_w, 36)
            draw_gradient_rect(surf, msg_rect, (0, 0, 0, 180), (0, 0, 0, 120),
                               border_radius=18)
            draw_text(surf, self.message, (cx, config.WINDOW_HEIGHT - 160), 16,
                      Palette.YELLOW, bold=True, center=True)

    def _draw_voice(self, surf):
        if not self.state.voice:
            return
        live = self.state.voice.mic_enabled
        self.btn_voice.label = "Mic On" if live else "Mic Off"
        self.btn_voice.color = Palette.GREEN if live else Palette.PANEL_LIGHT
        self.btn_voice.hover_color = Palette.GREEN_HOVER if live else Palette.PANEL_HOVER
        self.btn_voice.draw(surf)
        draw_text(surf, self.state.voice.status,
                  (config.WINDOW_WIDTH - 285, 66), 12, Palette.TEXT_MUTED)

    def _draw_color_picker(self, surf):
        overlay = pygame.Surface((config.WINDOW_WIDTH, config.WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surf.blit(overlay, (0, 0))

        cx = config.WINDOW_WIDTH // 2
        cy = config.WINDOW_HEIGHT // 2

        panel_w, panel_h = 480, 220
        panel_rect = (cx - panel_w // 2, cy - panel_h // 2, panel_w, panel_h)
        draw_shadow_rect(surf, panel_rect, offset=8, alpha=80, border_radius=20)
        draw_gradient_rect(surf, panel_rect, (36, 40, 60), (24, 28, 42),
                           border_radius=20)
        pygame.draw.rect(surf, Palette.PANEL_BORDER, panel_rect, 1, border_radius=20)

        draw_text(surf, "Pilih Warna", (cx, cy - 70), 26, Palette.TEXT,
                  bold=True, center=True)

        self.color_buttons = []
        colors = ["Red", "Green", "Blue", "Yellow"]
        total_w = 4 * 90 + 3 * 20
        start_x = cx - total_w // 2

        for i, color in enumerate(colors):
            bx = start_x + i * 110
            by = cy - 20
            rect = pygame.Rect(bx, by, 90, 90)

            draw_glow(surf, rect.center, 50, Palette.UNO_COLORS[color], intensity=0.5)

            pygame.draw.circle(surf, Palette.UNO_COLORS[color], rect.center, 38)
            pygame.draw.circle(surf, (255, 255, 255, 120), rect.center, 38, 3)

            self.color_buttons.append((rect, color))
            draw_text(surf, color, (rect.centerx, rect.bottom + 10), 14,
                      Palette.TEXT_DIM, center=True)

        draw_text(surf, "Klik di luar atau tekan ESC untuk batal",
                  (cx, cy + panel_h // 2 - 24), 13, Palette.TEXT_MUTED, center=True)
