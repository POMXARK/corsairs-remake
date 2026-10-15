"""The tables in the game keep to the goals of tune.py."""
import market_c
import sim
import tune


def test_current_tables_meet_the_goals():
    r = tune.evaluate(market_c.read())
    assert tune.score(r) < 0.05, r


def test_story_of_the_islands():
    # what an island makes is cheap there and dear somewhere else: Gull cloth and powder, the Crag
    # rum, Palm Key sugar
    d = market_c.read()
    for m, g in ((0, 2), (0, 3), (1, 1), (2, 0)):
        assert d.price[m * 4 + g] < 100
        assert max(d.price[o * 4 + g] for o in range(3)) > 100


def test_random_play_is_not_a_fortune():
    d = market_c.read()
    blind = [sim.metrics(sim.play(d, "wanderer", 40, s, gold=1000))["return"] for s in range(12)]
    smart = [sim.metrics(sim.play(d, "greedy", 40, s, gold=1000))["return"] for s in range(12)]
    assert sum(blind) < sum(smart)


def test_runs_repeat_with_a_seed():
    d = market_c.read()
    a = sim.play(d, "greedy", 20, 7)
    b = sim.play(d, "greedy", 20, 7)
    assert a.voyages == b.voyages
