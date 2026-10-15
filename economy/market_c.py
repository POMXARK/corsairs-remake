"""Reads and writes game/program/market.c: the tables the game's trade (trade.c) runs on.

The file keeps to plain `#define NAME number` and `int name[n] = {...};` lines, so a few regular
expressions read it, and the writer fills a template with the same layout and comments.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

MARKET_C = Path(__file__).resolve().parent.parent / "game" / "program" / "market.c"

GOODS = ["sugar", "rum", "cloth", "powder"]
MARKETS = ["gull", "crag", "palm"]


@dataclass
class MarketData:
    base: list = field(default_factory=list)  # pesos per unit, by good
    price: list = field(default_factory=list)  # percent of base, index market * 4 + good
    norm: list = field(default_factory=list)  # stock at which the market sells at its price
    recovery: int = 20  # percent of the way back to the norm a day
    price_min: int = 50
    price_max: int = 150
    buys: int = 85  # the market buys at this percent of what it sells for

    def copy(self):
        return MarketData(list(self.base), list(self.price), list(self.norm), self.recovery,
                          self.price_min, self.price_max, self.buys)


def _array(text, name):
    m = re.search(r"int\s+" + name + r"\s*\[\s*\d+\s*\]\s*=\s*\{([^}]*)\}", text)
    if not m:
        raise ValueError("no array " + name)
    return [int(v) for v in m.group(1).replace("\n", " ").split(",")]


def _define(text, name):
    m = re.search(r"#define\s+" + name + r"\s+(-?\d+)", text)
    if not m:
        raise ValueError("no define " + name)
    return int(m.group(1))


def read(path=MARKET_C):
    text = Path(path).read_text(encoding="utf-8")
    return MarketData(_array(text, "goodBase"), _array(text, "marketPrice"),
                      _array(text, "marketNorm"), _define(text, "MARKET_RECOVERY"),
                      _define(text, "MARKET_PRICE_MIN"), _define(text, "MARKET_PRICE_MAX"),
                      _define(text, "MARKET_BUYS"))


def _rows(values):
    rows = [", ".join(str(v) for v in values[m * 4:m * 4 + 4]) for m in range(len(MARKETS))]
    return "{\n\t" + ",\n\t".join(rows) + "}"


def write(data, path=MARKET_C, note=""):
    """Puts the tables of `data` into market.c, leaving the rest of the file as it is."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"int goodBase\[4\] = \{[^}]*\}",
                  "int goodBase[4] = {" + ", ".join(str(v) for v in data.base) + "}", text)
    text = re.sub(r"int marketPrice\[12\] = \{[^}]*\}", "int marketPrice[12] = " + _rows(data.price), text)
    text = re.sub(r"int marketNorm\[12\] = \{[^}]*\}", "int marketNorm[12] = " + _rows(data.norm), text)
    for name, value in (("MARKET_RECOVERY", data.recovery), ("MARKET_PRICE_MIN", data.price_min),
                        ("MARKET_PRICE_MAX", data.price_max), ("MARKET_BUYS", data.buys)):
        text = re.sub(r"#define " + name + r" -?\d+", "#define " + name + " " + str(value), text)
    if note:
        text = re.sub(r"// Written by [^\n]*\n\n?", "", text)
        text = text.replace("\n// the goods:", "\n// Written by economy/" + note + "\n\n// the goods:", 1)
    path.write_text(text, encoding="utf-8")
