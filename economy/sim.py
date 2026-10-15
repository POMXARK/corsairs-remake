"""An agent-based model of the archipelago's trade, without the engine.

`Markets` is trade.c line by line, in the same integer arithmetic: the tests hold the two together,
so whatever is tuned here behaves the same in the game. Around it `World` puts what the map does in
the game: voyages between the three ports that take hours of the map clock, storms that keep the brig
out longer, «Ворон» who comes for her (sooner when she is loaded, map.c) and takes the cargo when he
wins (sea.c), towing her home to Gull Island; when he loses, the governor pays a bounty there
(world.c), so a ruined trader has a way back as in the game. Traders are agents with a strategy: `Greedy` plays like
a player who knows the prices, `Wanderer` like one who does not.
"""
import math
import random
from dataclasses import dataclass, field

from market_c import GOODS, MARKETS, MarketData

CARGO_MAX = 50
START_GOLD = 100

# make_worldmap.py: the centres and radii of the islands, the waters reach WATERS m past the shore
ISLANDS = {"gull": (-430.0, 320.0, 150.0), "crag": (400.0, 430.0, 105.0), "palm": (290.0, -360.0, 175.0)}
WATERS = 105.0
# the brig makes about 20 m a second on the map (logs of the autotests), an hour of the map is two
# seconds (map.c, hourPerSec), and Enter is pressed some way into the waters
SPEED_PER_HOUR = 40.0
APPROACH = 60.0


def cdiv(a, b):
    """Integer division of the script language: toward zero, like C."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


class Markets:
    """The stocks of the three markets and the rules of trade.c over them."""

    def __init__(self, data: MarketData):
        self.data = data
        self.stock = list(data.norm)
        self.day = 0

    # Trade_Arrive: the stocks move toward the norm for every day since the last arrival, ten at most
    def arrive(self, today):
        d = self.data
        if self.day == 0:
            self.day = today
        days = min(today - self.day, 10)
        for _ in range(days):
            for i in range(len(self.stock)):
                diff = d.norm[i] - self.stock[i]
                move = cdiv(diff * d.recovery, 100)
                if move == 0 and diff > 0:
                    move = 1
                if move == 0 and diff < 0:
                    move = -1
                self.stock[i] += move
        self.day = today
        return days

    def percent(self, m, g):
        i = m * 4 + g
        p = 200 - cdiv(self.stock[i] * 100, self.data.norm[i])
        return max(self.data.price_min, min(self.data.price_max, p))

    # Trade_SellPrice: what the market sells a unit for
    def sell_price(self, m, g):
        d = self.data
        price = cdiv(cdiv(d.base[g] * d.price[m * 4 + g], 100) * self.percent(m, g), 100)
        return max(price, 1)

    # Trade_BuyPrice: what it pays for one
    def buy_price(self, m, g):
        return max(cdiv(self.sell_price(m, g) * self.data.buys, 100), 1)

    # Trade_Buy, any number of units: each one dearer than the last
    def buy(self, m, g, units, gold):
        i = m * 4 + g
        n = paid = 0
        while n < units and self.stock[i] > 0 and gold - paid >= self.sell_price(m, g):
            paid += self.sell_price(m, g)
            self.stock[i] -= 1
            n += 1
        return n, paid

    # Trade_Sell
    def sell(self, m, g, units):
        paid = 0
        for _ in range(units):
            paid += self.buy_price(m, g)
            self.stock[m * 4 + g] += 1
        return paid

    def peek_sell(self, m, g, units, extra=0):
        """What `units` more would fetch here if the stock were `extra` higher, the stock untouched."""
        i = m * 4 + g
        keep = self.stock[i]
        self.stock[i] += extra
        paid = self.sell(m, g, units)
        self.stock[i] = keep
        return paid


@dataclass
class Risk:
    """What the map does to a voyage; the chances are per voyage."""
    raven_empty: float = 0.15  # «Ворон» catches an empty brig
    raven_loaded: float = 0.30  # and a loaded one (he comes in 3 s instead of 6, map.c)
    win: float = 0.6  # the brig wins the battle
    storm: float = 0.3  # a storm keeps her out STORM_HOURS more
    storm_hours: tuple = (2, 6)
    tow_hours: int = 12  # towed home after a lost battle
    # world.c, Raven_Bounty: RAVEN_REWARD + level * RAVEN_LEVEL_REWARD, the level is the wins before
    # this one, RAVEN_MAX_LEVEL at most (the tougher «Ворон» of a higher level is not modelled)
    bounty: int = 500
    bounty_level: int = 250
    max_level: int = 4


def voyage_hours(a, b, rng):
    ax, az, ar = ISLANDS[a]
    bx, bz, br = ISLANDS[b]
    dist = math.hypot(ax - bx, az - bz) - (ar + WATERS) - (br + WATERS) + 2 * APPROACH
    # the wind is from 0.8 to 1.2 of the speed (wdm_objects.cpp)
    return max(dist, APPROACH) / (SPEED_PER_HOUR * rng.uniform(0.8, 1.2))


@dataclass
class Trader:
    name: str
    port: str = "gull"
    gold: int = START_GOLD
    hold: int = CARGO_MAX
    cargo: list = field(default_factory=lambda: [0] * len(GOODS))
    # what the cargo cost, to tell the return of a voyage
    cost: int = 0
    wins: int = 0
    unpaid: int = 0  # bounty to take on Gull Island; «Ворон» keeps away till then (map.c)
    bounties: int = 0  # all the bounty taken, to tell the gold of the trade alone

    def total(self):
        return sum(self.cargo)


class Greedy:
    """Sells everything on arrival, then loads the units with the best margin for the best port.

    It knows the stocks of every market (a player who has been there), so it is the upper bound
    of what trade gives: the tuning keeps its return in the band the design asks for.
    """
    min_margin = 1

    def plan(self, world, t):
        mk = world.markets
        here = MARKETS.index(t.port)
        best = (0, None, None)
        # a bounty waits on Gull Island: the map sends the brig there (map.c)
        dests = ["gull"] if t.unpaid and t.port != "gull" else MARKETS
        for dest in dests:
            if dest == t.port:
                continue
            there = MARKETS.index(dest)
            load = [0] * len(GOODS)
            bought = [0] * len(GOODS)
            gold = t.gold
            profit = 0
            keep = list(mk.stock)
            # unit by unit: the next unit of the good with the best margin now
            while sum(load) < t.hold:
                choice = None
                for g in range(len(GOODS)):
                    price = mk.sell_price(here, g)
                    if mk.stock[here * 4 + g] <= 0 or price > gold:
                        continue
                    gain = mk.peek_sell(there, g, 1, load[g]) - price
                    if gain >= self.min_margin and (choice is None or gain > choice[1]):
                        choice = (g, gain, price)
                if choice is None:
                    break
                g, gain, price = choice
                mk.stock[here * 4 + g] -= 1
                gold -= price
                load[g] += 1
                profit += gain
            mk.stock[:] = keep
            if profit > best[0]:
                best = (profit, dest, load)
        if best[1] is None:
            # nothing pays from here: sail empty to another port
            return world.rng.choice([p for p in dests if p != t.port]), [0] * len(GOODS)
        return best[1], best[2]


class Wanderer:
    """A player who does not compare prices: a random good, a random port, a lot or three."""

    def plan(self, world, t):
        dest = world.rng.choice([p for p in MARKETS if p != t.port])
        load = [0] * len(GOODS)
        load[world.rng.randrange(len(GOODS))] = 5 * world.rng.randint(1, 3)
        return dest, load


@dataclass
class Voyage:
    trader: str
    day: int
    start: str
    end: str
    cost: int
    revenue: int
    units: int
    lost: int  # units the pirates took
    pinned: int  # units bought or sold at the edge of the price band


class World:
    def __init__(self, data: MarketData, traders, risk=None, seed=0):
        self.markets = Markets(data)
        self.traders = traders  # [(Trader, strategy)]
        self.risk = risk or Risk()
        self.rng = random.Random(seed)
        self.hours = 9.0  # the map starts at 9 in the morning
        self.voyages = []
        self.prices = []  # (day, market, good, sell price) at every arrival

    def today(self):
        # Trade_Today counts from 0; the first arrival sets the day of the markets
        return 1 + int(self.hours // 24)

    def snapshot(self):
        for m in range(len(MARKETS)):
            for g in range(len(GOODS)):
                self.prices.append((self.today(), MARKETS[m], GOODS[g], self.markets.sell_price(m, g)))

    def run(self, voyages):
        """Every trader makes `voyages` voyages. They sail at once on the one clock of the map: the
        events (a trader casts off, a trader comes in) are taken in the order of their hours."""
        mk = self.markets
        mk.arrive(self.today())
        events = [(self.hours, i, "depart", None) for i in range(len(self.traders))]
        made = [0] * len(self.traders)
        while events:
            events.sort(key=lambda e: (e[0], e[1]))
            self.hours, i, kind, trip = events.pop(0)
            t, strategy = self.traders[i]
            if kind == "depart":
                if made[i] == voyages:
                    continue
                made[i] += 1
                events.append(self.depart(t, strategy, i))
            else:
                self.come_in(t, trip)
                events.append((self.hours, i, "depart", None))
        return self

    def depart(self, t, strategy, i):
        """Loads the hold and draws what the voyage meets; the event of the arrival."""
        mk = self.markets
        here = MARKETS.index(t.port)
        dest, load = strategy.plan(self, t)
        trip = {"start": t.port, "cost": 0, "units": 0, "pinned": 0, "lost": 0}
        for g, want in enumerate(load):
            room = t.hold - t.total()
            if want <= 0 or room <= 0:
                continue
            if mk.percent(here, g) == mk.data.price_max:
                trip["pinned"] += want
            n, paid = mk.buy(here, g, min(want, room), t.gold)
            t.gold -= paid
            t.cargo[g] += n
            trip["cost"] += paid
            trip["units"] += n
        hours = voyage_hours(t.port, dest, self.rng)
        r = self.risk
        if self.rng.random() < r.storm:
            hours += self.rng.uniform(*r.storm_hours)
        raven = r.raven_loaded if t.total() else r.raven_empty
        if t.unpaid:
            raven = 0.0
        if self.rng.random() < raven:
            if self.rng.random() >= r.win:
                trip["lost"] = t.total()
                t.cargo = [0] * len(GOODS)
                dest = "gull"
                hours += r.tow_hours
            else:
                t.unpaid += r.bounty + min(t.wins, r.max_level) * r.bounty_level
                t.wins += 1
        trip["end"] = dest
        return (self.hours + hours, i, "arrive", trip)

    def come_in(self, t, trip):
        mk = self.markets
        t.port = trip["end"]
        there = MARKETS.index(t.port)
        mk.arrive(self.today())
        revenue = 0
        for g in range(len(GOODS)):
            if t.cargo[g]:
                if mk.percent(there, g) == mk.data.price_min:
                    trip["pinned"] += t.cargo[g]
                revenue += mk.sell(there, g, t.cargo[g])
                t.cargo[g] = 0
        t.gold += revenue
        if t.unpaid and t.port == "gull":
            t.gold += t.unpaid
            t.bounties += t.unpaid
            t.unpaid = 0
        self.voyages.append(Voyage(t.name, self.today(), trip["start"], t.port, trip["cost"], revenue,
                                   trip["units"], trip["lost"], trip["pinned"]))
        self.snapshot()

def metrics(world):
    """The numbers the tuning and the report look at."""
    sold = [v for v in world.voyages if v.cost > 0 and not v.lost]
    units = sum(v.units for v in world.voyages)
    returns = [v.revenue / v.cost - 1 for v in sold]
    # the share of the profit the best route brings: near 1 when one route is all the game
    routes = {}
    for v in sold:
        routes[(v.start, v.end)] = routes.get((v.start, v.end), 0) + max(v.revenue - v.cost, 0)
    total = sum(routes.values())
    return {
        "voyages": len(world.voyages),
        "days": world.today(),
        "return": sum(returns) / len(returns) if returns else 0.0,
        "lost": sum(1 for v in world.voyages if v.lost) / max(len(world.voyages), 1),
        # the units bought at the top of the price band or sold at its bottom
        "pinned": sum(v.pinned for v in world.voyages) / max(units, 1),
        "top_route": max(routes.values()) / total if total else 1.0,
        "units": units,
        "gold": {t.name: t.gold for t, _ in world.traders},
        # the gold of the trade alone, without the bounties
        "trade_gold": {t.name: t.gold - t.bounties for t, _ in world.traders},
    }


def play(data, strategy="greedy", voyages=40, seed=0, risk=None, gold=START_GOLD):
    """One player alone, as in the game."""
    s = Greedy() if strategy == "greedy" else Wanderer()
    return World(data, [(Trader("player", gold=gold), s)], risk, seed).run(voyages)
