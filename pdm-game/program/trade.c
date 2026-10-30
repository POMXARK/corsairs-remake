// The trade of the stores (the screen "trade", the action STORE of the dialogs), by TOWN.dll of the original
// (docs/original-vs-remake.md, "Магазин"; the code of the store opening is FUN_1000b2e0). The goods of the list are those
// of Goods.idf but the guns (type 0); what an island exports, imports or forbids is IMAGES\GOODS\ISLANDS\<island>.gst
// (program/data/pdm_trade.c, tools/pdm_trade.py). Every opening of the store makes, for each goods:
//   a norm of the stock: export 300..548, import 80..128, the others 100..148 (a forbidden goods 0), times 30 for the
//     shot (type 1: it goes by twenty, the weight of Goods.idf is of twenty) or times 5 for the planks and the sailcloth
//     (type 3), divided by the weight of the goods;
//   the price A the store asks: export price / (1.3 + 0..16/35), import price * (2 + 0..34/35), the others
//     price * (1 + (0..27 - 14)/35); the price B the store pays: A / (1.4 + 0..9 * 0.04);
//   the stock: what was there plus the norm (twice at the first visit); over the norm it falls to the norm less a random
//     third of it.
// The hero's skill shifts them: with t = the Trade skill * 5 (up to 95) the store asks A - (price - A) * t%, pays
// B + (A' - B) * t%, never below 1 and never above what it asks. The prices stand while the window is open, only the stock
// moves with each piece.
// t = the Trade skill * 5 (up to 95) + the reputation part (Trade_Rep: reputation of the hero moved 5 away from 0, tenths cut,
// times 10, within -30..30); when the two prices meet, the store pays one less with a chance of a half (rand).
// Ours: the original counts the days since the last visit by the date of the game (the store fills up on the 1st and the 16th
// of each month), the remake has no calendar: the first visit is a month, each next one fifteen days. The price modifier of
// the island is not known: 100%.

#define TRADE_LINES 7

// the row under the cursor (an index in the list of the goods), the first row of the window, the quantity
int tradeSel = 0;
int tradeTop = 0;
int tradeQty = 0;
int tradeStage = 0;
// the line under the lists: what the last press did ("" shows the money, as the original)
string tradeHelp = "";
object PdmStore;
object PlayerFleet;

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

int Trade_Type(int i)
{
	string id = Trade_Id(i);
	return sti(PdmGoods.(id).type);
}

// the list of the window: the goods but the guns
int Trade_Rows()
{
	int n = 0;
	int all = Trade_Goods();
	for (int i = 0; i < all; i++)
	{
		if (Trade_Type(i) != 0) { n++; }
	}
	return n;
}

// the goods (an index in PdmGoods) of the row
int Trade_Nth(int row)
{
	int all = Trade_Goods();
	int at = 0;
	for (int i = 0; i < all; i++)
	{
		if (Trade_Type(i) == 0) { continue; }
		if (at == row) { return i; }
		at++;
	}
	return 0;
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

// "export", "import", "contraband" or "" of the goods at the island
string Trade_Kind(string island, int i)
{
	string id = Trade_Id(i);
	if (!CheckAttribute(PdmTrade, island + "." + id)) { return ""; }
	return PdmTrade.(island).(id);
}

int Trade_Step(int i)
{
	if (Trade_Type(i) == 1) { return 20; }
	return 1;
}

// The fleet of the hero: the flagship (PlayerShipCard) and up to seven companions PlayerFleet.s1..s7 (type_key, name,
// cargo.n<i>) — TOWN.dll lists the hero and the non-empty slots +0x130..+0x148 of him. PlayerFleet.n is the count with the
// flagship. The arrows PrevShip/NextShip of the store move tradeShip along the list.
int tradeShip = 0;

int Trade_Ships()
{
	if (!CheckAttribute(PlayerFleet, "n")) { return 1; }
	return sti(PlayerFleet.n);
}

// the companion slot of the ship tradeShip
string Trade_Slot()
{
	return "s" + tradeShip;
}

string Trade_ShipName()
{
	if (tradeShip == 0) { return PlayerShipCard.name; }
	string sk = Trade_Slot();
	return PlayerFleet.(sk).name;
}

// the key of the type of the ship in PdmShipTypes
string Trade_ShipType()
{
	if (tradeShip == 0) { return PlayerShipType.id; }
	string sk = Trade_Slot();
	return PlayerFleet.(sk).type_key;
}

int Trade_ShipCapacity()
{
	string tk = Trade_ShipType();
	return sti(PdmShipTypes.(tk).capacity);
}

// a companion for the fleet (tests; the ways to get one: the shipyard, a prize, a quest)
void Trade_AddShip(string typeKey, string name)
{
	int k = Trade_Ships();
	if (k > 7) { return; }
	string sk = "s" + k;
	PlayerFleet.(sk).type_key = typeKey;
	PlayerFleet.(sk).name = name;
	PlayerFleet.n = k + 1;
}

int Trade_Onboard(int i)
{
	string at = "n" + i;
	if (tradeShip == 0)
	{
		if (!CheckAttribute(PlayerShipCard, "cargo." + at)) { return 0; }
		return sti(PlayerShipCard.cargo.(at));
	}
	string sk = Trade_Slot();
	if (!CheckAttribute(PlayerFleet, sk + ".cargo." + at)) { return 0; }
	return sti(PlayerFleet.(sk).cargo.(at));
}

void Trade_SetOnboard(int i, int n)
{
	string at = "n" + i;
	if (tradeShip == 0) { PlayerShipCard.cargo.(at) = n; return; }
	string sk = Trade_Slot();
	PlayerFleet.(sk).cargo.(at) = n;
}

// the weight of the hold in twentieths of a centner: the shot weighs by twenty pieces, the rest by the piece
int Trade_Twentieths()
{
	int sum = 0;
	int n = Trade_Goods();
	for (int i = 0; i < n; i++)
	{
		int w = Trade_Onboard(i) * Trade_Weight(i);
		if (Trade_Type(i) != 1) { w = w * 20; }
		sum = sum + w;
	}
	return sum;
}

// the weight of the hold in centners
int Trade_Load()
{
	return Trade_Twentieths() / 20;
}

// what the store of the island has: PdmStore.<island>.n<i> the stock, .a<i> and .b<i> the prices before the skill
int Trade_Stock(string island, int i)
{
	string at = "n" + i;
	if (!CheckAttribute(PdmStore, island + "." + at)) { return 0; }
	return sti(PdmStore.(island).(at));
}

void Trade_SetStock(string island, int i, int n)
{
	string at = "n" + i;
	PdmStore.(island).(at) = n;
}

// the reputation part of t: R (reputation of the hero, +0x3d8) moved 5 away from 0, tenths cut, times 10, within -30..30
int Trade_Rep()
{
	int r = 0;
	if (CheckAttribute(PlayerCard, "reputation")) { r = sti(PlayerCard.reputation); }
	if (r < 0) { r = r - 5; } else { r = r + 5; }
	r = (r / 10) * 10;
	if (r > 30) { r = 30; }
	if (r < -30) { r = -30; }
	return r;
}

// t of the original: the Trade skill of the hero (with the officers in the original: ours has no officers) * 5, up to 95,
// plus the reputation part
int Trade_Skill()
{
	int k = 0;
	if (CheckAttribute(PlayerCard, "skills.commerce")) { k = sti(PlayerCard.skills.commerce) * 5; }
	if (k > 95) { k = 95; }
	return k + Trade_Rep();
}

// the store of the island is filled when it is opened
void Trade_Fill(string island)
{
	int refills = 1;
	if (!CheckAttribute(PdmStore, island + ".visits")) { refills = 2; PdmStore.(island).visits = 0; }
	PdmStore.(island).visits = sti(PdmStore.(island).visits) + 1;
	int n = Trade_Goods();
	for (int i = 0; i < n; i++)
	{
		if (Trade_Type(i) == 0) { continue; }
		string kind = Trade_Kind(island, i);
		float p = Trade_Price0(i);
		float f;
		int norm;
		int a;
		if (kind == "export")
		{
			norm = 300 + rand(249);
			f = rand(16);
			a = MakeInt(p / (1.3 + f / 35.0));
		}
		else
		{
			if (kind == "import")
			{
				norm = 80 + rand(49);
				f = rand(34);
				a = MakeInt(p * (2.0 + f / 35.0));
			}
			else
			{
				norm = 100 + rand(49);
				if (kind == "contraband") { norm = 0; }
				f = rand(27) - 14;
				a = MakeInt(p * (1.0 + f / 35.0));
			}
		}
		int m = 1;
		if (Trade_Type(i) == 1) { m = 30; }
		if (Trade_Type(i) == 3) { m = 5; }
		norm = norm * m / Trade_Weight(i);
		f = rand(9);
		int b = MakeInt(a / (1.4 + f * 0.04));
		int stock = Trade_Stock(island, i) + norm * refills;
		if (stock > norm) { stock = norm - rand(norm / 3); }
		Trade_SetStock(island, i, stock);
		string at = "a" + i;
		PdmStore.(island).(at) = a;
		at = "b" + i;
		PdmStore.(island).(at) = b;
		// the prices of the window: the skill is applied once, when the store is opened; when the two meet the original
		// takes a random piece off the price it pays
		float t = Trade_Skill();
		int ask = MakeInt(a - (p - a) * t * 0.01);
		if (ask < 1) { ask = 1; }
		int pay = MakeInt(b + (ask - b) * t * 0.01);
		if (pay < 1) { pay = 1; }
		if (pay > ask) { pay = ask; }
		if (pay == ask) { pay = pay - rand(1); }
		if (pay < 1) { pay = 1; }
		at = "ask" + i;
		PdmStore.(island).(at) = ask;
		at = "pay" + i;
		PdmStore.(island).(at) = pay;
	}
}

// the price the store asks for the piece (A' of the skill, fixed when the store was opened)
int Trade_Price(string island, int i)
{
	string at = "ask" + i;
	if (!CheckAttribute(PdmStore, island + "." + at)) { return 1; }
	return sti(PdmStore.(island).(at));
}

// the price the store pays (B' of the skill)
int Trade_SellPrice(string island, int i)
{
	string at = "pay" + i;
	if (!CheckAttribute(PdmStore, island + "." + at)) { return 1; }
	return sti(PdmStore.(island).(at));
}

// opening of the screen
void Trade_Begin()
{
	tradeSel = 0;
	tradeShip = 0;
	tradeTop = 0;
	tradeQty = 0;
	tradeHelp = "";
	if (townIsland == "") { return; }
	Trade_Fill(townIsland);
}

// the most the hero can buy of the goods now: what the store has, what fits into the hold, what the money pays; by the step
int Trade_MaxBuy(int i)
{
	int stock = Trade_Stock(townIsland, i);
	int step = Trade_Step(i);
	int w = Trade_Weight(i);
	int free = Trade_ShipCapacity() * 20 - Trade_Twentieths();
	int price = Trade_Price(townIsland, i);
	int money = sti(PlayerCard.money);
	int q = stock;
	if (step > 1) { q = (q / step) * step; }
	if (Trade_Type(i) == 1) { if (q * w > free) { q = (free / w / step) * step; } }
	else { if (q * w * 20 > free) { q = free / (w * 20); } }
	if (q * price > money) { q = money / price; if (step > 1) { q = (q / step) * step; } }
	if (q < 0) { q = 0; }
	return q;
}

int Trade_Sum(int i, bool buy)
{
	if (buy) { return tradeQty * Trade_Price(townIsland, i); }
	return tradeQty * Trade_SellPrice(townIsland, i);
}

string Trade_Value(string node)
{
	if (townIsland == "") { return ""; }
	int i = Trade_Nth(tradeSel);
	if (node == "S_QUANT" || node == "S_QUANTITY") { return "" + tradeQty; }
	if (node == "S_COST") { return "" + Trade_Price(townIsland, i); }
	if (node == "S_SUM") { return "" + Trade_Sum(i, true); }
	return "";
}

// the weight, the damage of the shot: t_1Goods, t_2Goods, t_3Goods of the original with the params of Goods.idf
string Trade_Chars(int i)
{
	string id = Trade_Id(i);
	int kind = Trade_Type(i);
	string text = PdmScreens.trade.t.(kind);
	int k = 0;
	while (findSubStr(text, "%", 0) >= 0)
	{
		text = Screen_Put(text, Screen_Nth(PdmGoods.(id).params, k));
		k++;
	}
	return text;
}

// the lists of the window: the name (with > at the cursor), the hold and the price for it, the store and its price, the mark of the island
void Trade_Lists()
{
	if (townIsland == "") { return; }
	int n = Trade_Rows();
	if (tradeSel < 0) { tradeSel = 0; }
	if (tradeSel >= n) { tradeSel = n - 1; }
	if (tradeSel < tradeTop) { tradeTop = tradeSel; }
	if (tradeSel >= tradeTop + TRADE_LINES) { tradeTop = tradeSel - TRADE_LINES + 1; }
	string names = "";
	string onboard = "";
	string sell = "";
	string store = "";
	string buy = "";
	string marks = "";
	for (int r = tradeTop; r < tradeTop + TRADE_LINES && r < n; r++)
	{
		int i = Trade_Nth(r);
		string id = Trade_Id(i);
		string name = Screen_Name("goods", PdmGoods.(id).filename, "name");
		if (r == tradeSel) { name = "> " + name; }
		names = names + name + "\n";
		onboard = onboard + Trade_Onboard(i) + "\n";
		sell = sell + Trade_SellPrice(townIsland, i) + "\n";
		store = store + Trade_Stock(townIsland, i) + "\n";
		buy = buy + Trade_Price(townIsland, i) + "\n";
		string kind = Trade_Kind(townIsland, i);
		if (kind == "export") { marks = marks + PdmScreens.trade.t.exporting; }
		if (kind == "import") { marks = marks + PdmScreens.trade.t.importing; }
		marks = marks + "\n";
	}
	Screen_Text(PdmScreens.trade.list.shiptovarname, names);
	Screen_Text(PdmScreens.trade.list.shiponboard, onboard);
	Screen_Text(PdmScreens.trade.list.shipprice, sell);
	Screen_Text(PdmScreens.trade.list.shopstore, store);
	Screen_Text(PdmScreens.trade.list.shopbuyprice, buy);
	Screen_Text(PdmScreens.trade.list.shopbalance, marks);
	int chosen = Trade_Nth(tradeSel);
	string cid = Trade_Id(chosen);
	string pick = PdmGoods.(cid).filename;
	Screen_Text("EDITDESC", Screen_Name("goods", pick, "about"));
	Screen_Text("EDITCHARS", Trade_Chars(chosen));
	// the money stands where the help is: the original shows it there until a press tells something else
	string line = tradeHelp;
	if (line == "") { line = Screen_Put(PdmScreens.trade.t.money, PlayerCard.money); }
	Screen_Text("EDITHELP", line);
}

// the sale: the piece by piece, as many as the stock, the hold and the money allow
void Trade_Buy()
{
	int i = Trade_Nth(tradeSel);
	int q = tradeQty;
	int max = Trade_MaxBuy(i);
	string why = "";
	if (q > max) { q = max; why = "Не всё: нет запаса, места или денег."; }
	int price = Trade_Price(townIsland, i);
	string at = "n" + i;
	PlayerCard.money = sti(PlayerCard.money) - q * price;
	Trade_SetOnboard(i, Trade_Onboard(i) + q);
	Trade_SetStock(townIsland, i, Trade_Stock(townIsland, i) - q);
	tradeHelp = why;
	tradeQty = 0;
	Trace("PDM trade: bought " + q + " of " + Trade_Id(i) + " for " + (q * price) + " at " + townIsland + ", money " + PlayerCard.money + ", load " + Trade_Load() + "/" + Trade_ShipCapacity() + " " + why);
}

void Trade_Sell()
{
	int i = Trade_Nth(tradeSel);
	int q = tradeQty;
	string why = "";
	if (q > Trade_Onboard(i)) { q = Trade_Onboard(i); why = "В трюме меньше."; }
	int price = Trade_SellPrice(townIsland, i);
	string at = "n" + i;
	PlayerCard.money = sti(PlayerCard.money) + q * price;
	Trade_SetOnboard(i, Trade_Onboard(i) - q);
	Trade_SetStock(townIsland, i, Trade_Stock(townIsland, i) + q);
	tradeHelp = why;
	tradeQty = 0;
	Trace("PDM trade: sold " + q + " of " + Trade_Id(i) + " for " + (q * price) + " at " + townIsland + ", money " + PlayerCard.money + ", load " + Trade_Load() + "/" + Trade_ShipCapacity() + " " + why);
}

// a button of the screen; true if it was one of the trade
bool Trade_Click(string node)
{
	int n = Trade_Rows();
	if (townIsland == "") { return false; }
	int i = Trade_Nth(tradeSel);
	if (node == "LB_TOVARUP" || node == "LB_TOVARUP1") { if (tradeSel > 0) { tradeSel--; tradeQty = 0; tradeHelp = ""; } }
	else if (node == "LB_TOVARDOWN" || node == "LB_TOVARDOWN1") { if (tradeSel < n - 1) { tradeSel++; tradeQty = 0; tradeHelp = ""; } }
	else if (node == "LB_LEFT") { tradeQty = tradeQty - Trade_Step(i); if (tradeQty < 0) { tradeQty = 0; } }
	else if (node == "LB_RIGHT")
	{
		// as many as can be bought; over the hold the sale of what is there
		tradeQty = tradeQty + Trade_Step(i);
		int most = Trade_MaxBuy(i);
		if (Trade_Onboard(i) > most) { most = Trade_Onboard(i); }
		if (tradeQty > most) { tradeQty = most; }
	}
	else if (node == "LB_ALL")
	{
		// everything of the hold, or when it is empty as much as can be bought
		tradeQty = Trade_Onboard(i);
		if (tradeQty < 1) { tradeQty = Trade_MaxBuy(i); }
	}
	else if (node == "LB_PREVSHIP") { if (tradeShip > 0) { tradeShip--; tradeQty = 0; tradeHelp = ""; } }
	else if (node == "LB_NEXTSHIP") { if (tradeShip < Trade_Ships() - 1) { tradeShip++; tradeQty = 0; tradeHelp = ""; } }
	else if (node == "LB_BUY") { Trade_Buy(); }
	else if (node == "LB_SELL") { Trade_Sell(); }
	else { return false; }
	Screen_Fill();
	return true;
}

// TOWN_AUTO=21: the hero talks to the store owner and picks the trade; the lists must be filled, then a purchase and a sale
// change the money, the hold and the stock the way the prices say, then the game quits
int tradeMoney0 = 0;
int tradeStock0 = 0;
int tradeOnboard0 = 0;
int tradeMoney1 = 0;

void Trade_Check(string name)
{
	if (TownAuto != STORE_ID || name != "trade") { return; }
	int i = Trade_Nth(0);
	string empty = "";
	if (Trade_Rows() != 16) { empty = empty + "rows "; }
	if (Trade_Stock(townIsland, i) < 1) { empty = empty + "stock "; }
	if (Trade_Price(townIsland, i) < 1) { empty = empty + "price "; }
	if (empty == "") { Trace("PDM store: values ok, the island " + townIsland + ", " + Trade_Rows() + " goods"); }
	else { Trace("PDM store: FAIL, " + empty); }
	// a companion for the test (ours): the same type as the flagship
	string tk = PlayerShipCard.type_key;
	Trade_AddShip(tk, "Companion");
	tradeMoney0 = sti(PlayerCard.money);
	tradeStock0 = Trade_Stock(townIsland, i);
	tradeOnboard0 = Trade_Onboard(i);
	// the first goods: 3 steps right, buy
	PostEvent("ievnt_command", 300, "ss", "click", "LB_RIGHT");
	PostEvent("ievnt_command", 500, "ss", "click", "LB_RIGHT");
	PostEvent("ievnt_command", 700, "ss", "click", "LB_RIGHT");
	PostEvent("ievnt_command", 900, "ss", "click", "LB_BUY");
	PostEvent("Trade_Verify", 1200);
	PostEvent("Town_AutoQuit", 6000);
}

// after the purchase: the money fell by the price, the hold and the stock moved by the same quantity; then the sale of it
void Trade_Verify()
{
	int i = Trade_Nth(0);
	int got = Trade_Onboard(i) - tradeOnboard0;
	int paid = tradeMoney0 - sti(PlayerCard.money);
	if (tradeStage == 0)
	{
		tradeStage = 1;
		if (got > 0 && paid == got * Trade_Price(townIsland, i) && Trade_Stock(townIsland, i) == tradeStock0 - got) { Trace("PDM store: buy ok, " + got + " for " + paid); }
		else { Trace("PDM store: buy FAIL, got " + got + ", paid " + paid + ", stock " + Trade_Stock(townIsland, i) + " of " + tradeStock0); }
		tradeMoney1 = sti(PlayerCard.money);
		PostEvent("ievnt_command", 100, "ss", "click", "LB_ALL");
		PostEvent("ievnt_command", 300, "ss", "click", "LB_SELL");
		PostEvent("Trade_Verify", 700);
		return;
	}
	if (tradeStage == 1)
	{
		tradeStage = 2;
		int earned1 = sti(PlayerCard.money) - tradeMoney1;
		if (Trade_Onboard(i) == 0 && earned1 > 0) { Trace("PDM store: sell ok, " + earned1 + " earned"); }
		else { Trace("PDM store: sell FAIL, onboard " + Trade_Onboard(i) + ", earned " + earned1); }
		// the next ship of the fleet: the purchase goes into its hold, the flagship stays empty
		PostEvent("ievnt_command", 100, "ss", "click", "LB_NEXTSHIP");
		PostEvent("ievnt_command", 300, "ss", "click", "LB_RIGHT");
		PostEvent("ievnt_command", 500, "ss", "click", "LB_BUY");
		PostEvent("Trade_Verify", 900);
		return;
	}
	int second = Trade_Onboard(i);
	tradeShip = 0;
	int flag = Trade_Onboard(i);
	tradeShip = 1;
	if (second > 0 && flag == 0 && Trade_ShipName() == "Companion") { Trace("PDM store: fleet ok, " + second + " in the hold of " + Trade_ShipName() + ", flagship " + flag); }
	else { Trace("PDM store: fleet FAIL, " + second + " in the second, " + flag + " in the flagship, ship " + tradeShip); }
}
