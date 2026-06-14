"""Unit test GameEngine & aturan UNO (tidak butuh DB/jaringan)."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.core.game_engine import GameEngine
from server.core.deck import build_standard_deck
from server.core.card import Card
from shared.constants import (
    calc_dynamic_point_delta, calc_point_delta, card_score_value, classify_rank,
)


def test_deck_has_108_cards():
    assert len(build_standard_deck()) == 108


def test_initial_deal():
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    assert len(eng.get_player(1).hand) == 7
    assert len(eng.get_player(2).hand) == 7
    assert eng.deck.top_card is not None


def test_card_matching():
    top = Card("Red", "5")
    assert Card("Red", "8").matches(top, "Red")       # warna sama
    assert Card("Blue", "5").matches(top, "Red")      # angka sama
    assert Card("Wild", "Wild").matches(top, "Red")   # wild selalu
    assert not Card("Blue", "8").matches(top, "Red")  # beda warna & angka


def test_not_your_turn_rejected():
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    cur = eng.current_player.user_id
    other = 2 if cur == 1 else 1
    ok, reason = eng.is_valid_play(other, eng.get_player(other).hand[0])
    assert not ok and reason == "not_your_turn"


def test_self_uno_penalty_when_many_cards():
    # Menekan UNO sendiri saat masih banyak kartu = pelanggaran -> penalti +2.
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    before = len(eng.get_player(1).hand)  # 7 kartu
    ok, action, target_uid, penalty = eng.call_uno(1, "self")
    assert not ok
    assert action == "false_call"
    assert len(eng.get_player(1).hand) == before + 2
    assert len(penalty) == 2


def test_self_uno_precall_two_cards_on_turn():
    # Sisa 2 kartu DI GILIRAN sendiri -> pre-call sah, tanpa penalti.
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    eng.current_idx = 0  # giliran pemain 1
    p1 = eng.get_player(1)
    p1.hand = p1.hand[:2]
    before = len(p1.hand)
    ok, action, _, _ = eng.call_uno(1, "self")
    assert ok and action == "self_call" and p1.called_uno
    assert len(p1.hand) == before  # tidak bertambah


def test_self_uno_two_cards_not_turn_penalty():
    # Sisa 2 kartu tapi BUKAN giliran sendiri -> belum waktunya, kena penalti.
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    eng.current_idx = 1  # giliran pemain 2
    p1 = eng.get_player(1)
    p1.hand = p1.hand[:2]
    before = len(p1.hand)
    ok, action, _, penalty = eng.call_uno(1, "self")
    assert not ok and action == "false_call"
    assert len(p1.hand) == before + 2


def test_false_catch_penalizes_reporter():
    # Lapor UNO tanpa ada lawan sisa 1 kartu -> pelapor kena penalti 2 kartu.
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    before = len(eng.get_player(1).hand)
    ok, action, target_uid, penalty = eng.call_uno(1, "catch")
    assert not ok
    assert action == "false_call"
    assert len(eng.get_player(1).hand) == before + 2
    assert len(penalty) == 2


def test_uno_race_self_call_protects():
    # Pemain sisa 1 kartu menekan UNO duluan -> lawan yang melapor kena penalti.
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    p1 = eng.get_player(1)
    p1.hand = p1.hand[:1]  # paksa sisa 1 kartu
    ok, action, _, _ = eng.call_uno(1, "self")
    assert ok and action == "self_call" and p1.called_uno
    before2 = len(eng.get_player(2).hand)
    ok2, action2, target2, penalty2 = eng.call_uno(2, "catch")
    assert action2 == "false_call"  # p1 sudah call -> tak bisa ditangkap
    assert len(eng.get_player(2).hand) == before2 + 2


def test_uno_race_catch_when_silent():
    # Pemain sisa 1 kartu TIDAK menekan UNO -> lawan melapor duluan, dia kena +2.
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    p1 = eng.get_player(1)
    p1.hand = p1.hand[:1]
    before1 = len(p1.hand)
    ok, action, target, penalty = eng.call_uno(2, "catch")
    assert ok and action == "catch" and target == 1
    assert len(p1.hand) == before1 + 2


def test_point_table():
    assert calc_point_delta(2, 1) == 15
    assert calc_point_delta(2, 2) == -10
    assert calc_point_delta(3, 2) == 10
    assert calc_point_delta(4, 1) == 25
    assert calc_point_delta(4, 4) == -10


def test_dynamic_point_uses_remaining_card_value():
    assert card_score_value(Card("Red", "7")) == 7
    assert card_score_value(Card("Blue", "Skip")) == 15
    assert card_score_value(Card("Wild", "Wild_Draw")) == 20
    assert calc_dynamic_point_delta(3, 1, 0, 47) == 22  # base 20 + 2
    assert calc_dynamic_point_delta(3, 3, 42, 0) == -12  # base -10 - 2


def test_multi_play_same_number_advances_once():
    eng = GameEngine([(1, "a"), (2, "b"), (3, "c")], seed=1)
    eng.deck.discard_pile = [Card("Red", "7")]
    eng.active_color = "Red"
    eng.current_idx = 0
    eng.players[0].hand = [Card("Red", "5"), Card("Blue", "5"), Card("Yellow", "5"), Card("Green", "9")]

    cards = [Card("Red", "5"), Card("Blue", "5"), Card("Yellow", "5")]
    ok, reason = eng.is_valid_multi_play(1, cards)
    assert ok, reason

    eng.play_cards(1, cards)
    assert [c.ctype for c in eng.players[0].hand] == ["9"]
    assert eng.deck.top_card == Card("Yellow", "5")
    assert eng.active_color == "Yellow"
    assert eng.current_player.user_id == 2


def test_multi_play_rejects_mixed_numbers_or_actions():
    eng = GameEngine([(1, "a"), (2, "b")], seed=1)
    eng.deck.discard_pile = [Card("Red", "7")]
    eng.active_color = "Red"
    eng.players[0].hand = [Card("Red", "5"), Card("Blue", "6"), Card("Red", "Skip")]

    ok, reason = eng.is_valid_multi_play(1, [Card("Red", "5"), Card("Blue", "6")])
    assert not ok and reason == "multi_play_same_number_only"

    ok, reason = eng.is_valid_multi_play(1, [Card("Red", "5"), Card("Red", "Skip")])
    assert not ok and reason == "multi_play_number_only"


def test_rank_classification():
    assert classify_rank(0) == "Bronze"
    assert classify_rank(999) == "Bronze"
    assert classify_rank(1000) == "Silver"
    assert classify_rank(1500) == "Gold"
    assert classify_rank(2000) == "Platinum"


def test_full_game_terminates_and_ranks():
    """Auto-play deterministik harus selalu menghasilkan game over & ranking lengkap."""
    eng = GameEngine([(1, "a"), (2, "b"), (3, "c")], seed=5)
    rng = random.Random(5)
    for _ in range(5000):
        if eng.game_over:
            break
        cur = eng.current_player.user_id
        st = eng.get_state()
        top = Card.from_dict(st["top_card"])

        # Gunakan is_valid_play untuk menentukan kartu yang bisa dimainkan
        # (ini menangani pending draw stacking secara otomatis)
        playable = [c for c in eng.get_player(cur).hand
                    if eng.is_valid_play(cur, c)[0]]

        if playable:
            eng.play_card(cur, rng.choice(playable),
                          chosen_color=rng.choice(["Red", "Green", "Blue", "Yellow"]))
        else:
            d = eng.draw_card(cur)
            # Jika draw_card mengembalikan list (stacked draw), giliran sudah di-skip
            if isinstance(d, list):
                continue
            st2 = eng.get_state()
            top2 = Card.from_dict(st2["top_card"])
            if d and isinstance(d, Card) and d.matches(top2, st2["active_color"]):
                eng.play_card(cur, d, chosen_color="Red")
            else:
                eng.pass_turn(cur)
    assert eng.game_over
    ranking = eng.final_ranking()
    assert len(ranking) == 3
    assert len(set(ranking)) == 3  # semua pemain punya posisi unik


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
