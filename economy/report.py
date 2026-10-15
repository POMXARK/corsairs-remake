"""Writes docs/ECONOMY.md and its plots: the hand tables against the tuned ones of market.c.

    python report.py
"""
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import market_c  # noqa: E402
import sim  # noqa: E402
import tune  # noqa: E402
from market_c import GOODS, MARKETS  # noqa: E402

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
PLOTS = DOCS / "economy"
HAND = market_c.read(HERE / "tests" / "fixtures" / "market_hand.c")
TUNED = market_c.read()
SEEDS = range(30)
NAMES = {"gull": "Остров Чаек", "crag": "Утёс", "palm": "Пальмовый",
         "sugar": "сахар", "rum": "ром", "cloth": "ткань", "powder": "порох"}


def gold_curves(data):
    curves = []
    for s in SEEDS:
        w = sim.play(data, "greedy", tune.VOYAGES, s)
        gold, line = sim.START_GOLD, [sim.START_GOLD]
        for v in w.voyages:
            gold += v.revenue - v.cost
            line.append(gold)
        curves.append(line)
    return curves


def plot_gold():
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, data, color in (("вручную", HAND, "tab:gray"), ("Optuna", TUNED, "tab:blue")):
        curves = gold_curves(data)
        cols = list(zip(*curves))
        med = [statistics.median(c) for c in cols]
        lo = [sorted(c)[len(c) // 4] for c in cols]
        hi = [sorted(c)[3 * len(c) // 4] for c in cols]
        ax.fill_between(range(len(med)), lo, hi, color=color, alpha=0.2)
        ax.plot(med, color=color, label=name + " (медиана, квартили)")
    ax.axhspan(1500, 4000, color="tab:green", alpha=0.08, label="цель к 40-му рейсу")
    ax.set_xlabel("рейс")
    ax.set_ylabel("песо")
    ax.set_title("Деньги торговлей (без наград за «Ворона»), от 100 песо новой игры")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "gold.png", dpi=90)
    plt.close(fig)


def plot_returns():
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, data, color in (("вручную", HAND, "tab:gray"), ("Optuna", TUNED, "tab:blue")):
        r = []
        for s in SEEDS:
            r += [100 * (v.revenue / v.cost - 1) for v in sim.play(data, "greedy", tune.VOYAGES, s).voyages
                  if v.cost and not v.lost]
        ax.hist(r, bins=30, range=(-20, 100), alpha=0.5, color=color, label=name)
    ax.axvspan(20, 40, color="tab:green", alpha=0.08, label="цель в среднем")
    ax.set_xlabel("доход рейса, % от цены груза")
    ax.set_ylabel("рейсов")
    ax.set_title("Доход за рейс (без рейсов, где груз забрали пираты)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "returns.png", dpi=90)
    plt.close(fig)


def plot_prices():
    """The sell prices of the tuned markets along one run of a rich player, percent of the price at the norm."""
    w = sim.play(TUNED, "greedy", 60, 3, gold=5000)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, market in zip(axes, MARKETS):
        m = MARKETS.index(market)
        for g, good in enumerate(GOODS):
            at_norm = sim.cdiv(TUNED.base[g] * TUNED.price[m * 4 + g], 100)
            pts = [(day, 100 * p / at_norm) for day, mk, gd, p in w.prices if mk == market and gd == good]
            ax.plot([d for d, _ in pts], [p for _, p in pts], label=NAMES[good])
        ax.axhline(100, color="black", lw=0.5)
        ax.set_title(NAMES[market])
        ax.set_xlabel("день")
    axes[0].set_ylabel("% цены при норме")
    axes[0].legend(fontsize=8)
    fig.suptitle("Цены рынков за 60 рейсов богатого игрока: скупка поднимает цену, дни возвращают к норме")
    fig.tight_layout()
    fig.savefig(PLOTS / "prices.png", dpi=90)
    plt.close(fig)


def rivals(data, n):
    """The player among n merchants who play as well as he does."""
    returns = []
    for s in range(10):
        traders = [(sim.Trader("player", gold=1000), sim.Greedy())]
        traders += [(sim.Trader("npc%d" % i, gold=1000, port=MARKETS[i % 3]), sim.Greedy()) for i in range(n)]
        w = sim.World(data, traders, seed=s).run(tune.VOYAGES)
        r = [v.revenue / v.cost - 1 for v in w.voyages if v.trader == "player" and v.cost and not v.lost]
        returns.append(statistics.mean(r) if r else 0.0)
    return statistics.mean(returns)


def table(data):
    rows = []
    for m, market in enumerate(MARKETS):
        cells = ["%d%% / %d (было %d%% / %d)" % (data.price[m * 4 + g], data.norm[m * 4 + g],
                                                 HAND.price[m * 4 + g], HAND.norm[m * 4 + g])
                 for g in range(len(GOODS))]
        rows.append("| %s | %s |" % (NAMES[market], " | ".join(cells)))
    return "\n".join(rows)


def main():
    PLOTS.mkdir(parents=True, exist_ok=True)
    plot_gold()
    plot_returns()
    plot_prices()
    hand, tuned = tune.evaluate(HAND), tune.evaluate(TUNED)

    def row(name, key, fmt, goal):
        return "| %s | %s | %s | %s |" % (name, fmt(hand[key]), fmt(tuned[key]), goal)

    pct = lambda v: "%+.0f%%" % (100 * v)  # noqa: E731
    metrics = "\n".join([
        row("доход за рейс, старт 100 песо", "return", pct, "20…40%"),
        row("доход за рейс, старт 5000 песо", "return_rich", pct, "10…40%"),
        row("песо торговлей за 40 рейсов (медиана)", "gold", lambda v: "%d" % v, "1500…4000"),
        row("доля прибыли лучшего маршрута", "top_route", lambda v: "%.2f" % v, "≤ 0.5"),
        row("товар на краю ценового коридора", "pinned", lambda v: "%.1f%%" % (100 * v), "≤ 5%"),
        row("доход случайного игрока", "return_blind", pct, "−30…0%"),
        row("рейсов, где пираты забрали груз", "lost", lambda v: "%.0f%%" % (100 * v), "—"),
        row("игр, где торговля ушла в минус", "ruin", lambda v: "%.0f%%" % (100 * v), "—"),
        row("песо вместе с наградами за «Ворона»", "bounty_gold", lambda v: "%d" % v, "—"),
        "| **счёт** (0 — все цели выполнены) | %.2f | %.2f | |" % (tune.score(hand), tune.score(tuned)),
    ])
    rival = "\n".join("| %d | %+.0f%% |" % (n, 100 * rivals(TUNED, n)) for n in (0, 2, 5, 10))

    text = f"""# Экономика архипелага

Торговля в игре (`game/program/trade.c`) — три порта, четыре товара, цены зависят от запаса на
складе. Таблицы рынков (`game/program/market.c`) подобраны симулятором `economy/`. Это отдельная
агентная модель на Python, движок ей не нужен.

Файл генерирует `economy/report.py`.

## Модель

- **Рынки** (`sim.Markets`) построчно повторяют `trade.c`, включая целочисленную арифметику
  скриптового языка. Цена — `база × % острова × (200 − запас/норма)`, коридор 50…150%. Покупка идёт
  поштучно, каждая единица дороже. Рынок берёт товар по `MARKET_BUYS`% своей цены. С каждым днём
  карты запас проходит `MARKET_RECOVERY`% пути к норме, но не больше десяти дней за раз.
- **Мир** (`sim.World`) моделирует карту:
  - переходы между портами по координатам `make_worldmap.py`: бриг идёт ~40 м за игровой час, ветер даёт 0.8…1.2;
  - штормы (+2…6 часов);
  - «Ворон»: с грузом догоняет вдвое чаще. Если бриг проигрывает бой, пираты забирают груз, а бриг уводят на Остров Чаек.
- **Агенты**:
  - `Greedy` — игрок, знающий цены. Грузит единицы с лучшей маржой на лучший порт и продаёт всё по прибытии.
  - `Wanderer` — игрок, который цены не сравнивает: случайный товар, случайный порт.

## Сверка с игрой

`replay.py` прогоняет строки `TRADE:` из лога движка через модель. Каждая сделка должна совпасть по
песо, остатку склада и кошельку. Тесты (`economy/tests`) проверяют на совпадение три лога:

| Лог | Таблицы | Что в нём |
|---|---|---|
| `autotrade.log` | ручные | рейс автотеста: ткань с Острова Чаек на Утёс, потеря груза |
| `fuzz.log` | ручные | 300 случайных сделок `fuzz_autotest.c` в трёх портах, дни идут |
| `fuzz_tuned.log` | Optuna | то же на подобранных таблицах |

## Цели баланса и результат

`tune.py` ищет таблицы с Optuna (TPE, 400 проб). Свободны процент цены и норма каждого товара на
каждом острове, скорость восстановления и наценка рынка. «Сюжет» островов сохраняется: что остров
производит, стоит там меньше 100% базы, чего ему не хватает — больше. Каждая проба — 12 сидов по 40 рейсов
для трёх игроков: бедного, богатого и случайного.

| Метрика | Вручную | Optuna | Цель |
|---|---|---|---|
{metrics}

Что показала модель:

- **Ручные таблицы.** Деньги торговлей приходили медленно. Игрок, вкладывающий в груз все песо, часто
  заканчивал в минусе: одна потеря груза съедала всё.
- **Подобранные таблицы.** Рынок платит ближе к своей цене (меньше спред), но у каждого товара своя
  норма запаса, поэтому большие партии быстрее упираются в рост цены. Доход стал ровнее, разорений
  меньше.
- **Награды за «Ворона».** Они дают игроку больше денег, чем торговля. Торговля в игре — способ
  начать и пережить потерю, а не главный источник дохода. Если её нужно сделать главной, есть два
  рычага: уменьшить `RAVEN_REWARD` в `world.c` или поднять наценки.
- **Шансы встречи и победы в бою.** В модели это оценки (`sim.Risk`), а не замер из игры. Их стоит
  уточнить логами игровых сессий.

![Кошелёк](economy/gold.png)

![Доход за рейс](economy/returns.png)

![Цены](economy/prices.png)

## Таблицы `market.c`

Процент базовой цены / норма запаса. Базовые цены: сахар 20, ром 40, ткань 60, порох 80.
Восстановление {TUNED.recovery}% в день (было {HAND.recovery}%), рынок берёт по {TUNED.buys}% (было {HAND.buys}%).

| Остров | сахар | ром | ткань | порох |
|---|---|---|---|---|
{table(TUNED)}

## Что если: торговцы-конкуренты

В игре на рынок влияет только игрок. Модель позволяет пустить рядом NPC-торговцев с той же
стратегией. Чем их больше, тем быстрее закрывается разница цен.

| NPC-торговцев | доход игрока за рейс |
|---|---|
{rival}

## Запуск

```bash
python3 -m venv --system-site-packages venv && venv/bin/pip install optuna==4.1.0 pytest==8.3.3
cd economy
../venv/bin/python -m pytest -q            # сверка с игрой и цели баланса
../venv/bin/python tune.py --write         # подобрать и записать market.c (~3 мин)
../venv/bin/python report.py               # этот отчёт
../venv/bin/python replay.py ~/.local/share/Akella/Sea\\ Dogs/Logs/compile.log   # сверить свою игру
```
"""
    (DOCS / "ECONOMY.md").write_text(text, encoding="utf-8")
    print(metrics)
    print(rival)


if __name__ == "__main__":
    main()
