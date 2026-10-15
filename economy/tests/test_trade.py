"""The model against trade.c: logs of the game replayed, and the prices worked out by hand."""
from pathlib import Path

import pytest

import market_c
import replay
import sim

FIX = Path(__file__).resolve().parent / "fixtures"
HAND = market_c.read(FIX / "market_hand.c")


# the logs of the engine, each with the tables it ran on: autotrade.log is the scripted voyage of the
# trade autotest, the fuzz logs are 300 random deals of fuzz_autotest.c with the days moving on
@pytest.mark.parametrize("log, tables", [
    ("autotrade.log", "market_hand.c"),
    ("fuzz.log", "market_hand.c"),
    ("fuzz_tuned.log", "market_tuned.c"),
])
def test_replay_game_log(log, tables):
    with open(FIX / log, encoding="utf-8") as f:
        checked, wrong = replay.replay(f, market_c.read(FIX / tables))
    assert checked > 0
    assert wrong == []


def test_prices_of_gull_cloth():
    mk = sim.Markets(HAND)
    # 60 pesos, 70 % on Gull Island, stock at the norm
    assert (mk.sell_price(0, 2), mk.buy_price(0, 2)) == (42, 35)
    assert (mk.sell_price(1, 2), mk.buy_price(1, 2)) == (78, 66)
    # each unit takes the stock down and the price up: 42 42 42 43 43
    assert mk.buy(0, 2, 5, 500) == (5, 212)


def test_buy_stops_at_gold_and_stock():
    mk = sim.Markets(HAND)
    assert mk.buy(0, 2, 5, 100) == (2, 84)
    mk.stock[0] = 1
    assert mk.buy(0, 0, 5, 1000)[0] == 1


def test_recovery_is_c_integer_math():
    mk = sim.Markets(HAND)
    mk.arrive(100)
    mk.stock[2] = 115
    mk.stock[6] = 45
    mk.arrive(105)
    # 115 -> 116 -> 117 -> 118 -> 119 -> 120: under 5 away a unit a day, not a fifth of nothing
    assert mk.stock[2] == 120
    # above the norm the move is toward zero as well: -5 * 20 / 100 = -1
    assert mk.stock[6] == 40
    # never more than ten days at once
    mk.stock[2] = 0
    assert mk.arrive(200) == 10


def test_cdiv_truncates_toward_zero():
    assert sim.cdiv(-7, 2) == -3
    assert sim.cdiv(7, 2) == 3


@pytest.mark.parametrize("tables", ["market_hand.c", "current"])
def test_no_profit_in_one_port(tables):
    data = market_c.read() if tables == "current" else HAND
    for m in range(3):
        for g in range(4):
            mk = sim.Markets(data)
            n, paid = mk.buy(m, g, 20, 10 ** 6)
            assert mk.sell(m, g, n) < paid


def test_market_c_round_trip(tmp_path):
    path = tmp_path / "market.c"
    path.write_text((FIX / "market_hand.c").read_text(encoding="utf-8"), encoding="utf-8")
    data = market_c.read(path)
    data.price[0] = 155
    data.recovery = 30
    market_c.write(data, path, note="a test.")
    market_c.write(data, path, note="a test.")
    assert market_c.read(path) == data
    text = path.read_text(encoding="utf-8")
    assert text.count("// Written by economy/") == 1
    assert "Market_PortName" in text
