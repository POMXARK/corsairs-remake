// The encounters of the world map: ships of the nations that meet the hero at sea (MAP.dll, docs/original-vs-remake.md).
// Data of mapparam.ini and interface.ini come from tools/pdm_encounters.py (data\pdm_encounters.c):
//   PdmEncGrid.n<nation>.c<col>_<row>  the pattern of the nation in the cell of the map (20 x 15 cells of 60 px)
//   PdmEncIsland.r<dy>_<dx>            the pattern round an island, the island at 2_2
//   PdmPattern.p<n>                    merchants mc and warships wc, with the classes of their ships from u (big) to d (small)
// While the hero sails, the time he spent is summed up; it is checked against the limit of the original
// ENC_BASE_MS / (rand * 0.05 + closeness to islands + 0.01), the limit is rolled again every tick. Over the limit a nation
// with a pattern in the cell is picked and a message comes up (the scroll of the map): the sail of a nation or of pirates
// (types 0, 1, 2: "Напасть" / "Пропустить"), or the attack (types 3, 4: "Да", then the battle).
// Ours, and not in the original yet (docs/gaps-plan.md): the war of the nations (relations, every nation not pirate only
// shows its sail), the condition of the ships in the attack, the storm, the pay of the crew, the whole squadron
// (the battle has the first ship of the pattern only), the ships fighting each other (type 9).

#define ENC_BASE_MS 2000.0
#define ENC_CELL 60.0
#define ENC_ATTACK_ROLL 300
#define ENC_ATTACK_MIN 30
#define ENC_TRIES 64
// the layer of the islands after the four nations (nations.idf: england, pirate, france, spain)
#define ENC_NATIONS 4
#define ENC_PIRATE 1
// the window in the 800 x 600 of the screen (map_message.tga 564 x 351, centred; the text and buttons by map.ini of the original)
#define ENC_SCROLL_L 118
#define ENC_SCROLL_T 124
#define ENC_SCROLL_R 682
#define ENC_SCROLL_B 475
#define ENC_AUTO_MS 1500
#define ENC_AUTO_QUIT_MS 6000

int encAcc = 0;
bool encShown = false;
int encPay = 0;         // the sum the window of the pay (message 6) asks, 0 for the other windows
bool encPlain = false; // the window only says something: "OK" closes it, no battle
int encKind = -1;       // the number of the message shown (Mapparammessage<n>, 32 the weekly pay)
// the type of the message (Mapparammessage<n>), the nation and the pattern met
int encType = -1;
int encNation = ENC_PIRATE;
int encPattern = 0;
// the nearest island of the place of the meeting: the sea of the battle is the sea of it
string encIsland = "";
// the ship of the battle: a type of PdmShipTypes and the nation; the battle takes the card from here (Battle_EnemyKey)
string encShipType = "";
int encCount = 0;
// TOWN_AUTO=24: the first tick forces the attack of pirates, the autotest answers by itself
int encForce = 0;
int encPick[5];
int encPats[5];
object MapEncText;

string Enc_Text(string key)
{
	if (!CheckAttribute(&PdmEncText, key)) { return ""; }
	return PdmEncText.(key);
}

// text with the first %s (or %d: the pay windows) replaced
string Enc_Format(string text, string arg)
{
	int at = findSubStr(text, "%s", 0);
	if (at < 0) { at = findSubStr(text, "%d", 0); }
	if (at < 0) { return text; }
	string head = "";
	if (at > 0) { head = strcut(text, 0, at - 1); }
	string tail = "";
	if (at + 2 < strlen(text)) { tail = strcut(text, at + 2, strlen(text) - 1); }
	return head + arg + tail;
}

// "английск", "пиратск", ... (mapEnglish ...): the stem to which the text adds its ending
string Enc_Adjective(int nation)
{
	if (nation == 0) { return Enc_Text("mapEnglish"); }
	if (nation == 1) { return Enc_Text("mapPirates"); }
	if (nation == 2) { return Enc_Text("mapFrench"); }
	return Enc_Text("mapSpanish");
}

string Enc_Noun(int nation)
{
	if (nation == 0) { return Enc_Text("mapEnglish1"); }
	if (nation == 1) { return Enc_Text("mapPirates1"); }
	if (nation == 2) { return Enc_Text("mapFrench1"); }
	return Enc_Text("mapSpanish1");
}

// the pattern of the nation in the cell, 0 none
int Enc_NationPattern(int nation, int col, int row)
{
	string path = "n" + nation + ".c" + col + "_" + row;
	if (!CheckAttribute(&PdmEncGrid, path)) { return 0; }
	return sti(PdmEncGrid.(path));
}

// the pattern round the nearest island if the hero is in its 5 x 5 cells, 0 none
int Enc_IslandPattern(int col, int row, int iconCol, int iconRow)
{
	int dx = col - iconCol + 2;
	int dy = row - iconRow + 2;
	if (dx < 0 || dx > 4 || dy < 0 || dy > 4) { return 0; }
	string path = "r" + dy + "_" + dx;
	if (!CheckAttribute(&PdmEncIsland, path)) { return 0; }
	return sti(PdmEncIsland.(path));
}

// the sum of 1 / d^2 over the islands from the place of the hero in cells (at most 1) and the nearest island; the
// cell of an island is the first number of its map_cell (row * 20 + column), its middle is the point
float Enc_Closeness(float x, float y)
{
	float sum = 0.0;
	float best = 10000.0;
	encIsland = "";
	string at, key, cell;
	int number;
	float fx, fy, d;
	for (int i = 0; i < mapIslandCount; i++)
	{
		at = "i" + i;
		key = MapIslands.(at);
		cell = PdmIslands.(key).map_cell;
		number = sti(strcut(cell, 0, findSubStr(cell, ",", 0) - 1));
		fx = (number % 20) + 0.5;
		fy = makeint(number / 20) + 0.5;
		d = (x - fx) * (x - fx) + (y - fy) * (y - fy);
		if (d < best) { best = d; encIsland = key; }
		if (d > 0.0001) { sum = sum + 1.0 / d; }
	}
	if (sum > 1.0) { sum = 1.0; }
	return sum;
}

// a tick of the sail: ms since the last one
// does the crew rise: on the step of the map (reputation below -30: 1 in (|rep|-30)*6), at the weekly reminder in debt
// (|rep|-1 tries of 1 in 100, TryBunt 0x10008c40); TOWN_AUTO=40 makes it sure; the mutiny itself (BuntR1) is not made
bool Enc_Bunt(bool weekly)
{
	if (TownAuto == 40) { return true; }
	int rep = Pdm_Count(PlayerCard, "reputation");
	if (rep < -35) { rep = -35; }
	if (weekly)
	{
		for (int i = 1; i < 0 - rep; i++)
		{
			if (rand(99) == 50) { return true; }
		}
		return false;
	}
	if (rep >= -30) { return false; }
	int n = (0 - rep - 30) * 6;
	return rand(n - 1) == n / 2;
}

void Enc_Tick(int ms)
{
	if (encShown) { return; }
	encAcc = encAcc + ms;
	float x = mapX / ENC_CELL;
	float y = mapY / ENC_CELL;
	float close = Enc_Closeness(x, y);
	float limit = ENC_BASE_MS / (rand(13) * 0.05 + close + 0.01);
	if (encForce == 1)
	{
		encForce = 2;
		encAcc = makeint(limit) + 1;
	}
	if (encAcc < limit) { return; }
	// the crew with a bad captain mutinies instead of the meeting (the check of 0x10008b50 at the step of the map)
	if (Enc_Bunt(false))
	{
		encAcc = 0;
		Enc_Show(12, Enc_Text("MapMessageBunt"));
		return;
	}
	int col = makeint(x);
	int row = makeint(y);
	// the layers with a pattern in this cell: the four nations and the island
	int layers = 0;
	int i;
	int p;
	for (i = 0; i < ENC_NATIONS; i++)
	{
		p = Enc_NationPattern(i, col, row);
		if (p > 0) { encPick[layers] = i; encPats[layers] = p; layers++; }
	}
	if (encIsland != "" && CheckAttribute(&PdmIslands, encIsland + ".nation"))
	{
		string cell = PdmIslands.(encIsland).map_cell;
		int number = sti(strcut(cell, 0, findSubStr(cell, ",", 0) - 1));
		p = Enc_IslandPattern(col, row, number % 20, makeint(number / 20));
		if (p > 0) { encPick[layers] = sti(PdmIslands.(encIsland).nation); encPats[layers] = p; layers++; }
	}
	if (encForce == 2)
	{
		encForce = 3;
		layers = 1;
		encPick[0] = ENC_PIRATE;
		encPats[0] = 21;
		// TOWN_AUTO=25: the merchants of England (pattern 5), the hero attacks them and they run away
		if (TownAuto == 25 || TownAuto == 34) { encPick[0] = 0; encPats[0] = 5; }
		// TOWN_AUTO=36: England and Spain meet in one cell, they fight each other (message 9)
		if (TownAuto == 36) { layers = 2; encPick[0] = 0; encPats[0] = 5; encPick[1] = 3; encPats[1] = 5; }
		// TOWN_AUTO=26: the pirate squadron of three (pattern 8), the hero attacks, the escorts join the battle
		if (TownAuto == 26) { encPats[0] = 8; }
	}
	if (layers == 0) { return; }
	int at = rand(layers - 1);
	if (TownAuto == 36) { at = 0; }
	if (Enc_War(layers, at)) { return; }
	Enc_Meet(encPick[at], encPats[at]);
}

// MAP.dll isEnemy for two nations that are not the hero's: different nations, both known, are enemies (the hero has no
// nation of his own in the remake: the rule for his nation is Enc_Relation)
bool Enc_IsEnemy(int first, int second)
{
	if (first < 0 || second < 0 || first == second) { return false; }
	return true;
}

// GetWar of MAP.dll: with two nations or more in the cell the nation picked may meet an enemy of its own: "ships fight each
// other" (message 9), the roll is over 220 of 300. Returns true when the message came up.
bool Enc_War(int layers, int at)
{
	if (layers < 2) { return false; }
	int enemies = 0;
	int j;
	for (j = 0; j < layers; j++)
	{
		if (j != at && Enc_IsEnemy(encPick[at], encPick[j])) { enemies++; }
	}
	if (enemies == 0) { return false; }
	int roll = rand(ENC_ATTACK_ROLL - 1);
	if (TownAuto == 36) { roll = ENC_ATTACK_ROLL - 1; }
	if (roll <= 220) { return false; }
	int nth = rand(enemies - 1);
	int other = -1;
	for (j = 0; j < layers; j++)
	{
		if (j == at || !Enc_IsEnemy(encPick[at], encPick[j])) { continue; }
		if (nth == 0) { other = encPick[j]; break; }
		nth--;
	}
	encAcc = 0;
	encNation = encPick[at];
	encPattern = encPats[at];
	string pat = "p" + encPattern;
	int mc = sti(PdmPattern.(pat).mc);
	int wc = sti(PdmPattern.(pat).wc);
	encCount = wc;
	if (wc == 0) { encCount = mc; }
	encType = 9;
	string text = Enc_Format(Enc_Format(Enc_Text("MapMessageWAR"), Enc_Adjective(encNation)), Enc_Adjective(other));
	Trace("PDM war: ships of nation " + encNation + " fight nation " + other + " (" + text + ")");
	Sound_Once("mapattack");
	Enc_Show(9, text);
	return true;
}

// a meeting with the pattern of the nation: the type of the message by the rules of the original, then the window
void Enc_Meet(int nation, int pattern)
{
	encAcc = 0;
	encNation = nation;
	encPattern = pattern;
	string pat = "p" + pattern;
	int mc = sti(PdmPattern.(pat).mc);
	int wc = sti(PdmPattern.(pat).wc);
	encCount = wc;
	if (wc == 0) { encCount = mc; }
	bool attack = false;
	if (nation == ENC_PIRATE)
	{
		// a pirate attacks when the roll is over ENC_ATTACK_MIN (the original adds more when the hero is at war: ours
		// the war is not yet), else his sail is only seen
		attack = rand(ENC_ATTACK_ROLL - 1) > ENC_ATTACK_MIN;
		encType = 2;
		if (attack) { encType = 4; }
	}
	else
	{
		// the sail of a nation: merchants in the pattern are the type 1, the warships the type 0; the attack of a nation
		// needs war with it, which the remake does not have yet
		encType = 0;
		if (mc > 0 && wc == 0) { encType = 1; }
		// a nation at war with the hero (relation 2, MAP.dll isEnemy) attacks by the same roll as pirates, the others never
		if (Enc_Relation(nation) == 2)
		{
			int roll = rand(ENC_ATTACK_ROLL - 1);
			if (TownAuto == 34) { roll = ENC_ATTACK_ROLL - 1; }
			if (roll > ENC_ATTACK_MIN) { encType = 3; }
			else { encType = 2; }
		}
	}
	if (encForce == 3 && TownAuto == 34) { encForce = 0; }
	if (encForce == 3) { encType = 4; if (TownAuto == 25) { encType = 1; } encForce = 0; }
	string text = Enc_Message(encType, nation, pattern, encCount);
	Trace("PDM encounter: nation " + nation + ", pattern " + pattern + ", type " + encType + ", " + encCount + " ship(s) at " + encIsland);
	// the sound of the sail (MAP.dll): an attack - mapattack, pirates in sight - mapenemy, the sail of a nation - mapship
	if (encType == 3 || encType == 4) { Sound_Once("mapattack"); }
	else if (encType == 2) { Sound_Once("mapenemy"); }
	else { Sound_Once("mapship"); }
	if (TownAuto == 34 && encType == 3) { Trace("PDM war: hostile nation " + nation + " attacks"); }
	Enc_Show(encType, text);
}

// the relation of the hero with a nation: 0 neutral, 1 ally, 2 hostile (relations.idf; the table of the hero is
// PlayerCard.relations.n<nation>)
int Enc_Relation(int nation)
{
	string at = "n" + nation;
	if (!CheckAttribute(&PlayerCard, "relations." + at)) { return 0; }
	return sti(PlayerCard.relations.(at));
}

string Enc_Message(int type, int nation, int pattern, int count)
{
	string key = "Mapparammessage" + type;
	string text = Enc_Text(key);
	if (type == 0 || type == 1 || type == 3) { return Enc_Format(text, Enc_Adjective(nation)); }
	if (type == 2 || type == 4) { return text; }
	return text;
}

// the window: the scroll, the text and the buttons ("Да" for an attack; "Напасть" and "Пропустить" for a sail)
void Enc_Show(int type, string text)
{
	encShown = true;
	int e = mapEdge;
	int t = mapTopEdge;
	encKind = type;
	if (type == 12) { Trace("PDM map: mutiny message"); }
	encPlain = type == 5 || type == 11 || type == 12 || type == 33;
	encPay = 0;
	if (type == 4 || type == 3)
	{
		// the attack: as the attack of pirates the text of the count and the nation too, the original puts it into MapMessageAttack
		string line = Enc_Text("attack" + encCount);
		if (line == "") { line = Enc_Text("attack1"); }
		text = Enc_Format(Enc_Text("MapMessageAttack"), Enc_Format(line, Enc_Adjective(encNation)));
		if (encNation == ENC_PIRATE) { text = Enc_Text("Mapparammessage4"); }
	}
	Enc_Node("MSGSCROLL", ENC_SCROLL_L + e, ENC_SCROLL_T + t, ENC_SCROLL_R + e, ENC_SCROLL_B + t);
	Enc_Node("EDITMESSAGES", 240 + e, 190 + t, 550 + e, 340 + t);
	Enc_SetText("EDITMESSAGES", text);
	if (type == 3 || type == 4 || encPlain)
	{
		Enc_Node("LB_OK", 350 + e, 371 + t, 450 + e, 401 + t);
	}
	else
	{
		Enc_Node("LB_YES", 265 + e, 365 + t, 385 + e, 395 + t);
		Enc_Node("LB_NO", 415 + e, 365 + t, 535 + e, 395 + t);
	}
	if (TownAuto >= 24) { PostEvent("Enc_Auto", ENC_AUTO_MS); }
}

void Enc_Node(string node, int left, int top, int right, int bottom)
{
	Map_MoveNode(node, left, top, right, bottom);
}

// the text of a node: replaces the string of the group 0, the first call adds it
void Enc_SetText(string node, string text)
{
	string key = "enc_" + node;
	if (CheckAttribute(&MapEncText, key))
	{
		SendMessage(&GameInterface, "lslle", MSG_INTERFACE_MSG_TO_NODE, node, 10, 0, &text);
		return;
	}
	MapEncText.(key) = "1";
	SendMessage(&GameInterface, "lsle", MSG_INTERFACE_MSG_TO_NODE, node, 0, &text);
}

// the window goes away: the scroll and the text shrink to nothing, the buttons (their text shows even at no size) go off the screen
void Enc_Hide()
{
	Enc_Node("MSGSCROLL", 0, 0, 0, 0);
	Enc_Node("EDITMESSAGES", 0, 0, 0, 0);
	Enc_Node("LB_OK", -2000, -2000, -1900, -1970);
	Enc_Node("LB_YES", -2000, -2000, -1900, -1970);
	Enc_Node("LB_NO", -2000, -2000, -1900, -1970);
	encShown = false;
}

// the buttons of the window: "Да" and "Напасть" go to the battle, "Пропустить" sails on
void Enc_Command(string node)
{
	if (!encShown) { return; }
	if (encKind == 33)
	{
		// "У вас не хватает золота!": the crew is angry, the reputation falls by 5 (ProcessButtonYes of MAP.dll, cases 0x21, 0xb)
		Enc_Hide();
		Pdm_AddReputation(-5);
		Trace("PDM map: debt, reputation " + PlayerCard.reputation);
		Enc_Show(11, Enc_Text("MapMessageReputation"));
		return;
	}
	if (encKind == 11 || encKind == 12)
	{
		Enc_Hide();
		if (TownAuto == 38 && encKind == 11) { PostEvent("Map_AutoQuit", 500); }
		if (TownAuto == 40 && encKind == 12) { PostEvent("Map_AutoQuit", 500); }
		return;
	}
	if (encPay > 0)
	{
		if (node == "LB_YES")
		{
			// enough gold - the whole sum is paid and the debt is gone, else nothing is taken and the crew goes into debt
			int pay = encPay;
			if (pay <= sti(PlayerCard.money))
			{
				PlayerCard.money = sti(PlayerCard.money) - pay;
				mapDebt = false;
				Trace("PDM map: paid " + pay);
			}
			else
			{
				mapDebt = true;
				Trace("PDM map: not enough gold for " + pay);
				Enc_Hide();
				Enc_Show(33, Enc_Text("MapMessageNotEnoughMoney"));
				return;
			}
		}
		else { Trace("PDM map: not paid"); }
		Enc_Hide();
		if (TownAuto == 28 || TownAuto == 39) { PostEvent("Map_AutoQuit", 500); }
		return;
	}
	if (node == "LB_NO")
	{
		Trace("PDM encounter: ignored");
		Enc_Hide();
		return;
	}
	if (encPlain)
	{
		Trace("PDM map: message closed");
		Enc_Hide();
		return;
	}
	if (node == "LB_OK" || node == "LB_YES") { Enc_Battle(); }
}

// TOWN_AUTO=24: the enemy of the pattern is at sea, the battle is on
void Enc_AutoQuit()
{
	Trace("PDM encounter: autotest done, enemy " + battleEnemy + " of " + encShipType + ", flees " + battleEnemyFlees + ", escorts " + battleEscorts);
	// the sea AI asks the script for the balls of the ships every frame, after ExitProgram it gets no answer and asserts
	Battle_Release();
	ExitProgram();
}

void Enc_Auto()
{
	if (!encShown) { return; }
	if (TownAuto >= 25) { Enc_Command("LB_YES"); }
	else { Enc_Command("LB_OK"); }
}

// the type of the first ship of the pattern: a random one of PdmShipTypes of the classes from u to d with the flag of the
// kind in weapon_type (1 war, 2 merchant), up to ENC_TRIES draws as the original does
string Enc_ShipType(int pattern, bool war)
{
	string pat = "p" + pattern;
	int up = sti(PdmPattern.(pat).wu);
	int down = sti(PdmPattern.(pat).wd);
	int flag = 1;
	if (!war)
	{
		up = sti(PdmPattern.(pat).mu);
		down = sti(PdmPattern.(pat).md);
		flag = 2;
	}
	int n = GetAttributesNum(&PdmShipTypes);
	string found = "";
	aref type;
	for (int i = 0; i < ENC_TRIES; i++)
	{
		type = GetAttributeN(&PdmShipTypes, rand(n - 1));
		int shipClass = sti(type.class);
		int kind = sti(type.weapon_type);
		if (shipClass < up || shipClass > down) { continue; }
		if (makeint(kind / flag) % 2 == 0) { continue; }
		found = GetAttributeName(type);
		break;
	}
	return found;
}

// the card of the captain and the ship of the battle (ours: the unnamed captain)
void Enc_MakeEnemy(string key, string typeKey, int nation)
{
	DeleteAttribute(&PdmCharacters, key);
	DeleteAttribute(&PdmShips, key);
	PdmShips.(key).type_key = typeKey;
	PdmShips.(key).name = PdmShipTypes.(typeKey).type;
	PdmShips.(key).class = PdmShipTypes.(typeKey).class;
	PdmShips.(key).crew = PdmShipTypes.(typeKey).maxcrew;
	PdmShips.(key).hull_hp = PdmShipTypes.(typeKey).hitpoint;
	PdmShips.(key).skills.soldier = "1";
	PdmShips.(key).skills.cannoneer = "1";
	PdmShips.(key).skills.sailor = "1";
	string base = BATTLE_ENEMY;
	PdmCharacters.(key).id = "Captain";
	PdmCharacters.(key).name = "Капитан";
	PdmCharacters.(key).nation = nation;
	PdmCharacters.(key).relation = "3";
	PdmCharacters.(key).kind = "2";
	PdmCharacters.(key).model = PdmCharacters.(base).model;
	PdmCharacters.(key).ship_key = key;
	PdmCharacters.(key).address.island = "";
	PdmCharacters.(key).skills.combat = "4";
	PdmCharacters.(key).skills.defence = "4";
	PdmCharacters.(key).skills.sailing = "4";
	PdmCharacters.(key).skills.accuracy = "4";
	PdmCharacters.(key).skills.reload = "4";
}

// the battle: the sea of the nearest island, the first ship of the pattern coming at the hero
void Enc_Battle()
{
	Enc_Hide();
	// ours (the original gives no source of the relation): the hero who attacks a nation becomes its enemy
	if (encNation != ENC_PIRATE && Enc_Relation(encNation) != 2)
	{
		string rel = "n" + encNation;
		PlayerCard.relations.(rel) = 2;
		Trace("PDM war: nation " + encNation + " is hostile now");
	}
	string pat = "p" + encPattern;
	bool war = sti(PdmPattern.(pat).wc) > 0;
	if (encType == 1) { war = false; }
	string typeKey = Enc_ShipType(encPattern, war);
	if (typeKey == "") { typeKey = Enc_ShipType(encPattern, !war); }
	if (typeKey == "")
	{
		Trace("PDM encounter: no ship of the pattern " + encPattern);
		return;
	}
	Enc_MakeEnemy("PdmEnc", typeKey, encNation);
	// the rest of the squadron of the pattern (ours: they only attack the hero, the victory and boarding go by the first ship)
	battleEscorts = 0;
	for (int k = 1; k < encCount && k <= BATTLE_MAX_ESCORTS; k++)
	{
		string escortType = Enc_ShipType(encPattern, war);
		if (escortType == "") { break; }
		Enc_MakeEnemy("PdmEnc" + k, escortType, encNation);
		battleEscorts = k;
	}
	encShipType = typeKey;
	Trace("PDM encounter: battle, " + typeKey + " of nation " + encNation + " near " + encIsland);
	battleEnemyFlees = encType == 1;
	Map_Fight(encIsland);
	// TOWN_AUTO=24: the battle has started, the test is done
	if (TownAuto >= 24) { PostEvent("Enc_AutoQuit", ENC_AUTO_QUIT_MS); }
}
