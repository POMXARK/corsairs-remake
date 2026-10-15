"""Replays the trade of a game log through the model: the `TRADE:` lines trade.c traces.

    python replay.py ~/.local/share/Akella/Sea\\ Dogs/Logs/compile.log

Every purchase and sale is made again on `Markets` from the same stocks; the pesos, the stock left
and the purse must come out as in the game, or the model and trade.c have drifted apart.
"""
import re
import sys

import market_c
from market_c import GOODS, MARKETS
from sim import Markets

ARRIVE = re.compile(r"TRADE: arrive (\w+) day (\d+) after (\d+)")
DEAL = re.compile(r"TRADE: (\w+) (buy|sell) (\w+) (\d+) for (\d+) stock (\d+) gold (\d+)")


def replay(lines, data=None):
    """Returns the deals checked and a list of the ones that differ."""
    mk = Markets(data or market_c.read())
    checked, wrong = 0, []
    for line in lines:
        a = ARRIVE.search(line)
        if a:
            days = mk.arrive(int(a.group(2)))
            if days != int(a.group(3)):
                wrong.append((line.strip(), "days %d" % days))
            continue
        d = DEAL.search(line)
        if not d:
            continue
        island, kind, good, units, paid, stock, gold = d.groups()
        m, g = MARKETS.index(island), GOODS.index(good)
        units, paid, stock, gold = int(units), int(paid), int(stock), int(gold)
        if kind == "buy":
            n, got = mk.buy(m, g, units, gold + paid)
        else:
            n, got = units, mk.sell(m, g, units)
        checked += 1
        if (n, got, mk.stock[m * 4 + g]) != (units, paid, stock):
            wrong.append((line.strip(), "model: %d for %d stock %d" % (n, got, mk.stock[m * 4 + g])))
    return checked, wrong


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        checked, wrong = replay(f)
    for line, why in wrong:
        print("DIFF", line, "--", why)
    print("%d deals, %d differ" % (checked, len(wrong)))
    sys.exit(1 if wrong else 0)
