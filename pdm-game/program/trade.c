// The trade of the stores (the screen "trade", the action STORE of the dialogs). The original gives the data:
// the goods with a class (Goods.idf: 1 Chocolate, Sugar, Coffee, Wheat; 2 guns and shot; 4 Linen, Sailcloth; 8 Wine,
// Rum, Tobacco; 16 Mahogany, Ebony, Planks), a weight and a base price, and the specialisation of an island as a
// mask of these classes (RESOURCE\WORLDS\bits.txt). The prices themselves were made by TOWN.dll, no table of them
// is left, so the formula is ours (docs/pdm-formats.md, "Trade"):
//   the store of an island keeps PdmStore.<island>.n<goods> pieces, the norm of a goods is 10000 / (price + 8)
//   (40..800 pieces: the cheap goods are plenty, the dear ones few); an island sells its specialisation
//   at 85% of the base price and everything else at 115%, the stock lowers or raises that: 130% of it at an empty
//   store, 90% at a full one. The hero sells at 85% of what the store asks. Every piece changes the stock and
//   so the price of the next one. The store fills up a quarter of the way to its start each time it is opened.
// The islands of islands_x.idf have no mask (it is in the older Islands.idf for 11 of them), so each island
// takes two classes by its place in the list.

#define TRADE_ROWS 10

// the goods under the cursor (an index in PdmGoods), the first row of the window, the quantity
int tradeSel = 0;
int tradeTop = 0;
int tradeQty = 1;
// the line under the lists: what the last press did
string tradeHelp = "";
object PdmStore;

int Trade_Goods()
{
	aref all;
	makearef(all, PdmGoods);
	return GetAttributesNum(all);
}

string Trade_Id(int i)
{
	aref all, row;
	makearef(all, PdmGoods);
	row = GetAttributeN(all, i);
	return GetAttributeName(row);
}

int Trade_Price0(int i)
{
	string id = Trade_Id(i);
	return sti(PdmGoods.(id).price);
}

int Trade_Weight(int i)
{
	string id = Trade_Id(i);
	return sti(PdmGoods.(id).weight);
}

// 0..4 for the classes 1, 2, 4, 8, 16
int Trade_Bit(int i)
{
	string id = Trade_Id(i);
	int c = sti(PdmGoods.(id).class);
	if (c == 1) { return 0; }
	if (c == 2) { return 1; }
	if (c == 4) { return 2; }
	if (c == 8) { return 3; }
	return 4;
}

// the place of the island in PdmIslands
int Trade_IslandAt(string island)
{
	aref all, row;
	makearef(all, PdmIslands);
	int n = GetAttributesNum(all);
	for (int i = 0; i < n; i++)
	{
		row = GetAttributeN(all, i);
		if (GetAttributeName(row) == island) { return i; }
	}
	return 0;
}

bool Trade_Special(string island, int i)
{
	int at = Trade_IslandAt(island);
	int a = at % 5;
	int b = (at * 3 + 1) % 5;
	if (b == a) { b = (a + 1) % 5; }
	int bit = Trade_Bit(i);
	return bit == a || bit == b;
}

int Trade_Norm(int i)
{
	int n = 10000 / (Trade_Price0(i) + 8);
	if (n < 40) { n = 40; }
	if (n > 800) { n = 800; }
	return n;
}

// what the store holds after the first visit
int Trade_Start(string island, int i)
{
	int n = Trade_Norm(i);
	if (Trade_Special(island, i)) { return n; }
	return n / 6;
}

int Trade_Stock(string island, int i)
{
	string at = "n" + i;
	if (!CheckAttribute(PdmStore, island + "." + at)) { PdmStore.(island).(at) = Trade_Start(island, i); }
	return sti(PdmStore.(island).(at));
}

void Trade_SetStock(string island, int i, int n)
{
	string at = "n" + i;
	PdmStore.(island).(at) = n;
}

// the price of the store at a stock of the goods, for the hero to pay
int Trade_Price(string island, int i, int stock)
{
	int m = 115;
	if (Trade_Special(island, i)) { m = 85; }
	int r = stock * 100 / Trade_Norm(i);
	if (r > 100) { r = 100; }
	int f = 130 - 40 * r / 100;
	int p = (Trade_Price0(i) * m * f + 5000) / 10000;
	if (p < 1) { p = 1; }
	return p;
}

int Trade_SellPrice(string island, int i, int stock)
{
	int p = Trade_Price(island, i, stock) * 85 / 100;
	if (p < 1) { p = 1; }
	return p;
}

int Trade_Onboard(int i)
{
	string at = "n" + i;
	if (!CheckAttribute(PlayerShipCard, "cargo." + at)) { return 0; }
	return sti(PlayerShipCard.cargo.(at));
}

// the weight of the hold in tenths of a centner: the weight of Goods.idf is the weight of ten pieces (ours: the hero
// starts with 1720 of it in a hold of 400, so it cannot be the weight of one)
int Trade_Tenths()
{
	int sum = 0;
	int n = Trade_Goods();
	for (int i = 0; i < n; i++) { sum = sum + Trade_Onboard(i) * Trade_Weight(i); }
	return sum;
}

// the weight of the hold in centners
int Trade_Load()
{
	return Trade_Tenths() / 10;
}

// the stores go a quarter of the way back to their start when the screen opens
void Trade_Begin()
{
	tradeSel = 0;
	tradeTop = 0;
	tradeQty = 1;
	tradeHelp = "";
	if (townIsland == "") { return; }
	int n = Trade_Goods();
	for (int i = 0; i < n; i++)
	{
		int stock = Trade_Stock(townIsland, i);
		int start = Trade_Start(townIsland, i);
		Trade_SetStock(townIsland, i, stock + (start - stock) / 4);
	}
}

// the sum for qty pieces; buying raises the stock one piece at a time, selling lowers the price the same
int Trade_Sum(int i, int qty, bool buy)
{
	int stock = Trade_Stock(townIsland, i);
	int sum = 0;
	for (int k = 0; k < qty; k++)
	{
		if (buy)
		{
			if (stock - k <= 0) { break; }
			sum = sum + Trade_Price(townIsland, i, stock - k);
		}
		else
		{
			sum = sum + Trade_SellPrice(townIsland, i, stock + k);
		}
	}
	return sum;
}

string Trade_Value(string node)
{
	if (townIsland == "") { return ""; }
	if (node == "S_QUANT") { return "" + Trade_Onboard(tradeSel); }
	if (node == "S_COST") { return "" + Trade_Price(townIsland, tradeSel, Trade_Stock(townIsland, tradeSel)); }
	if (node == "S_QUANTITY") { return "" + tradeQty; }
	if (node == "S_SUM") { return "" + Trade_Sum(tradeSel, tradeQty, true); }
	return "";
}

// the lists of the window: the name (with > at the cursor), the hold and the price for it, the store and its price
void Trade_Lists()
{
	if (townIsland == "") { return; }
	int n = Trade_Goods();
	if (tradeSel < tradeTop) { tradeTop = tradeSel; }
	if (tradeSel >= tradeTop + TRADE_ROWS) { tradeTop = tradeSel - TRADE_ROWS + 1; }
	string names = "";
	string onboard = "";
	string sell = "";
	string store = "";
	string buy = "";
	for (int i = tradeTop; i < tradeTop + TRADE_ROWS && i < n; i++)
	{
		string id = Trade_Id(i);
		int stock = Trade_Stock(townIsland, i);
		string name = Screen_Name("goods", PdmGoods.(id).filename, "name");
		if (i == tradeSel) { name = "> " + name; }
		names = names + name + "\n";
		onboard = onboard + Trade_Onboard(i) + "\n";
		sell = sell + Trade_SellPrice(townIsland, i, stock) + "\n";
		store = store + stock + "\n";
		buy = buy + Trade_Price(townIsland, i, stock) + "\n";
	}
	Screen_Text(PdmScreens.trade.list.shiptovarname, names);
	Screen_Text(PdmScreens.trade.list.shiponboard, onboard);
	Screen_Text(PdmScreens.trade.list.shipprice, sell);
	Screen_Text(PdmScreens.trade.list.shopstore, store);
	Screen_Text(PdmScreens.trade.list.shopbuyprice, buy);
	Screen_Text(PdmScreens.trade.list.shopbalance, "");
	string chosen = Trade_Id(tradeSel);
	string pick = PdmGoods.(chosen).filename;
	Screen_Text("EDITDESC", Screen_Name("goods", pick, "about"));
	Screen_Text("EDITHELP", tradeHelp);
}

// the quantity goes 1, 2, 3, 4, 5, 10, 15 .. 50, 100, 150 ..
int Trade_Step(int q, int dir)
{
	// down from 5 or 50 goes to the step below
	int at = q;
	if (dir < 0) { at = q - 1; }
	int step = 1;
	if (at >= 5) { step = 5; }
	if (at >= 50) { step = 50; }
	q = q + dir * step;
	if (q < 1) { q = 1; }
	if (q > 2000) { q = 2000; }
	return q;
}

// the sale: pieces of the goods under the cursor, as many as the stock, the money and the hold allow
void Trade_Buy()
{
	int i = tradeSel;
	int got = 0;
	int paid = 0;
	string why = "";
	int capacity = sti(PlayerShipType.capacity);
	for (int k = 0; k < tradeQty; k++)
	{
		int stock = Trade_Stock(townIsland, i);
		if (stock <= 0) { why = "В магазине больше нет."; break; }
		int price = Trade_Price(townIsland, i, stock);
		if (sti(PlayerCard.money) < price) { why = "Не хватает денег."; break; }
		if (Trade_Tenths() + Trade_Weight(i) > capacity * 10) { why = "В трюме нет места."; break; }
		PlayerCard.money = sti(PlayerCard.money) - price;
		string at = "n" + i;
		PlayerShipCard.cargo.(at) = Trade_Onboard(i) + 1;
		Trade_SetStock(townIsland, i, stock - 1);
		got++;
		paid = paid + price;
	}
	tradeHelp = "Куплено " + got + " за " + paid + ". " + why;
	Trace("PDM trade: bought " + got + " of " + Trade_Id(i) + " for " + paid + " at " + townIsland + ", money " + PlayerCard.money + ", load " + Trade_Load() + "/" + PlayerShipType.capacity + " " + why);
}

void Trade_Sell()
{
	int i = tradeSel;
	int gone = 0;
	int earned = 0;
	string why = "";
	for (int k = 0; k < tradeQty; k++)
	{
		if (Trade_Onboard(i) <= 0) { why = "В трюме больше нет."; break; }
		int stock = Trade_Stock(townIsland, i);
		int price = Trade_SellPrice(townIsland, i, stock);
		PlayerCard.money = sti(PlayerCard.money) + price;
		string at = "n" + i;
		PlayerShipCard.cargo.(at) = Trade_Onboard(i) - 1;
		Trade_SetStock(townIsland, i, stock + 1);
		gone++;
		earned = earned + price;
	}
	tradeHelp = "Продано " + gone + " за " + earned + ". " + why;
	Trace("PDM trade: sold " + gone + " of " + Trade_Id(i) + " for " + earned + " at " + townIsland + ", money " + PlayerCard.money + ", load " + Trade_Load() + "/" + PlayerShipType.capacity + " " + why);
}

// a button of the screen; true if it was one of the trade
bool Trade_Click(string node)
{
	int n = Trade_Goods();
	if (townIsland == "") { return false; }
	if (node == "LB_TOVARUP" || node == "LB_TOVARUP1") { if (tradeSel > 0) { tradeSel--; } }
	else if (node == "LB_TOVARDOWN" || node == "LB_TOVARDOWN1") { if (tradeSel < n - 1) { tradeSel++; } }
	else if (node == "LB_LEFT") { tradeQty = Trade_Step(tradeQty, -1); }
	else if (node == "LB_RIGHT") { tradeQty = Trade_Step(tradeQty, 1); }
	else if (node == "LB_ALL")
	{
		// everything of the hold, or when it is empty as much as the store has
		tradeQty = Trade_Onboard(tradeSel);
		if (tradeQty < 1) { tradeQty = Trade_Stock(townIsland, tradeSel); }
		if (tradeQty < 1) { tradeQty = 1; }
	}
	else if (node == "LB_BUY") { Trade_Buy(); }
	else if (node == "LB_SELL") { Trade_Sell(); }
	else { return false; }
	Screen_Fill();
	return true;
}
