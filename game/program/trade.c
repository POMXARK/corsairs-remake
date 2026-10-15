// Trade between the islands: every port (port.c) has a market of four goods with the prices of
// market.c, the brig carries them in her hold. Buying takes from the stock of the market and makes
// the good dearer there, selling adds to it and makes it cheaper; the days of the map bring every
// stock back to its norm. Tom trades on Gull Island, a merchant in the other ports. Pirates on the
// map come sooner for a loaded brig (map.c) and take the cargo when they win (sea.c).

#include "market.c"

// a unit is a barrel or a bale; the hold of the brig takes CARGO_MAX of them besides the charges
#define CARGO_MAX 50
#define CARGO_LOT 5

int cargo[4];
int marketStock[12];
// the day of the map the stocks were last brought up to, 0 before the first port
int marketDay = 0;
// the port the brig is in or was last in (a model name of make_worldmap.py)
string portIsland = "gull";
// the good the dialog shows, and the cargo pirates took in the last lost battle
int tradeGood = 0;
int cargoLost = 0;

void Trade_Reset()
{
	int i, g;
	for (i = 0; i < 12; i++) { marketStock[i] = marketNorm[i]; }
	for (g = 0; g < GOODS; g++) { cargo[g] = 0; }
	marketDay = 0;
	portIsland = "gull";
	tradeGood = 0;
	cargoLost = 0;
}

// the market of an island, -1 when it has no port
int Trade_Market(string island)
{
	int m;
	for (m = 0; m < MARKETS; m++)
	{
		if (Market_Island(m) == island) { return m; }
	}
	return -1;
}

int Trade_Here() { return Trade_Market(portIsland); }

int Cargo_Total()
{
	int g;
	int total = 0;
	for (g = 0; g < GOODS; g++) { total = total + cargo[g]; }
	return total;
}

// the day of the map clock, counted in months of 31 days: only the difference matters
int Trade_Today()
{
	return sti(worldMap.date.year) * 372 + sti(worldMap.date.month) * 31 + sti(worldMap.date.day);
}

// the brig comes into a port: the stocks of every market have moved toward the norm since
void Trade_Arrive()
{
	int d, i, diff, move;
	int today = Trade_Today();
	if (marketDay == 0) { marketDay = today; }
	int days = today - marketDay;
	if (days > 10) { days = 10; }
	for (d = 0; d < days; d++)
	{
		for (i = 0; i < 12; i++)
		{
			// at least a unit a day, or the last few never come back
			diff = marketNorm[i] - marketStock[i];
			move = diff * MARKET_RECOVERY / 100;
			if (move == 0 && diff > 0) { move = 1; }
			if (move == 0 && diff < 0) { move = -1; }
			marketStock[i] = marketStock[i] + move;
		}
	}
	marketDay = today;
	Trace("TRADE: arrive " + portIsland + " day " + today + " after " + days);
}

// what the market here sells a unit for: its price for the island, higher as the stock runs low
int Trade_SellPrice(int good)
{
	int i = Trade_Here() * GOODS + good;
	int percent = 200 - marketStock[i] * 100 / marketNorm[i];
	if (percent < MARKET_PRICE_MIN) { percent = MARKET_PRICE_MIN; }
	if (percent > MARKET_PRICE_MAX) { percent = MARKET_PRICE_MAX; }
	int price = goodBase[good] * marketPrice[i] / 100 * percent / 100;
	if (price < 1) { price = 1; }
	return price;
}

int Trade_BuyPrice(int good)
{
	int price = Trade_SellPrice(good) * MARKET_BUYS / 100;
	if (price < 1) { price = 1; }
	return price;
}

// "сахар 10, ром 5", or "пусто"
string Cargo_List()
{
	int g;
	string list = "";
	for (g = 0; g < GOODS; g++)
	{
		if (cargo[g] > 0)
		{
			if (list != "") { list = list + ", "; }
			list = list + Good_Name(g) + " " + cargo[g];
		}
	}
	if (list == "") { return "пусто"; }
	return list;
}

// a lost battle: the pirates take the whole cargo
void Cargo_Lose()
{
	int g;
	cargoLost = Cargo_Total();
	for (g = 0; g < GOODS; g++) { cargo[g] = 0; }
	if (cargoLost > 0) { Trace("TRADE: cargo lost " + cargoLost); }
}

// ---------------------------------------------------------------- the dialog (port.c)

// the nodes of the trade; 1 when the node was one of them
int Trade_Node(string node)
{
	int g;
	if (node == "trade") { Trade_Show(""); return 1; }
	for (g = 0; g < GOODS; g++)
	{
		if (node == "g" + g || node == "g" + g + "2") { tradeGood = g; Trade_Good(""); return 1; }
	}
	// a twin of an answer chosen twice in a row (port.c, Answer)
	if (node == "buy" || node == "buy2") { Trade_Buy(); return 1; }
	if (node == "sell" || node == "sell2") { Trade_Sell(); return 1; }
	return 0;
}

void Trade_Show(string reply)
{
	int g;
	string text = reply;
	if (text != "") { text = text + " "; }
	text = text + "Беру и продаю, капитан. В трюме: " + Cargo_List() + " (" + Cargo_Total() + " из " + CARGO_MAX + "), в кошельке " + gold + " песо.";
	Say(text);
	for (g = 0; g < GOODS; g++)
	{
		Answer("l" + g, Good_Name(g) + ": продаю по " + Trade_SellPrice(g) + ", беру по " + Trade_BuyPrice(g), "g" + g);
	}
	if (Trade_Here() == MARKET_GULL) { Answer("l9", "Хватит.", "again"); }
	else { Answer("l9", "Хватит.", "hello"); }
}

void Trade_Good(string reply)
{
	int g = tradeGood;
	int i = Trade_Here() * GOODS + g;
	string text = reply;
	if (text != "") { text = text + " "; }
	text = text + "Товар — " + Good_Name(g) + ": на складе " + marketStock[i] + ", в трюме " + cargo[g] + ". Продаю по " + Trade_SellPrice(g) + " песо, беру по " + Trade_BuyPrice(g) + ". В кошельке " + gold + ".";
	Say(text);
	Answer("l1", "Купить " + CARGO_LOT + " (около " + Trade_SellPrice(g) * CARGO_LOT + " песо)", "buy");
	if (cargo[g] > 0) { Answer("l2", "Продать " + Trade_SellLot() + " (около " + Trade_BuyPrice(g) * Trade_SellLot() + " песо)", "sell"); }
	Answer("l3", "Другой товар", "trade");
}

int Trade_SellLot()
{
	if (cargo[tradeGood] < CARGO_LOT) { return cargo[tradeGood]; }
	return CARGO_LOT;
}

// The price goes up after every unit, so a lot is bought unit by unit: as many as the gold, the
// hold and the stock allow, a part of a lot is better than none.
void Trade_Buy()
{
	int g = tradeGood;
	int i = Trade_Here() * GOODS + g;
	if (Cargo_Total() >= CARGO_MAX) { Trade_Good("Трюм полон."); return; }
	if (marketStock[i] <= 0) { Trade_Good("Склад пуст, капитан."); return; }
	if (gold < Trade_SellPrice(g)) { Trade_Good("Не хватает песо."); return; }
	int paid = 0;
	int units = 0;
	int price = 0;
	while (units < CARGO_LOT && Cargo_Total() < CARGO_MAX && marketStock[i] > 0 && gold >= Trade_SellPrice(g))
	{
		price = Trade_SellPrice(g);
		paid = paid + price;
		gold = gold - price;
		marketStock[i] = marketStock[i] - 1;
		cargo[g] = cargo[g] + 1;
		units++;
	}
	Trace("TRADE: " + portIsland + " buy " + Good_Id(g) + " " + units + " for " + paid + " stock " + marketStock[i] + " gold " + gold);
	Trade_Good("Погрузили " + units + ", " + paid + " песо.");
}

void Trade_Sell()
{
	int n;
	int g = tradeGood;
	int i = Trade_Here() * GOODS + g;
	int lot = Trade_SellLot();
	if (lot <= 0) { Trade_Good("В трюме этого нет."); return; }
	int paid = 0;
	for (n = 0; n < lot; n++)
	{
		paid = paid + Trade_BuyPrice(g);
		marketStock[i] = marketStock[i] + 1;
	}
	gold = gold + paid;
	cargo[g] = cargo[g] - lot;
	Trace("TRADE: " + portIsland + " sell " + Good_Id(g) + " " + lot + " for " + paid + " stock " + marketStock[i] + " gold " + gold);
	Trade_Good("Выгрузили, вот " + paid + " песо.");
}
