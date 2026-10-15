"""Tunes the tables of market.c with Optuna to the goals of the design, and writes them back.

    python tune.py              # 400 trials, prints the best tables and their scores
    python tune.py --write      # and puts them into game/program/market.c

The goals, each a band; the score is the sum of the squared misses, 0 when the tables keep to all:
- a player who knows the prices makes 20-40 % a voyage, starting with the 100 pesos of a new game;
- a rich one (5000 pesos, the whole hold every time) still makes 10-40 %: the slope of the prices
  eats the margin of big lots, but trade stays worth it;
- in 40 voyages the first one trades up to 1500-4000 pesos (median of the seeds, the bounties for
  «Ворон» left out): money comes, not floods;
- no route brings more than half of the profit, so all three ports matter;
- the price stays inside the band: under 5 % of the units at its edge, or the market is broken;
- a player who trades at random loses a little (-30..0 %), not everything at once.
The story of the islands stays: what an island makes is under 100 % of the base, what it lacks above.
"""
import argparse
import statistics

import optuna

import market_c
import sim

SEEDS = range(30)
VOYAGES = 40
CURRENT = market_c.read()


def band(value, low, high, scale=1.0):
    if value < low:
        return ((low - value) / scale) ** 2
    if value > high:
        return ((value - high) / scale) ** 2
    return 0.0


def evaluate(data, seeds=SEEDS):
    """The metrics of the goals, the means over the seeds."""
    poor = [sim.metrics(sim.play(data, "greedy", VOYAGES, s)) for s in seeds]
    rich = [sim.metrics(sim.play(data, "greedy", VOYAGES, s, gold=5000)) for s in seeds]
    blind = [sim.metrics(sim.play(data, "wanderer", VOYAGES, s, gold=1000)) for s in seeds]
    mean = statistics.mean
    return {
        "return": mean(m["return"] for m in poor),
        "return_rich": mean(m["return"] for m in rich),
        "gold": statistics.median(m["trade_gold"]["player"] for m in poor),
        # the runs that end with less than the start: one loss with every peso in the hold
        "ruin": mean(m["trade_gold"]["player"] < sim.START_GOLD for m in poor),
        "bounty_gold": statistics.median(m["gold"]["player"] for m in poor),
        "top_route": mean(m["top_route"] for m in poor + rich),
        "pinned": mean(m["pinned"] for m in poor + rich),
        "return_blind": mean(m["return"] for m in blind),
        "lost": mean(m["lost"] for m in poor),
    }


def score(r):
    return (band(r["return"], 0.20, 0.40, 0.05)
            + band(r["return_rich"], 0.10, 0.40, 0.05)
            + band(r["gold"], 1500, 4000, 500)
            + band(r["top_route"], 0.0, 0.5, 0.05)
            + band(r["pinned"], 0.0, 0.05, 0.02)
            + band(r["return_blind"], -0.30, 0.0, 0.05))


def suggest(trial):
    d = CURRENT.copy()
    for i, now in enumerate(CURRENT.price):
        # the island keeps what it makes cheap and what it lacks dear
        if now < 100:
            d.price[i] = trial.suggest_int("price%d" % i, 50, 95, step=5)
        else:
            d.price[i] = trial.suggest_int("price%d" % i, 105, 160, step=5)
        d.norm[i] = trial.suggest_int("norm%d" % i, 20, 200, step=5)
    d.recovery = trial.suggest_int("recovery", 5, 40, step=5)
    d.buys = trial.suggest_int("buys", 70, 95, step=5)
    return d


def objective(trial):
    d = suggest(trial)
    r = evaluate(d)
    for k, v in r.items():
        trial.set_user_attr(k, v)
    # a little pull toward the tables in the game: of two equal answers, the one nearer them
    drift = sum(abs(a - b) for a, b in zip(d.price + d.norm, CURRENT.price + CURRENT.norm)) / 10000
    return score(r) + drift


def tune(trials=400, seed=1):
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=seed))
    # start from the tables in the game now
    study.enqueue_trial({**{"price%d" % i: v for i, v in enumerate(CURRENT.price)},
                         **{"norm%d" % i: max(20, min(200, v)) for i, v in enumerate(CURRENT.norm)},
                         "recovery": CURRENT.recovery, "buys": CURRENT.buys})
    study.optimize(objective, n_trials=trials)
    return study


def best_data(study):
    return suggest(optuna.trial.FixedTrial(study.best_params))


def show(name, r):
    print("%-6s score %.3f  return %+.0f%%  rich %+.0f%%  blind %+.0f%%  gold %d  top route %.2f  pinned %.3f  lost %.2f"
          % (name, score(r), 100 * r["return"], 100 * r["return_rich"], 100 * r["return_blind"],
             r["gold"], r["top_route"], r["pinned"], r["lost"]))
    print("       ruined %.0f%%  gold with the bounties %d" % (100 * r["ruin"], r["bounty_gold"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=400)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    study = tune(args.trials)
    best = best_data(study)
    show("now", evaluate(CURRENT))
    show("tuned", evaluate(best))
    print("price", best.price, "\nnorm ", best.norm, "\nrecovery", best.recovery, "buys", best.buys)
    if args.write:
        market_c.write(best, note="tune.py, %d trials of Optuna: the goals are in its comment." % args.trials)
        print("written", market_c.MARKET_C)
