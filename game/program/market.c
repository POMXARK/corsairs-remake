// The markets of the archipelago: the data alone, the rules are in trade.c. The economy simulator
// (economy/, its tune.py) reads and writes the tables, so they keep to plain lines. A market is a
// port island, a good is one of four; a table of the markets lists the four goods of Gull Island,
// then of the Crag, then of Palm Key (index market * 4 + good).

// Written by economy/tune.py, 400 trials of Optuna: the goals are in its comment.

// the goods: sugar, rum, cloth, gunpowder
#define GOODS 4
#define GOOD_SUGAR 0
#define GOOD_RUM 1
#define GOOD_CLOTH 2
#define GOOD_POWDER 3
// the islands with a port (the model names of make_worldmap.py); the Reef has none
#define MARKETS 3
#define MARKET_GULL 0
#define MARKET_CRAG 1
#define MARKET_PALM 2

// the price of a unit, pesos, before the island and its stock change it
int goodBase[4] = {20, 40, 60, 80};

// the price on each island, percent of the base: what the island makes is cheap, what it lacks is
// dear. Gull Island is a town of weavers with a powder mill, the Crag a fort with a rum distillery,
// Palm Key a sugar plantation.
int marketPrice[12] = {
	160, 110, 65, 80,
	110, 65, 120, 135,
	75, 130, 125, 120};

// the stock at which the market sells at its price, units: more makes the good cheaper, less dearer
int marketNorm[12] = {
	70, 40, 120, 165,
	130, 125, 25, 60,
	170, 60, 25, 55};

// a day of the map brings the stock this percent of the way back to its norm
#define MARKET_RECOVERY 20
// the price follows the stock between these percents of the island's price
#define MARKET_PRICE_MIN 50
#define MARKET_PRICE_MAX 150
// the market buys at this percent of what it sells for
#define MARKET_BUYS 95

string Market_Island(int market)
{
	if (market == MARKET_CRAG) { return "crag"; }
	if (market == MARKET_PALM) { return "palm"; }
	return "gull";
}

// "Порт Утёса": the log on arrival
string Market_PortName(int market)
{
	if (market == MARKET_CRAG) { return "Порт на Утёсе"; }
	if (market == MARKET_PALM) { return "Порт на Пальмовом"; }
	return "Порт Острова Чаек";
}

string Good_Name(int good)
{
	if (good == GOOD_RUM) { return "ром"; }
	if (good == GOOD_CLOTH) { return "ткань"; }
	if (good == GOOD_POWDER) { return "порох"; }
	return "сахар";
}

// for the trace of the trade, which the simulator reads
string Good_Id(int good)
{
	if (good == GOOD_RUM) { return "rum"; }
	if (good == GOOD_CLOTH) { return "cloth"; }
	if (good == GOOD_POWDER) { return "powder"; }
	return "sugar";
}
