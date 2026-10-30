// The screens of the original besides the main menu and the world map: the pages of MENU.dll (Options,
// KeyControls, LoadGame, SaveGame, Credits), the status of STATUS.dll (SStuff, SGoods, SShip, LogBook, SChest;
// F1 at sea and in a town, control20 of INI/controls.ini), the trade and the shipyard of TOWN.dll (the
// actions STORE and SHIPYARD of the dialogs) and the screens of RANSACK.dll. tools/pdm_ui.py converts them
// into resource\ini\interfaces\<section>.ini: the picture, the titles and the buttons of the original and
// the fields the scripts fill. Here the buttons go from page to page and back, the fields show the hero
// and his ship; what the screens do (the trade, the repair, the saves) comes with their stages (P9).
// The scene stands still under a screen. SCENE=screens shows every screen in turn and the status over
// the town (the test without key presses).

#define MSG_INTERFACE_SET_FORMATEDTEXT 45038
#define MSG_INTERFACE_SET_NODE_USING 45016
#define SCREEN_KEY 112
#define SCREEN_AUTO_MS 2500
// the scene is drawn by then, the log of the HUD (65535) is not
#define SCREEN_SHOT_PRIORITY 65534

// the open screen, "" if none; "mainmenu" is the menu of menu.c
string screenName = "";
// the screen is over the town or the sea, not over the menu
bool screenOverGame = false;
// the main menu is open over the game (Escape): its pages go back to it, "Продолжить" back to the game (ours)
bool screenGameMenu = false;
// the screen Screen_Go opens, "" closes it; "click" and "activate" of one press change the page once
string screenNext = "";
bool screenGoing = false;
// the screen a dialog asked for (Pdm_LaunchInterface), opened when it closes
string screenPending = "";
// SCENE=screens: the screens it shows over the menu and over the game, where it is in the list and the stage
string screenTourMenu = "options,keycontrols,loadgame,savegame,credits,messagebox,mainmenu";
string screenTourGame = "sgoods,sship,logbook,schest,trade,shipyard,crew,tavern,messagebox_town,transfer,shipexchange,messagebox_ransack";
// the text of the message box and what its "Да" does
// the shipyard: the type chosen in the list (ShipUp/ShipDown) and whether the old ship is sold already
string shipyardPick = "";
bool shipyardSold = false;
int shipyardMoney = 0;
string shipyardOwn = "";
string screenMessage = "";
string screenMessageYes = "";
// the page the message box goes back to
string screenMessageBack = "";
int screenTourAt = 0;
int screenTourStage = 0;

void Screen_Init()
{
	SetEventHandler("Screen_Go", "Screen_Go", 0);
	SetEventHandler("Screen_ShipyardVerify", "Screen_ShipyardVerify", 0);
	SetEventHandler("Screen_Pending", "Screen_Pending", 0);
	SetEventHandler("Screen_Tour", "Screen_Tour", 0);
	SetEventHandler("Screen_Credits", "Screen_CreditsStep", 0);
	SetEventHandler("PdmStory_Interface", "Screen_Launch", 0);
	MapKey("Screen_Status", SCREEN_KEY);
}

// the page a button opens, "back" for the buttons that close a page, "" for the others (ours: the
// original opens them from the C++ of its DLLs)
string Screen_Target(string node)
{
	if (node == "LB_OPTIONS") { return "options"; }
	if (node == "LB_LOADGAME") { return "loadgame"; }
	if (node == "LB_SAVEGAME") { return "savegame"; }
	if (node == "LB_CREDITS") { return "credits"; }
	if (node == "LB_CONTROLS") { return "keycontrols"; }
	if (node == "LB_CHEST") { return "schest"; }
	if (node == "LB_GOODS") { return "sgoods"; }
	if (node == "LB_SHIP") { return "sship"; }
	if (node == "LB_STUFF") { return "sstuff"; }
	if (node == "LB_LOGBOOK") { return "logbook"; }
	if (node == "LB_EXIT" || node == "LB_OK" || node == "LB_CANCEL" || node == "LB_NO") { return "back"; }
	return "";
}

// where a page goes back to: the options from the keys, the menu from its pages, the game from the others
string Screen_Parent(string name)
{
	if (name == "keycontrols") { return "options"; }
	if (name == "messagebox" && screenMessageBack != "") { return screenMessageBack; }
	if (screenGameMenu && name != "mainmenu") { return "mainmenu"; }
	if (screenOverGame) { return ""; }
	return "mainmenu";
}

// the screen over the game (F1, a dialog): the scene stands still, the interface takes the keys
void Screen_Open(string name)
{
	if (screenName != "") { return; }
	Menu_InterfaceKeys();
	LayerFreeze(EXECUTE, true);
	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);
	SetEventHandler("ievnt_command", "Screen_Command", 0);
	screenOverGame = true;
	Screen_Show(name);
}

void Screen_Close()
{
	Trace("PDM screen: closed " + screenName);
	DelEventHandler("ievnt_command", "Screen_Command");
	SendMessage(&GameInterface, "l", MSG_INTERFACE_RELEASE);
	DeleteClass(&GameInterface);
	DeleteClass(&ScrShoter);
	LayerFreeze(EXECUTE, false);
	screenName = "";
	screenOverGame = false;
	screenGameMenu = false;
}

// Escape in the game: the main menu over it, as in the original, the game stands still under it
void Screen_GameMenu()
{
	if (screenName != "") { return; }
	Trace("PDM screen: the menu over the game");
	screenGameMenu = true;
	// the picture of the game under the menu for the header of a save (save.c Save_FromScreen), as the original
	CreateEntity(&ScrShoter, "SCRSHOTER");
	LayerAddObject(REALIZE, &ScrShoter, SCREEN_SHOT_PRIORITY);
	Screen_Open("mainmenu");
}

void Screen_Show(string name)
{
	screenName = name;
	if (name == "trade") { Trade_Begin(); }
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\" + name + ".ini");
	Screen_Fill();
	Trace("PDM screen: " + name);
	Screen_ShipyardCheck(name);
}

void Screen_Text(string node, string text)
{
	SendMessage(&GameInterface, "lss", MSG_INTERFACE_SET_FORMATEDTEXT, node, text);
}

// the credits (ours): the text of credits.ini in CREDITSTEXT goes up by a line from time to time, as the
// original scrolls it, and starts again after the end
float screenCreditsAt = 0.0;
bool screenCreditsRuns = false;

void Screen_CreditsStep()
{
	if (screenName != "credits") { screenCreditsRuns = false; return; }
	screenCreditsAt = screenCreditsAt + 0.002;
	if (screenCreditsAt > 1.1) { screenCreditsAt = 0.0; }
	float at = screenCreditsAt;
	if (at > 1.0) { at = 1.0; }
	SendMessage(&GameInterface, "lslf", MSG_INTERFACE_MSG_TO_NODE, "CREDITSTEXT", 2, at);
	PostEvent("Screen_Credits", 100);
}

void Screen_Credits()
{
	Screen_Text("CREDITSTEXT", PdmScreens.credits.credits);
	screenCreditsAt = 0.0;
	if (screenCreditsRuns) { return; }
	screenCreditsRuns = true;
	PostEvent("Screen_Credits", 100);
}

// the fields of the original the game knows already: the hero under his face, his status and his ship
void Screen_Fill()
{
	if (screenName == "mainmenu")
	{
		// without a game "Сохранить" and "Продолжить" cannot be chosen, as in the original; nor "Сохранить" where
		// the game is not saved (a battle, a boarding)
		bool save = screenOverGame;
		if (Save_Where() == "") { save = false; }
		SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_SAVEGAME", save);
		SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_RESUMEGAME", screenOverGame);
		// a new game over a running one needs the town taken down first: not yet
		SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_NEWGAME", !screenOverGame);
		return;
	}
	if (findSubStr(screenName, "messagebox", 0) == 0) { Screen_Text("EDITTEXT", screenMessage); return; }
	if (screenName == "options") { Options_Fill(); return; }
	if (screenName == "credits") { Screen_Credits(); return; }
	Screen_TitlePlace();
	if (screenName == "trade") { Trade_Lists(); }
	// the name and the money under the face would read as the ones of the save under the cursor
	if (screenName == "loadgame" || screenName == "savegame") { Save_ScreenFill(); return; }
	if (!CheckAttribute(PlayerCard, "money")) { return; }
	string name = PlayerCard.name;
	string ship = PlayerShipCard.name;
	if (screenName == "shipyard")
	{
		// the original has no name here; its "Деньги N" stands at the right bottom (EDITSHIPMONEY, tools/pdm_ui.py)
		Screen_Text("EDITFACENAME", "");
		Screen_Text("EDITFACEMONEY", "");
		Screen_Text("EDITSHIPMONEY", Screen_Put(PdmScreens.shipyard.t.money, PlayerCard.money));
	}
	else
	{
		Screen_Text("EDITFACENAME", name);
		Screen_Text("EDITFACEMONEY", PlayerCard.money);
	}
	Screen_Text("EDITSHIPNAME", ship);
	Screen_Text("EDITSHIPTYPENAME", PlayerShipType.type);
	Screen_ShipText();
	Screen_Lists();
	// the values of the screen in the texts of the original: "Ранг %d", "9 узлов"
	if (!CheckAttribute(PdmScreens, screenName + ".s")) { return; }
	aref values;
	makearef(values, PdmScreens.(screenName).s);
	int n = GetAttributesNum(values);
	for (int i = 0; i < n; i++)
	{
		aref entry = GetAttributeN(values, i);
		string node = GetAttributeName(entry);
		string value = Screen_Value(node);
		if (value == "") { continue; }
		string text = GetAttributeValue(entry);
		if (findSubStr(text, "%", 0) >= 0) { text = Screen_Put(text, value); }
		else
		{
			if (text == "") { text = value; } else { text = value + " " + text; }
		}
		Screen_Text(node, text);
	}
}

// the lists the DLLs of the original drew: the goods of the hold and of the trade (a LIST_<COLUMN> per
// column of tools/pdm_ui.py, PdmScreens.<screen>.list.<column> = its node, a line a row; "\n" breaks a line of a FORMATEDTEXT) and the items of the hero;
// the first row is described under the list
void Screen_Lists()
{
	if (screenName == "schest") { Screen_Items(); return; }
	if (screenName == "trade" && townIsland != "") { return; }
	if (!CheckAttribute(PdmScreens, screenName + ".list")) { return; }
	aref columns, all, row;
	makearef(columns, PdmScreens.(screenName).list);
	// GetAttributeN of the object itself gives a dangling aref, of a makearef a good one
	makearef(all, PdmGoods);
	string first = "";
	int k = GetAttributesNum(columns);
	for (int c = 0; c < k; c++)
	{
		aref entry = GetAttributeN(columns, c);
		string column = GetAttributeName(entry);
		string text = "";
		int n = GetAttributesNum(all);
		for (int i = 0; i < n; i++)
		{
			// by the name, the aref is not passed on
			row = GetAttributeN(all, i);
			string goods = GetAttributeName(row);
			string at = "n" + i;
			int quantity = 0;
			if (CheckAttribute(PlayerShipCard, "cargo." + at)) { quantity = sti(PlayerShipCard.cargo.(at)); }
			// the hold shows what is in it, the trade every goods
			if (screenName == "sgoods" && quantity == 0) { continue; }
			if (first == "") { first = PdmGoods.(goods).filename; }
			text = text + Screen_Cell(column, goods, quantity) + "\n";
		}
		Screen_Text(GetAttributeValue(entry), text);
	}
	if (first == "") { return; }
	string about = Screen_Name("goods", first, "about");
	if (screenName == "sgoods")
	{
		Screen_Text("EDITTOVARNAME", Screen_Name("goods", first, "name"));
		Screen_Text("EDITINVTEXT", about);
	}
	if (screenName == "trade") { Screen_Text("EDITDESC", about); }
}

// a cell of a row of goods; the prices of the town and its store are not there yet (P9): the price of the
// original both ways, the store and the balance empty (ours)
string Screen_Cell(string column, string goods, int quantity)
{
	if (column == "shiptovarname") { return Screen_Name("goods", PdmGoods.(goods).filename, "name"); }
	if (column == "shiponboard" && screenName == "trade") { return "" + quantity; }
	// [SGoods] has p_ShipPrice under "в трюме" and p_ShipOnboard under "вес" (the weight of one, ours)
	if (column == "shipprice" && screenName == "sgoods") { return "" + quantity; }
	if (column == "shiponboard") { return PdmGoods.(goods).weight; }
	if (column == "shipprice" || column == "shopbuyprice") { return PdmGoods.(goods).price; }
	return "";
}

// the name or the description of a goods or an item in the texts of the original, the stem itself without it
string Screen_Name(string kind, string stem, string field)
{
	if (CheckAttribute(PdmScreens, kind + "." + stem + "." + field)) { return PdmScreens.(kind).(stem).(field); }
	if (field == "name") { return stem; }
	return "";
}

// the chest: the items of the hero, "x N" after the name of more than one
void Screen_Items()
{
	if (!CheckAttribute(PlayerCard, "items")) { return; }
	aref items;
	makearef(items, PlayerCard.items);
	string text = "";
	string first = "";
	int n = GetAttributesNum(items);
	for (int i = 0; i < n; i++)
	{
		aref entry = GetAttributeN(items, i);
		int count = sti(GetAttributeValue(entry));
		string id = GetAttributeName(entry);
		if (count <= 0 || id == "money") { continue; }
		string stem = id;
		if (CheckAttribute(PdmItems, id + ".description")) { stem = PdmItems.(id).description; }
		if (stem == "" && CheckAttribute(PdmItems, id + ".filename")) { stem = PdmItems.(id).filename; }
		if (first == "") { first = stem; }
		string line = Screen_Name("items", stem, "name");
		if (count > 1) { line = line + " x" + count; }
		text = text + line + "\n";
	}
	Screen_Text("EDITINVENTORY", text);
	if (first != "") { Screen_Text("EDITINVTEXT", Screen_Name("items", first, "about")); }
}

// the message box over the screen with a text, "Да" does <yes> (the scripts of the screen that asked)
void Screen_Message(string text, string yes)
{
	screenMessage = text;
	screenMessageYes = yes;
	screenMessageBack = screenName;
	screenNext = "messagebox";
	screenGoing = true;
	PostEvent("Screen_Go", 0);
}

// "Магазин на %s", "Верфь на %s": the island of the town, as the label of the world map (PdmScreens of
// tools/pdm_ui.py: the number of the title in TITLES and its text)
void Screen_TitlePlace()
{
	if (!CheckAttribute(PdmScreens, screenName + ".title") || townIsland == "") { return; }
	string place = townIsland;
	if (CheckAttribute(PdmIslands, townIsland + ".label")) { place = PdmIslands.(townIsland).label; }
	string text = PdmScreens.(screenName).text;
	int at = findSubStr(text, "%s", 0);
	if (at < 0) { return; }
	string tail = "";
	if (at + 2 < strlen(text)) { tail = strcut(text, at + 2, strlen(text) - 1); }
	text = strcut(text, 0, at - 1) + place + tail;
	int n = sti(PdmScreens.(screenName).title);
	SendMessage(&GameInterface, "lslls", MSG_INTERFACE_MSG_TO_NODE, "TITLES", 1, n, "#" + text);
}

// the first %d or %s of a text of the original replaced with the value
string Screen_Put(string text, string value)
{
	int at = findSubStr(text, "%", 0);
	string tail = "";
	if (at + 2 < strlen(text)) { tail = strcut(text, at + 2, strlen(text) - 1); }
	if (at == 0) { return value + tail; }
	return strcut(text, 0, at - 1) + value + tail;
}

// the weight in the hold: the goods of the ship of the hero
int Screen_Cargo()
{
	if (!CheckAttribute(PlayerShipCard, "cargo")) { return 0; }
	aref cargo;
	makearef(cargo, PlayerShipCard.cargo);
	return Trade_Load();
}

// the first number of "4,0,0" (the guns of a board, of the stern)
// the n-th number of a "a,b,c" list
string Screen_Nth(string list, int n)
{
	string rest = list;
	for (int i = 0; i < n; i++)
	{
		int at = findSubStr(rest, ",", 0);
		if (at < 0) { return ""; }
		rest = strcut(rest, at + 1, strlen(rest) - 1);
	}
	return Screen_First(rest);
}

// "4 + 4": the guns of the board are on both sides
string Screen_Board(string list)
{
	string n = Screen_First(list);
	return n + " + " + n;
}

// the best class the rank lets command (ours: the original counts it in TOWN.dll)
int Screen_RankClass(int rank)
{
	if (rank >= 25) { return 1; }
	if (rank >= 20) { return 2; }
	if (rank >= 15) { return 3; }
	if (rank >= 10) { return 4; }
	if (rank >= 5) { return 5; }
	return 6;
}

string Screen_Decimal(string value)
{
	if (screenName != "shipyard") { return value; }
	if (findSubStr(value, ".", 0) >= 0) { return value; }
	return value + ".0";
}

// what the shipyard of the original does not show for this hero: the sheathing and the refit buttons, the
// rows of the gun prices (they stay empty there too)
void Screen_ShipyardHide()
{
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "LB_UPGRADE", false);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "LB_REFIT", false);
	string nodes = "S_LBS0,S_LBS1,S_GOLD0,S_GOLD1";
	int at = 0;
	while (at < strlen(nodes))
	{
		int end = findSubStr(nodes, ",", at);
		if (end < 0) { end = strlen(nodes); }
		Screen_Text(strcut(nodes, at, end - 1), "");
		at = end + 1;
	}
}

// the right window of the shipyard: the types by class, "Ваш корабль" on top, the price and the rank under it
// (the texts are of the screenshot of the original: they are not in the files read so far)
void Screen_ShipyardRight()
{
	string list = PdmScreens.shipyard.t.yourship + "\n";
	int rank = 0;
	if (CheckAttribute(PlayerCard, "rank")) { rank = sti(PlayerCard.rank); }
	int n = GetAttributesNum(&PdmShipTypes);
	for (int c = 5; c <= 6; c++)
	{
		list = list + "\n" + Screen_Put(PdmScreens.shipyard.t.classorder, "" + c) + "\n";
		for (int i = 0; i < n; i++)
		{
			aref type;
			type = GetAttributeN(&PdmShipTypes, i);
			if (sti(type.class) != c) { continue; }
			string id = type.id;
			if (CheckAttribute(PdmScreens, "ships." + id + ".name")) { list = list + PdmScreens.ships.(id).name + "\n"; }
		}
	}
	Screen_Text("EDITSHIP", list);
	Screen_Text("EDITSUMMA", Screen_Put(PdmScreens.shipyard.t.shipcost, PlayerShipType.sellprice));
	Screen_Text("EDITDAMAGES", Screen_Put(PdmScreens.shipyard.t.shipdamages, "0"));
	Screen_Text("EDITHELP", Screen_Put(PdmScreens.shipyard.t.buybutclass, "" + Screen_RankClass(rank)));
	Screen_Text("EDITHULL", "100%");
	Screen_Text("EDITRIG", "100%");
	Screen_ShipyardHide();
	Screen_Text("EDITHULLSUM", "0");
	Screen_Text("EDITRIGSUM", "0");
}

// the type and the description of the ship of the hero in the words of the original (tools/pdm_ui.py, GOODS/SHIPS)
void Screen_ShipText()
{
	string id = PlayerShipType.id;
	if (CheckAttribute(PdmScreens, "ships." + id + ".name")) { Screen_Text("EDITSHIPTYPE", PdmScreens.ships.(id).name); }
	if (CheckAttribute(PdmScreens, "ships." + id + ".about")) { Screen_Text("EDITDESC", PdmScreens.ships.(id).about); }
	if (screenName == "shipyard")
	{
		// the picture of the ship in its frame (the original IMAGES/GOODS/SHIPS, ship_<id> of tools/pdm_ui.py)
		SendMessage(&GameInterface, "lslls", MSG_INTERFACE_MSG_TO_NODE, "SHIPSPRITE", 2, 0, "interfaces\\pdm\\ship_" + id + ".tga");
		SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "SHIPSPRITE", 1);
		// the picture of the gun in its frame (GOODS/GOODS/<file>64.tga of the original, cannon_<file>)
		if (CheckAttribute(PdmCannons, "Demi_culverins.filename"))
		{
			SendMessage(&GameInterface, "lslls", MSG_INTERFACE_MSG_TO_NODE, "CANNONSPRITE", 2, 0, "interfaces\\pdm\\cannon_" + Town_Lower(PdmCannons.Demi_culverins.filename) + ".tga");
			SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "CANNONSPRITE", 1);
		}
		Screen_ShipyardRight();
	}
}

// the numbers of the gun of the hero: "12,400,40,27" is the shot, the range, the reload and the weight
string Screen_Cannon(string node)
{
	string key = "Demi_culverins";
	if (!CheckAttribute(PdmCannons, key + ".params")) { return ""; }
	string params = PdmCannons.(key).params;
	if (node == "S_CALIBERSET") { return Screen_Nth(params, 0); }
	if (node == "S_FIRERANGE") { return Screen_Nth(params, 1); }
	if (node == "S_RELOADRATE") { return Screen_Nth(params, 2); }
	return Screen_Nth(params, 3);
}

string Screen_First(string list)
{
	int at = findSubStr(list, ",", 0);
	if (at <= 0) { return list; }
	return strcut(list, 0, at - 1);
}

// the value of an s_ node of the original the game knows, "" for the others (the shipyard and the trade show
// the ship of the hero until they have their own, P9)
string Screen_Value(string node)
{
	if (screenName == "trade" && Trade_Value(node) != "") { return Trade_Value(node); }
	if (node == "S_CAPTAIN") { return PlayerCard.name; }
	if (node == "S_RANK") { return PlayerCard.rank; }
	if (node == "S_EXPERIENCE") { return PlayerCard.experience; }
	if (node == "S_MONEY") { return PlayerCard.money; }
	if (node == "S_REPUTATION") { return PlayerCard.reputation; }
	if (node == "S_CREWNUM") { return PlayerShipCard.crew; }
	if (node == "S_CREWALLOWED") { return PlayerShipType.maxcrew; }
	if (node == "S_TYPE") { return PlayerShipType.type; }
	if (node == "S_CLASS") { return PlayerShipType.class; }
	if (node == "S_HITPOINTS") { return PlayerShipType.hitpoint; }
	// the shipyard shows them with a decimal: "9.0", "55.0"
	if (node == "S_SPEEDRATE") { return Screen_Decimal(PlayerShipType.speedrate); }
	if (node == "S_TURNRATE") { return Screen_Decimal(PlayerShipType.turnrate); }
	if (node == "S_MAXCREW") { return PlayerShipType.maxcrew; }
	if (node == "S_MINCREW") { return PlayerShipType.mincrew; }
	if (node == "S_CAPACITY" || node == "S_MAXWEIGHT") { return PlayerShipType.capacity; }
	if (node == "S_WEIGHT" || node == "S_TOTALWEIGHT") { return "" + Screen_Cargo(); }
	if (node == "S_GUNPORTS") { return PlayerShipType.cannonstotal; }
	if (node == "S_BOARD") { return Screen_Board(PlayerShipType.deckcannons); }
	if (node == "S_STERN") { return Screen_First(PlayerShipType.cannonback); }
	if (node == "S_CALIBERSET" || node == "S_SHOTWEIGHT" || node == "S_FIRERANGE" || node == "S_RELOADRATE") { return Screen_Cannon(node); }
	if (node == "S_BOARDNUM") { return Screen_First(PlayerShipType.deckcannons); }
	if (node == "S_STERNNUM") { return Screen_First(PlayerShipType.cannonback); }
	return "";
}


// the price of a ship the shipyard asks (A of the original) and gives (B), in hundreds; the skill and the
// reputation of the hero are not mapped yet (docs/original-vs-remake.md), so the spread is 0
int Screen_ShipBuyPrice(string id) { return (sti(PdmShipTypes.(id).buyprice) / 100) * 100; }
int Screen_ShipSellPrice(string id) { return (sti(PdmShipTypes.(id).sellprice) / 100) * 100; }

// the next type of the list "Класс 5/6" after the chosen one (step -1: the previous)
void Screen_ShipyardStep(int step)
{
	int n = GetAttributesNum(&PdmShipTypes);
	int at = -1;
	int first = -1;
	for (int i = 0; i < n; i++)
	{
		aref type;
		type = GetAttributeN(&PdmShipTypes, i);
		int c = sti(type.class);
		if (c != 5 && c != 6) { continue; }
		if (type.id == shipyardPick) { at = i; }
	}
	int k = at;
	for (int j = 0; j < n; j++)
	{
		k = k + step;
		if (k >= n) { k = 0; }
		if (k < 0) { k = n - 1; }
		aref cand;
		cand = GetAttributeN(&PdmShipTypes, k);
		int cc = sti(cand.class);
		if (cc == 5 || cc == 6) { shipyardPick = cand.id; break; }
	}
	string id = shipyardPick;
	Screen_Text("EDITSUMMA", Screen_Put(PdmScreens.shipyard.t.shipcost, Screen_ShipBuyPrice(id)));
	if (CheckAttribute(PdmScreens, "ships." + id + ".name")) { Screen_Text("EDITSHIPTYPE", PdmScreens.ships.(id).name); }
	Trace("PDM shipyard: pick " + id);
}

// Sell: the hero gets the price B of the ship, the type is chosen from the list; Buy: needs the old ship sold
// and the gold, the new one takes its place (the messages are the original ones)
bool Screen_ShipyardClick(string node)
{
	if (node == "LB_SHIPUP") { Screen_ShipyardStep(-1); return true; }
	if (node == "LB_SHIPDOWN") { Screen_ShipyardStep(1); return true; }
	if (node == "LB_SELL")
	{
		if (shipyardSold) { return true; }
		string own = PlayerShipType.id;
		PlayerCard.money = sti(PlayerCard.money) + Screen_ShipSellPrice(own);
		shipyardSold = true;
		Screen_Text("EDITSHIPMONEY", Screen_Put(PdmScreens.shipyard.t.money, PlayerCard.money));
		Trace("PDM shipyard: sold " + own + ", money " + PlayerCard.money);
		return true;
	}
	if (node == "LB_BUY")
	{
		if (shipyardPick == "") { Screen_ShipyardStep(1); }
		string id = shipyardPick;
		if (!shipyardSold) { Screen_Text("EDITHELP", PdmScreens.shipyard.t.buybutsell); Trace("PDM shipyard: refused, sell the old ship"); return true; }
		int price = Screen_ShipBuyPrice(id);
		if (sti(PlayerCard.money) < price) { Screen_Text("EDITHELP", PdmScreens.shipyard.t.buybutmoney); Trace("PDM shipyard: refused, no money"); return true; }
		PlayerCard.money = sti(PlayerCard.money) - price;
		PlayerShipCard.type_key = id;
		makearef(PlayerShipType, PdmShipTypes.(id));
		shipyardSold = false;
		Screen_ShipText();
		Screen_Text("EDITSHIPMONEY", Screen_Put(PdmScreens.shipyard.t.money, PlayerCard.money));
		Trace("PDM shipyard: bought " + id + ", money " + PlayerCard.money);
		return true;
	}
	return false;
}

void Screen_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command != "click" && command != "activate") { return; }
	if (screenName == "mainmenu")
	{
		if (node == "LB_RESUMEGAME") { Screen_Escape(); return; }
		if (node == "LB_EXIT") { Screen_Message(PdmScreens.mainmenu.t.exit, "exit"); return; }
		if (node == "LB_NEWGAME") { return; }
	}
	if (screenName == "messagebox" && node == "LB_YES" && screenMessageYes == "exit") { ExitProgram(); return; }
	if (screenName == "trade" && Trade_Click(node)) { return; }
	if (screenName == "shipyard" && Screen_ShipyardClick(node)) { return; }
	if (Screen_Page(node)) { return; }
	Screen_Click(node);
}

// the buttons that do something on their page (options.c, save.c); true if it was one. "Да" of their message
// box does it and goes back to the page
bool Screen_Page(string node)
{
	if (screenName == "options") { return Options_Click(node); }
	if (screenName == "loadgame" || screenName == "savegame") { return Save_ScreenClick(node); }
	if (screenName != "messagebox" || node != "LB_YES") { return false; }
	if (screenMessageYes != "delete" && screenMessageYes != "overwrite") { return false; }
	Save_ScreenYes();
	Screen_Click("LB_NO");
	return true;
}

// a button that goes to another page or back; true if it was one. The page changes after the event:
// the button is still being pressed in it (menu.c)
bool Screen_Click(string node)
{
	string to = Screen_Target(node);
	if (to == "") { return false; }
	if (screenGoing) { return true; }
	if (to == "back") { to = Screen_Parent(screenName); }
	Trace("PDM screen: " + screenName + " " + node + " -> " + to);
	screenNext = to;
	screenGoing = true;
	PostEvent("Screen_Go", 0);
	return true;
}

void Screen_Go()
{
	screenGoing = false;
	if (screenNext == "") { Screen_Close(); return; }
	Screen_Show(screenNext);
}

// Escape on a screen: back, as its Exit
bool Screen_Escape()
{
	if (screenName == "") { return false; }
	if (screenName == "mainmenu" && !screenGameMenu) { return false; }
	if (screenGoing) { return true; }
	screenNext = Screen_Parent(screenName);
	// the menu over the game goes back to the game
	if (screenName == "mainmenu") { screenNext = ""; }
	screenGoing = true;
	PostEvent("Screen_Go", 0);
	return true;
}

// F1: the status, in a town out of a dialog or at sea
void Screen_Status()
{
	if (screenName != "") { return; }
	// the script compiler takes no brackets inside a condition
	if (!seaActive)
	{
		if (!townLoaded || townTalkNpc >= 0) { return; }
	}
	Screen_Open("sstuff");
}

// Pdm_LaunchInterface("TOWN", "trade"): the dialog is open, the screen comes when it closes
void Screen_Launch()
{
	string dll = GetEventData();
	string page = GetEventData();
	screenPending = page;
	Trace("PDM screen: " + dll + " " + page + " after the dialog");
}

void Screen_Pending()
{
	if (screenPending == "") { return; }
	string name = screenPending;
	screenPending = "";
	Screen_Open(name);
}

// the next name of a list of the tour, "" at its end
string Screen_TourNext(string list)
{
	if (screenTourAt >= strlen(list)) { return ""; }
	int end = findSubStr(list, ",", screenTourAt);
	if (end < 0) { end = strlen(list); }
	string name = strcut(list, screenTourAt, end - 1);
	screenTourAt = end + 1;
	return name;
}

// the trade in the tour: the second goods bought five times and sold at once (the log tells the money and the hold)
void Screen_TourTrade(string name)
{
	if (name != "trade") { return; }
	PlayerCard.money = 500;
	string keys = "LB_TOVARDOWN,LB_RIGHT,LB_RIGHT,LB_RIGHT,LB_RIGHT,LB_RIGHT,LB_BUY,LB_LEFT,LB_SELL,LB_TOVARDOWN,LB_ALL,LB_BUY";
	int at = 0;
	int t = 300;
	while (at < strlen(keys))
	{
		int end = findSubStr(keys, ",", at);
		if (end < 0) { end = strlen(keys); }
		PostEvent("ievnt_command", t, "ss", "click", strcut(keys, at, end - 1));
		at = end + 1;
		t = t + 120;
	}
}

// TOWN_AUTO=19: the hero talks to the shipyard owner in the town and picks "верфь"; the values of the screen must be
// there (the log tells the empty ones), then the game quits
void Screen_ShipyardCheck(string name)
{
	if (TownAuto != SHIPYARD_ID || name != "shipyard") { return; }
	string nodes = "S_CLASS,S_HITPOINTS,S_SPEEDRATE,S_TURNRATE,S_MAXCREW,S_MINCREW,S_CAPACITY,S_GUNPORTS,S_BOARD,S_STERN,S_CALIBERSET,S_SHOTWEIGHT,S_FIRERANGE,S_RELOADRATE";
	string empty = "";
	int at = 0;
	while (at < strlen(nodes))
	{
		int end = findSubStr(nodes, ",", at);
		if (end < 0) { end = strlen(nodes); }
		string node = strcut(nodes, at, end - 1);
		string value = Screen_Value(node);
		Trace("PDM shipyard: " + node + " = '" + value + "'");
		if (value == "") { empty = empty + node + " "; }
		at = end + 1;
	}
	string id = PlayerShipType.id;
	if (!CheckAttribute(PdmScreens, "ships." + id + ".name")) { empty = empty + "type "; }
	if (!CheckAttribute(PdmScreens, "ships." + id + ".about")) { empty = empty + "about "; }
	if (empty == "") { Trace("PDM shipyard: values ok"); }
	else { Trace("PDM shipyard: FAIL, empty " + empty); }
	shipyardMoney = sti(PlayerCard.money);
	shipyardOwn = PlayerShipType.id;
	PostEvent("ievnt_command", 500, "ss", "click", "LB_BUY");
	PostEvent("ievnt_command", 800, "ss", "click", "LB_SELL");
	PostEvent("ievnt_command", 1100, "ss", "click", "LB_BUY");
	PostEvent("Screen_ShipyardVerify", 2000);
	PostEvent("Town_AutoQuit", 4000);
}

// the buttons in the test: the first Buy is refused (the old ship stands), Sell gives B, Buy takes A of the picked one
void Screen_ShipyardVerify()
{
	string id = shipyardPick;
	int want = shipyardMoney + Screen_ShipSellPrice(shipyardOwn) - Screen_ShipBuyPrice(id);
	if (PlayerShipType.id == id && sti(PlayerCard.money) == want && id != "") { Trace("PDM shipyard: actions ok"); }
	else { Trace("PDM shipyard: actions FAIL, type " + PlayerShipType.id + ", pick " + id + ", money " + PlayerCard.money + ", want " + want); }
}

// SCENE=screens: the pages of the menu, a new game, F1 in the town and its button "Корабль", the other
// screens over the game with the hero filled in, Escape back to the game
void Screen_Tour()
{
	string name;
	if (screenTourStage == 0)
	{
		name = Screen_TourNext(screenTourMenu);
		screenMessage = PdmScreens.mainmenu.t.exit;
		if (name != "") { Screen_Show(name); PostEvent("Screen_Tour", SCREEN_AUTO_MS); return; }
		screenTourStage = 1;
		screenTourAt = 0;
		PostEvent("ievnt_command", 0, "ss", "click", "LB_NEWGAME");
		// the town loads in a few seconds
		PostEvent("Screen_Tour", 12000);
		return;
	}
	if (screenTourStage == 1)
	{
		screenTourStage = 2;
		Screen_Status();
		PostEvent("ievnt_command", SCREEN_AUTO_MS, "ss", "click", "LB_SHIP");
		PostEvent("Screen_Tour", SCREEN_AUTO_MS * 2);
		return;
	}
	if (screenTourStage == 2)
	{
		name = Screen_TourNext(screenTourGame);
		if (name != "") { Screen_Show(name); Screen_TourTrade(name); PostEvent("Screen_Tour", SCREEN_AUTO_MS); return; }
		screenTourStage = 3;
		Screen_Escape();
		PostEvent("Screen_Tour", SCREEN_AUTO_MS);
		return;
	}
	Trace("PDM screen: the tour is over, the screen '" + screenName + "'");
	ExitProgram();
}
