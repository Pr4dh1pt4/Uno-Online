"""
GameEngine — inti aturan UNO yang bersifat authoritative di server.

Bertanggung jawab atas: pembagian kartu, giliran, arah, validasi langkah,
efek kartu aksi/wild, deteksi pemenang, dan snapshot state untuk dikirim
ke client. Semua keputusan akhir ada di sini; client tidak dipercaya.
"""
from shared.constants import (
    INITIAL_HAND_SIZE, DIRECTION_CW, DIRECTION_CCW, COLORS, card_score_value,
)
from server.core.deck import Deck
from server.core.card import Card


class EnginePlayer:
    """Data pemain di dalam engine (terpisah dari koneksi jaringan)."""

    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        self.hand: list[Card] = []
        self.is_active = True       # masih bermain (belum menang/keluar)
        self.has_won = False        # sudah menghabiskan kartu
        self.finish_position = 0    # urutan finish (1 = pertama habis)
        self.called_uno = False     # sudah menekan UNO saat sisa 1 kartu

    def to_public(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "hand_count": len(self.hand),
            "remaining_value": self.remaining_value(),
            "is_active": self.is_active,
            "has_won": self.has_won,
            "finish_position": self.finish_position,
            "called_uno": self.called_uno,
        }

    def remaining_value(self) -> int:
        return sum(card_score_value(card) for card in self.hand)


class GameEngine:
    def __init__(self, players: list[tuple[int, str]], seed: int | None = None):
        """players: list of (user_id, username) sesuai urutan duduk."""
        self.deck = Deck(seed)
        self.players: list[EnginePlayer] = [EnginePlayer(uid, name) for uid, name in players]
        self.player_count = len(self.players)
        self.current_idx = 0
        self.direction = DIRECTION_CW
        self.active_color = ""
        # --- Draw stacking state ---
        self.pending_draw = 0          # akumulasi jumlah kartu yang harus diambil
        self.pending_draw_type = ""    # "Draw" untuk +2 stack, "Wild_Draw" untuk +4 stack
        # ---------------------------
        self.finished_count = 0
        self.game_over = False
        self.finish_order: list[int] = []  # user_id sesuai urutan finish
        # True jika pemain giliran ini sudah menarik 1 kartu (draw biasa);
        # mencegah menarik kartu lebih dari sekali dalam satu giliran.
        self.drawn_this_turn = False
        self._start()

    # -- setup --------------------------------------------------------------
    def _start(self) -> None:
        for p in self.players:
            p.hand = self.deck.draw_many(INITIAL_HAND_SIZE)
        # Kartu pembuka selalu kartu angka (0-9), tidak ada efek khusus
        first = self.deck.draw_first_discard()
        self.deck.play_to_discard(first)
        self.active_color = first.color

    # -- helper giliran -----------------------------------------------------
    def _next_active_index(self, start: int, step: int) -> int:
        """Cari indeks pemain aktif berikutnya dari `start` dengan arah step."""
        idx = start
        for _ in range(self.player_count):
            idx = (idx + step) % self.player_count
            if self.players[idx].is_active:
                return idx
        return start  # tidak ada pemain aktif lain

    def _advance(self) -> None:
        self.current_idx = self._next_active_index(self.current_idx, self.direction)
        # Giliran baru: reset status "sudah menarik kartu".
        self.drawn_this_turn = False

    @property
    def current_player(self) -> EnginePlayer:
        return self.players[self.current_idx]

    def get_player(self, user_id: int) -> EnginePlayer | None:
        for p in self.players:
            if p.user_id == user_id:
                return p
        return None

    def active_players(self) -> list[EnginePlayer]:
        return [p for p in self.players if p.is_active]

    # -- validasi & langkah -------------------------------------------------
    def is_valid_play(self, user_id: int, card: Card) -> tuple[bool, str]:
        """Cek apakah pemain boleh memainkan kartu tsb sekarang."""
        if self.game_over:
            return False, "game_over"
        player = self.current_player
        if player.user_id != user_id:
            return False, "not_your_turn"
        # kartu harus ada di tangan
        if card not in player.hand:
            return False, "card_not_in_hand"

        # --- Stacking: jika ada pending draw, boleh main kartu penambah apa saja (+2 atau +4) ---
        if self.pending_draw > 0:
            if card.is_any_draw:
                return True, ""
            return False, "must_stack_or_draw"

        top = self.deck.top_card
        if not card.matches(top, self.active_color):
            return False, "invalid_card"
        return True, ""

    def play_card(self, user_id: int, card: Card, chosen_color: str | None = None) -> dict:
        """
        Terapkan langkah valid. Pemanggil WAJIB memvalidasi dulu via is_valid_play.
        Return dict ringkasan efek untuk logging/broadcast.
        """
        player = self.current_player
        # buang dari tangan (hapus instance pertama yang cocok)
        for i, c in enumerate(player.hand):
            if c == card:
                player.hand.pop(i)
                break
        self.deck.play_to_discard(card)

        effect = {"type": card.ctype, "color_chosen": None}

        # tentukan warna aktif
        if card.is_wild:
            color = chosen_color if chosen_color in COLORS else COLORS[0]
            self.active_color = color
            effect["color_chosen"] = color
        else:
            self.active_color = card.color

        # reset flag uno bila kartu bertambah dari sisi lain ditangani saat draw
        if len(player.hand) != 1:
            player.called_uno = False

        # cek menang sebelum menerapkan efek lanjutan
        if len(player.hand) == 0:
            self._mark_winner(player)
            # efek kartu terakhir tetap diterapkan ke pemain berikutnya
            self._apply_card_effect(card, skip_advance_for_winner=True)
            return effect

        self._apply_card_effect(card)
        return effect

    def is_valid_multi_play(self, user_id: int, cards: list[Card]) -> tuple[bool, str]:
        """Validasi house rule: beberapa kartu angka boleh dimainkan jika angkanya sama."""
        if len(cards) <= 1:
            return self.is_valid_play(user_id, cards[0]) if cards else (False, "invalid_card")
        if self.pending_draw > 0:
            return False, "must_stack_or_draw"
        if any((not c.is_number) for c in cards):
            return False, "multi_play_number_only"
        number = cards[0].ctype
        if any(c.ctype != number for c in cards):
            return False, "multi_play_same_number_only"

        ok, reason = self.is_valid_play(user_id, cards[0])
        if not ok:
            return False, reason

        player = self.current_player
        remaining = list(player.hand)
        for card in cards:
            for i, hand_card in enumerate(remaining):
                if hand_card == card:
                    remaining.pop(i)
                    break
            else:
                return False, "card_not_in_hand"
        return True, ""

    def play_cards(self, user_id: int, cards: list[Card]) -> dict:
        """
        Terapkan multi-play kartu angka valid sebagai satu aksi.
        Giliran hanya maju sekali setelah seluruh kartu dibuang.
        """
        if len(cards) == 1:
            return self.play_card(user_id, cards[0])

        player = self.current_player
        for card in cards:
            for i, hand_card in enumerate(player.hand):
                if hand_card == card:
                    player.hand.pop(i)
                    break
            self.deck.play_to_discard(card)
            self.active_color = card.color

        if len(player.hand) != 1:
            player.called_uno = False

        if len(player.hand) == 0:
            self._mark_winner(player)

        if not self.game_over:
            self._advance()

        return {
            "type": "multi_number",
            "count": len(cards),
            "number": cards[0].ctype,
            "cards": [c.to_dict() for c in cards],
        }

    def _apply_card_effect(self, card: Card, skip_advance_for_winner: bool = False) -> None:
        ctype = card.ctype

        if ctype == "Reverse":
            if self.player_count > 2:
                # >2 pemain: balik arah, lanjut ke pemain berikutnya sesuai arah baru
                self.direction *= -1
                self._advance()
            else:
                # 2 pemain: Reverse = pemain yang sama jalan lagi
                # TIDAK advance — giliran tetap di pemain ini, tapi giliran
                # baru dimulai sehingga jatah draw kembali tersedia.
                self.drawn_this_turn = False

        elif ctype == "Skip":
            self._advance()  # lewati pemain berikut
            self._advance()

        elif ctype == "Draw":
            # +2: akumulasi ke pending_draw, jangan langsung terapkan
            self.pending_draw += 2
            self.pending_draw_type = "Draw"
            # giliran pindah ke pemain berikut (dia harus stack atau ambil)
            self._advance()

        elif ctype == "Wild_Draw":
            # +4: akumulasi ke pending_draw
            self.pending_draw += 4
            self.pending_draw_type = "Wild_Draw"
            # giliran pindah ke pemain berikut
            self._advance()

        else:
            # number atau wild biasa: lanjut ke pemain berikut
            self._advance()

    def draw_card(self, user_id: int) -> Card | list[Card] | None:
        """
        Pemain menarik kartu. Jika ada pending_draw (akumulasi stacking),
        pemain mengambil semua kartu akumulasi. Jika tidak, ambil 1 kartu biasa.
        Return: single Card (draw biasa), list[Card] (pending draw), atau None.
        """
        if self.game_over:
            return None
        player = self.current_player
        if player.user_id != user_id:
            return None

        if self.pending_draw > 0:
            # Ambil semua kartu akumulasi
            count = self.pending_draw
            cards = self.deck.draw_many(count)
            player.hand.extend(cards)
            player.called_uno = False
            self.pending_draw = 0
            self.pending_draw_type = ""
            # Pemain yang kena draw di-skip (giliran pindah)
            self._advance()
            return cards

        # Draw biasa: hanya boleh 1 kartu per giliran.
        if self.drawn_this_turn:
            return None
        card = self.deck.draw()
        player.hand.append(card)
        player.called_uno = False
        self.drawn_this_turn = True
        return card

    def pass_turn(self, user_id: int) -> bool:
        """Lewati giliran setelah menarik kartu (tidak memainkan kartu hasil draw)."""
        if self.current_player.user_id != user_id:
            return False
        self._advance()
        return True

    def _give_cards(self, player: EnginePlayer, n: int) -> None:
        player.hand.extend(self.deck.draw_many(n))
        player.called_uno = False

    # -- UNO call -----------------------------------------------------------
    def call_uno(self, user_id: int, mode: str = "self") -> tuple[bool, str, int, list[Card]]:
        """
        Pemain menekan tombol UNO. Mekanik balapan (race): pemain bertanggung
        jawab menekan UNO sendiri lebih dulu sebelum lawan melapor.

        mode == "self"  → tombol "UNO!" milik sendiri:
          - "self_call": berhasil menandai UNO. Hanya sah saat sisa 1 kartu, ATAU
            sisa 2 kartu di giliran sendiri (pre-call: tekan dulu baru mainkan
            kartu kedua-dari-terakhir).
          - "false_call": menekan UNO saat belum waktunya (masih banyak kartu) →
            pemanggil kena penalti 2 kartu.
          - "noop": sudah terlanjur call / pemain tidak aktif → tidak ada efek.

        mode == "catch" → tombol "Lapor UNO!" terhadap lawan:
          - "catch": ada lawan sisa 1 kartu yang belum call → lawan kena +2 kartu
          - "false_call": tidak ada lawan yang bisa ditangkap (mis. pemain sisa 1
            sudah lebih dulu menekan UNO) → pelapor sendiri kena penalti 2 kartu

        Return: (success, action_type, target_user_id, penalty_cards)
        """
        player = self.get_player(user_id)
        if not player:
            return False, "", 0, []

        if mode == "self":
            if player.called_uno or not player.is_active:
                return False, "noop", user_id, []
            n = len(player.hand)
            # Sah: sisa 1 kartu (wajib), atau sisa 2 kartu saat giliran sendiri.
            if n == 1 or (n == 2 and self.current_player.user_id == user_id):
                player.called_uno = True
                return True, "self_call", user_id, []
            # Menekan UNO terlalu dini (masih banyak kartu) → penalti 2 kartu.
            before = len(player.hand)
            self._give_cards(player, 2)
            return False, "false_call", user_id, player.hand[before:]

        # mode == "catch": cari lawan sisa 1 kartu yang belum call UNO
        for p in self.players:
            if (p.user_id != user_id and p.is_active
                    and len(p.hand) == 1 and not p.called_uno):
                before = len(p.hand)
                self._give_cards(p, 2)
                return True, "catch", p.user_id, p.hand[before:]

        # Tidak ada yang bisa ditangkap → laporan keliru, pelapor kena penalti.
        before = len(player.hand)
        self._give_cards(player, 2)
        return False, "false_call", user_id, player.hand[before:]

    # -- pemenang & akhir ---------------------------------------------------
    def _mark_winner(self, player: EnginePlayer) -> None:
        player.has_won = True
        player.is_active = False
        self.finished_count += 1
        player.finish_position = self.finished_count
        self.finish_order.append(player.user_id)
        self._check_game_over()

    def remove_player(self, user_id: int) -> None:
        """Pemain keluar/disconnect permanen: ditandai tidak aktif & dianggap kalah."""
        player = self.get_player(user_id)
        if not player or not player.is_active:
            return
        was_current = self.current_player.user_id == user_id
        player.is_active = False
        if not player.has_won:
            # belum menang -> dapat posisi terakhir di antara yang tersisa nanti
            pass
        self._check_game_over()
        if not self.game_over and was_current:
            self._advance()

    def _check_game_over(self) -> None:
        """Game selesai jika tersisa <= 1 pemain aktif."""
        active = self.active_players()
        if len(active) <= 1 and not self.game_over:
            self.game_over = True
            # Berikan posisi finish akhir ke semua pemain yang belum menyelesaikannya
            # Urutkan: pemain yang masih aktif didahulukan, lalu diurutkan berdasarkan sisa kartu tersedikit
            remaining = [p for p in self.players if not p.finish_position]
            remaining.sort(key=lambda p: (not p.is_active, len(p.hand)))
            for p in remaining:
                p.is_active = False
                self.finished_count += 1
                p.finish_position = self.finished_count
                self.finish_order.append(p.user_id)

    # -- snapshot state -----------------------------------------------------
    def get_state(self) -> dict:
        top = self.deck.top_card
        return {
            "top_card": top.to_dict() if top else None,
            "active_color": self.active_color,
            "current_turn": self.current_player.user_id if not self.game_over else None,
            "direction": self.direction,
            "draw_pile_count": len(self.deck.draw_pile),
            "game_over": self.game_over,
            "players": [p.to_public() for p in self.players],
            "scoreboard": self._scoreboard(),
            "pending_draw": self.pending_draw,
            "pending_draw_type": self.pending_draw_type,
            "drawn_this_turn": self.drawn_this_turn,
        }

    def _scoreboard(self) -> list[dict]:
        ordered = sorted(
            self.players,
            key=lambda p: (p.finish_position if p.finish_position else 99, len(p.hand)),
        )
        return [{"user_id": p.user_id, "username": p.username,
                 "finish_position": p.finish_position, "hand_count": len(p.hand),
                 "remaining_value": p.remaining_value()}
                for p in ordered]

    def get_hand(self, user_id: int) -> list[dict]:
        player = self.get_player(user_id)
        return [c.to_dict() for c in player.hand] if player else []

    def final_ranking(self) -> list[int]:
        """Urutan user_id dari pemenang (posisi 1) sampai terakhir."""
        ranked = sorted(
            [p for p in self.players if p.finish_position],
            key=lambda p: p.finish_position,
        )
        return [p.user_id for p in ranked]

    def final_ranking_details(self) -> list[dict]:
        """Detail ranking akhir, termasuk value kartu tersisa untuk scoring."""
        ranked = sorted(
            [p for p in self.players if p.finish_position],
            key=lambda p: p.finish_position,
        )
        return [
            {
                "user_id": p.user_id,
                "username": p.username,
                "finish_position": p.finish_position,
                "hand_count": len(p.hand),
                "remaining_value": p.remaining_value(),
            }
            for p in ranked
        ]
