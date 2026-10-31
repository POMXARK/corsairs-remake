// The world map of the original (MAP.dll): the parchment of the Caribbean, IMAGES\MAP\RUSSIAN\map_open.tga
// (1200 x 900, the islands drawn on it), seen through the window of [MainMap] of INI/map.ini; the screen is
// converted by tools/pdm_ui.py into resource\ini\interfaces\mainmap.ini. The ship of the hero sails over it
// to the island chosen in the list (Up/Down or the scroll buttons, Enter or a click to sail) or clicked on
// the map, and comes to
// the sea at that island (sea.c Sea_Arrive). The sea opens the map when the ship sails off its island
// (exit_r of tools/pdm_island.py) or on M.
// TOWN_AUTO=6 clicks Highrock on the map (or Granda Avilia, leaving Highrock).

// the map picture and its texture of tools/pdm_ui.py (a power of two)
#define MAP_W 1200
#define MAP_H 900
#define MAP_TEX_W 2048.0
#define MAP_TEX_H 1024.0
// map_pos and map_rect of [MainMap]
#define MAP_VIEW_X 31
#define MAP_VIEW_Y 27
#define MAP_VIEW_W 587
#define MAP_VIEW_H 484
// the background is cut here, the strip MAP_BACK_TILE wide before the cut lengthens it on a wide window,
// MAP_BACK_TILES pictures of it in mainmap.ini (tools/pdm_ui.py); its texture is 768 of 1024 high (ours)
#define MAP_BACK_SPLIT 320
#define MAP_BACK_SPLIT_Y 300
#define MAP_BACK_TILE 200
#define MAP_BACK_TILES 8
#define MAP_BACK_V 0.75
// IMAGES\MAP\ship.tga
#define MAP_SHIP_W 35
#define MAP_SHIP_H 24
#define MAP_SHIP_U 0.546875
#define MAP_SHIP_V 0.75
// map_cell x,y of an island is where MAP.dll draws its flag, above the island picture (ours: measured on map_open)
#define MAP_ISLAND_DY 35.0
// pixels of the map a second (ours: Granda Avilia to Highrock in about 6 seconds)
#define MAP_SPEED 40.0
#define MAP_TICK_MS 40
#define MAP_AUTO_MS 2000
// a click on the map sails to the nearest island this many pixels of the map round it (ours)
#define MAP_CLICK_R 60.0
// one px of the map is 50 m of the sea: the scale from the original (WDM_MAP_TO_SEA_SCALE of worldmap_globals.c)
#define MAP_TO_SEA_SCALE 50.0

float mapX = 0.0;
float mapY = 0.0;
float mapToX = 0.0;
float mapToY = 0.0;
// the course of the ship on the map, it crosses the transitions (the original's worldMap.playerShipAY)
float mapAY = 0.0;
// the game date: hours from 1 January of 1601, 00:00 (the original keeps seconds, minutes, hours, day, month, year in the hero of MAP.dll);
// the start is 12 June 17:00; 1 s of real sailing is about 37 game hours (measured in the original); years of 365 days (ours)
float gameHours = 3905.0;
#define MAP_HOURS_PER_TICK 1.48
string mapDateShown = "";
// the anchor (mapparam.ini [Anchors]): the game hour it lasts to; -1 none; mapAnchorMeet - until an encounter (anchor -3)
float mapAnchorTo = -1.0;
bool mapAnchorMeet = false;
bool mapAnchorListed = false;
#define MAP_SUNRISE 6
#define MAP_SUNSET 18
string mapTarget = "";
string mapFrom = "";
bool mapActive = false;
// the window over the map on this screen: wider than map_rect on a wide window (Map_Layout)
int mapViewX = MAP_VIEW_X;
int mapViewY = MAP_VIEW_Y;
int mapViewW = MAP_VIEW_W;
int mapViewH = MAP_VIEW_H;
// how far the 800 x 600 rect moved in on a wider or a higher window: the window of the encounter is placed by it (encounter.c)
int mapEdge = 0;
int mapTopEdge = 0;
// the left top of the map picture in the window (Map_View)
float mapLeft = 0.0;
float mapTop = 0.0;
// the player has scrolled the map with the mouse at the edge of the window: the view stays where it was put and does not follow the ship
bool mapManual = false;
// the cursor of the screen: 0 the flame arrow, 1..8 the arrows of the edges (up, up-right, ... up-left); -1 not set yet
int mapPointer = -1;
#define MSG_INTERFACE_SET_MOUSE_POINTER 45063
#define MAP_EDGE_PX 10
#define MAP_SCROLL_PX 4
// Shift (the original: twice) or the left button (ours: four times) held speeds the scroll up; 1 = normal
int mapFast = 1;
bool mapShiftDown = false;
bool mapLmbDown = false;
int mapIslandCount = 0;
// the keys of PdmIslands in the order of the list
object MapIslands;
bool mapNote;           // the note "якорь брошен" is up (it needs no answer, the ship stands)
bool mapDebt = false;   // the crew was not paid for lack of gold (MAP.dll +0x167c48): the weekly reminder comes
int mapHour = -1;       // the hour of the day at the last step of the sail, -1 before the first one
int mapWeek = -1;       // the week of the month last seen (day / 7), -1 before the first look
int mapPayMonth = -1;   // the month the crew was last asked to be paid in
string mapLastIsland;
object MapList;
int mapListCount = 0;
// The fog of MAP.dll: the closed chart (map_close.tga, fogTexture of MAP) covers the map, and the stamps of
// ShowCell burn it away: mask_black (65 px, alpha up to 124, adding up) at every point of a 16 px grid the
// ship passes, once each, and mask_black_island (140 px) on an island found in the 3 x 3 cells of 60 px round
// the ship (CheckCell, OpenIsland). A new game starts all closed (IMAGES\MAP\map.dat is zero).
// MapFog keeps what is open for the game: route.<point>.x, y and island.<key>.
#define MAP_FOG_GRID 16
#define MAP_FOG_CELL 60
#define MAP_FOG_ROUTE 0
#define MAP_FOG_ISLAND 1
object MapFog;

// x, y of the island on the map picture
float Map_IslandX(string islandKey)
{
	string cell = PdmIslands.(islandKey).map_cell;
	int a = findSubStr(cell, ",", 0);
	int b = findSubStr(cell, ",", a + 1);
	return stf(strcut(cell, a + 1, b - 1));
}

float Map_IslandY(string islandKey)
{
	string cell = PdmIslands.(islandKey).map_cell;
	int a = findSubStr(cell, ",", 0);
	int b = findSubStr(cell, ",", a + 1);
	return stf(strcut(cell, b + 1, strlen(cell) - 1)) + MAP_ISLAND_DY;
}

void Map_Start(string fromIsland, float atX, float atY, float ay)
{
	Menu_InterfaceKeys();
	mapFrom = fromIsland;
	mapLastIsland = fromIsland;
	mapPayMonth = -1;
	mapWeek = -1;
	mapHour = -1;
	mapDebt = false;
	// the test of the pay (28) starts a few hours before the end of June
	if (TownAuto == 28) { gameHours = 3905.0 + 400.0; PlayerCard.money = 1000; }
	// the test of the week (37) starts a few hours before the 8th of January
	if (TownAuto == 37 || TownAuto == 39) { gameHours = 164.0; }
	// the test of the debt (38): no gold at the end of the month; of the weekly pay (39): in debt, gold enough
	if (TownAuto == 38) { gameHours = 3905.0 + 400.0; PlayerCard.money = 10; }
	if (TownAuto == 39) { PlayerCard.money = 1000; mapDebt = true; }
	// the test of the mutiny (40): a hated captain, the step of the map ends in the message
	if (TownAuto == 40) { PlayerCard.reputation = -35; encForce = 1; }
	// the test of the storm (42): the hour is about to become 15
	if (TownAuto == 42) { gameHours = 3901.0; }
	mapTarget = "";
	encShown = false;
	mapAnchorTo = -1.0;
	mapAnchorMeet = false;
	mapAnchorListed = false;
	encAcc = 0;
	DeleteAttribute(&MapEncText, "");
	if (TownAuto >= 24 && TownAuto < 27) { encForce = 1; }
	if (TownAuto == 34 || TownAuto == 36) { encForce = 1; }
	if (TownAuto == 34) { PlayerCard.relations.n0 = 2; }
	if (fromIsland != "" && CheckAttribute(&PdmIslands, fromIsland + ".map_cell"))
	{
		mapX = atX;
		mapY = atY;
		// the route crosses the transition as is (playerShipAY of the original)
		mapAY = ay;
	}
	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);
	SetEventHandler("ievnt_command", "Map_Command", 0);
	SetEventHandler("FormatedTextActivate", "Map_Activate", 0);
	SetEventHandler("Map_Tick", "Map_Tick", 0);
	SetEventHandler("Map_Arrive", "Map_Arrive", 0);
	SetEventHandler("Map_Exit", "Map_Exit", 0);
	SetEventHandler("Map_AutoSail", "Map_AutoSail", 0);
	SetEventHandler("Map_AutoQuit", "Map_AutoQuit", 0);
	SetEventHandler("Map_AutoScroll", "Map_AutoScroll", 0);
	SetEventHandler("Control Activation", "Map_KeyDown", 0);
	SetEventHandler("Control Deactivation", "Map_KeyUp", 0);
	mapShiftDown = false;
	mapLmbDown = false;
	mapFast = 1;
	SetEventHandler("Map_AutoAnchor", "Map_AutoAnchor", 0);
	SetEventHandler("Enc_Auto", "Enc_Auto", 0);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\mainmap.ini");
	Map_Layout();
	Map_FillIslands();
	Map_FillAnchors();
	Map_FogReplay();
	Map_Fog();
	mapManual = false;
	mapPointer = -1;
	Map_Pointer(0);
	Map_View();
	Sound_StopLocation();
	Sound_Music("map");
	mapActive = true;
	PostEvent("Map_Tick", MAP_TICK_MS);
	Trace("PDM map: from " + fromIsland + " at " + mapX + ", " + mapY);
	if (TownAuto == 6 || TownAuto == 28 || TownAuto == 37 || TownAuto == 38 || TownAuto == 39 || TownAuto == 40 || TownAuto == 42) { PostEvent("Map_AutoSail", MAP_AUTO_MS); }
	if (TownAuto == 27) { PostEvent("Map_AutoAnchor", MAP_AUTO_MS); }
	if (TownAuto == 30 || TownAuto == 32 || TownAuto == 33) { PostEvent("Map_AutoScroll", MAP_AUTO_MS); }
}

// the islands of islands_x.idf with a model at sea; the dead towns (Highrock_) stand on the living ones
// MapIslands is all of them (the encounters count the closeness to every island), MapList the ones found, in the order of finding:
// MAP.dll shows in the list only the islands it has opened (OpenIsland)
void Map_FillIslands()
{
	DeleteAttribute(&MapIslands, "");
	DeleteAttribute(&MapList, "");
	mapIslandCount = 0;
	mapListCount = 0;
	int n = GetAttributesNum(&PdmIslands);
	aref island;
	string key, at;
	for (int i = 0; i < n; i++)
	{
		island = GetAttributeN(&PdmIslands, i);
		key = GetAttributeName(island);
		if (!CheckAttribute(island, "port_x") || !CheckAttribute(island, "map_cell")) { continue; }
		if (strcut(key, strlen(key) - 1, strlen(key) - 1) == "_") { continue; }
		at = "i" + mapIslandCount;
		MapIslands.(at) = key;
		mapIslandCount++;
	}
	// a new game: MAP.dll opens avilia, Belflor and Highrock at the start (first_start of mapparam.ini)
	if (!CheckAttribute(&MapFog, "island"))
	{
		MapFog.island.avilia = 1;
		MapFog.island.Belflor = 1;
		MapFog.island.Highrock = 1;
	}
	// the test of the scroller of the list (TOWN_AUTO=33): every island is found, the list is longer than its window
	if (TownAuto == 33)
	{
		for (int k = 0; k < mapIslandCount; k++) { at = "i" + k; key = MapIslands.(at); MapFog.island.(key) = 1; }
	}
	aref found;
	makearef(found, MapFog.island);
	n = GetAttributesNum(found);
	int from = 0;
	for (int j = 0; j < n; j++)
	{
		key = GetAttributeName(GetAttributeN(found, j));
		if (!CheckAttribute(&PdmIslands, key + ".map_cell")) { continue; }
		if (key == mapFrom) { from = mapListCount; }
		Map_ListAdd(key);
	}
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, from);
	Trace("PDM map: list of " + mapListCount + " islands");
}

// an island found goes to the end of the list of the map
void Map_ListAdd(string key)
{
	string at = "l" + mapListCount;
	MapList.(at) = key;
	mapListCount++;
	string name = PdmIslands.(key).class;
	if (CheckAttribute(&PdmIslands, key + ".label")) { name = PdmIslands.(key).label; }
	SendMessage(&GameInterface, "lsle", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 0, &name);
}

// The screen of the original is 4:3. On a wider window (ScreenLeft of the xinterface: how far its 800 x 600
// rect moved in) the background is cut at MAP_BACK_SPLIT and its halves go to the edges; the strip before the
// cut repeats between them (BACK_TILE<n> of tools/pdm_ui.py), so the frame of the map grows longer and nothing
// is stretched. On a narrower one (5:4, ScreenTop) the same is done up and down. The window over the map grows
// with the frame and shows more of the parchment, the panel with the list keeps to the right top corner (ours).
// The messages take positions on the whole window, not in the 800 x 600 rect.
void Map_Layout()
{
	int edge = 0;
	int top = 0;
	if (CheckAttribute(&GameInterface, "ScreenLeft")) { edge = sti(GameInterface.ScreenLeft); }
	if (CheckAttribute(&GameInterface, "ScreenTop")) { top = sti(GameInterface.ScreenTop); }
	mapEdge = edge;
	mapTopEdge = top;
	int width = 800 + 2 * edge;
	int height = 600 + 2 * top;
	mapViewX = MAP_VIEW_X;
	mapViewY = MAP_VIEW_Y;
	mapViewW = MAP_VIEW_W + 2 * edge;
	mapViewH = MAP_VIEW_H + 2 * top;
	int i, at, w;
	string node;
	if (top > 0)
	{
		Map_BackPiece("BACKGROUND", 0, 0, 0, 0, 800, MAP_BACK_SPLIT_Y);
		Map_BackPiece("BACK_RIGHT", 0, MAP_BACK_SPLIT_Y + 2 * top, 0, MAP_BACK_SPLIT_Y, 800, 600 - MAP_BACK_SPLIT_Y);
		at = MAP_BACK_SPLIT_Y;
		for (i = 0; i < MAP_BACK_TILES; i++)
		{
			node = "BACK_TILE" + i;
			w = Map_TileSize(MAP_BACK_SPLIT_Y + 2 * top - at);
			Map_BackPiece(node, 0, at, 0, MAP_BACK_SPLIT_Y - MAP_BACK_TILE, 800, w);
			at = at + w;
		}
	}
	else
	{
		Map_BackPiece("BACKGROUND", 0, 0, 0, 0, MAP_BACK_SPLIT, 600);
		Map_BackPiece("BACK_RIGHT", MAP_BACK_SPLIT + 2 * edge, 0, MAP_BACK_SPLIT, 0, 800 - MAP_BACK_SPLIT, 600);
		at = MAP_BACK_SPLIT;
		for (i = 0; i < MAP_BACK_TILES; i++)
		{
			node = "BACK_TILE" + i;
			w = Map_TileSize(MAP_BACK_SPLIT + 2 * edge - at);
			Map_BackPiece(node, at, 0, MAP_BACK_SPLIT - MAP_BACK_TILE, 0, w, 600);
			at = at + w;
		}
	}
	SendMessage(&GameInterface, "lslllll", MSG_INTERFACE_MSG_TO_NODE, "MAP", 0, mapViewX, mapViewY, mapViewX + mapViewW, mapViewY + mapViewH);
	// -1: the position message of every node (inode.cpp), the rects of mainmap.ini moved right
	int dx = 2 * edge;
	Map_MoveNode("ISLANDS", 650 + dx, 125, 758 + dx, 386);
	Map_MoveNode("ISLSCROLL", 762 + dx, 125, 790 + dx, 386);
	Map_MoveNode("EDITTIME", 650 + dx, 515, 762 + dx, 585);
	Map_MoveNode("LB_EXIT", 657 + dx, 34, 771 + dx, 75);
	Map_MoveNode("LB_ISLANDUP", 763 + dx, 123, 784 + dx, 141);
	Map_MoveNode("LB_ISLANDDOWN", 763 + dx, 370, 784 + dx, 388);
	// a string collection moves its strings by the change of its rect, the 800 x 600 one at edge, top: by
	// edge to the right and back up to the top of the window, as the nodes above
	Map_MoveNode("TITLES", dx, 0, dx + 800, 600);
	Trace("PDM map: window " + width + " x " + height + ", the map in it " + mapViewW + " x " + mapViewH);
}

// how much of the strip still goes before the second half: whole strips, the rest, then none
int Map_TileSize(int left)
{
	if (left > MAP_BACK_TILE) { return MAP_BACK_TILE; }
	if (left < 0) { return 0; }
	return left;
}

// the piece of the background at u, v (in its 800 x 600) w x h big, put at x, y
void Map_BackPiece(string node, int x, int y, int u, int v, int w, int h)
{
	SendMessage(&GameInterface, "lslllll", MSG_INTERFACE_MSG_TO_NODE, node, 0, x, y, x + w, y + h);
	SendMessage(&GameInterface, "lslffff", MSG_INTERFACE_MSG_TO_NODE, node, 1,
		u / 800.0, (u + w) / 800.0, v * MAP_BACK_V / 600.0, (v + h) * MAP_BACK_V / 600.0);
}

void Map_MoveNode(string node, int left, int top, int right, int bottom)
{
	SendMessage(&GameInterface, "lsllllll", MSG_INTERFACE_MSG_TO_NODE, node, -1, 4, left, top, right, bottom);
}

// the window over the map follows the ship
void Map_View()
{
	float left = mapX - mapViewW / 2;
	float top = mapY - mapViewH / 2;
	if (mapManual) { left = mapLeft; top = mapTop; }
	if (left > MAP_W - mapViewW) { left = MAP_W - mapViewW; }
	if (top > MAP_H - mapViewH) { top = MAP_H - mapViewH; }
	if (left < 0.0) { left = 0.0; }
	if (top < 0.0) { top = 0.0; }
	mapLeft = left;
	mapTop = top;
	SendMessage(&GameInterface, "lslffff", MSG_INTERFACE_MSG_TO_NODE, "MAP", 1,
		left / MAP_TEX_W, (left + mapViewW) / MAP_TEX_W, top / MAP_TEX_H, (top + mapViewH) / MAP_TEX_H);
	// an int takes a float rounded down
	int x = mapViewX + mapX - left - MAP_SHIP_W / 2;
	int y = mapViewY + mapY - top - MAP_SHIP_H / 2;
	// a ship out of the window (the view is scrolled away from it) is not drawn over the frame
	if (x < mapViewX || y < mapViewY || x + MAP_SHIP_W > mapViewX + mapViewW || y + MAP_SHIP_H > mapViewY + mapViewH) { x = 0; y = 0; }
	if (x == 0 && y == 0) { SendMessage(&GameInterface, "lslllll", MSG_INTERFACE_MSG_TO_NODE, "SHIP", 0, 0, 0, 0, 0); }
	else { SendMessage(&GameInterface, "lslllll", MSG_INTERFACE_MSG_TO_NODE, "SHIP", 0, x, y, x + MAP_SHIP_W, y + MAP_SHIP_H); }
	// the picture faces right: sailing west it is mirrored
	if (mapTarget != "" && mapToX < mapX)
	{
		SendMessage(&GameInterface, "lslffff", MSG_INTERFACE_MSG_TO_NODE, "SHIP", 1, MAP_SHIP_U, 0.0, 0.0, MAP_SHIP_V);
	}
	else
	{
		SendMessage(&GameInterface, "lslffff", MSG_INTERFACE_MSG_TO_NODE, "SHIP", 1, 0.0, MAP_SHIP_U, 0.0, MAP_SHIP_V);
	}
}

// the stamps already open, burnt again into the fog of the new interface
void Map_FogReplay()
{
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_MSG_TO_NODE, "MAP", 10);
	aref root, point;
	int i, n;
	makearef(root, MapFog.route);
	n = GetAttributesNum(root);
	for (i = 0; i < n; i++)
	{
		point = GetAttributeN(root, i);
		SendMessage(&GameInterface, "lsllll", MSG_INTERFACE_MSG_TO_NODE, "MAP", 9, MAP_FOG_ROUTE, sti(point.x), sti(point.y));
	}
	int points = n;
	makearef(root, MapFog.island);
	n = GetAttributesNum(root);
	string key;
	for (i = 0; i < n; i++)
	{
		key = GetAttributeName(GetAttributeN(root, i));
		Map_FogIsland(key);
	}
	Trace("PDM map: fog, " + points + " points of the route and " + n + " islands open");
}

// the ship opens the point of the grid it is at and the islands in the cells round it
void Map_Fog()
{
	// an int takes a float rounded down
	int gx = mapX / MAP_FOG_GRID;
	int gy = mapY / MAP_FOG_GRID;
	string at = "g" + gx + "_" + gy;
	if (!CheckAttribute(&MapFog, "route." + at))
	{
		MapFog.route.(at).x = gx * MAP_FOG_GRID + MAP_FOG_GRID / 2;
		MapFog.route.(at).y = gy * MAP_FOG_GRID + MAP_FOG_GRID / 2;
		SendMessage(&GameInterface, "lsllll", MSG_INTERFACE_MSG_TO_NODE, "MAP", 9, MAP_FOG_ROUTE, sti(MapFog.route.(at).x), sti(MapFog.route.(at).y));
	}
	int cx = mapX / MAP_FOG_CELL;
	int cy = mapY / MAP_FOG_CELL;
	int ix, iy;
	string key;
	for (int i = 0; i < mapIslandCount; i++)
	{
		at = "i" + i;
		key = MapIslands.(at);
		if (CheckAttribute(&MapFog, "island." + key)) { continue; }
		ix = Map_IslandX(key) / MAP_FOG_CELL;
		iy = Map_IslandY(key) / MAP_FOG_CELL;
		if (abs(ix - cx) > 1 || abs(iy - cy) > 1) { continue; }
		MapFog.island.(key) = 1;
		Map_FogIsland(key);
		Map_ListAdd(key);
		Trace("PDM map: fog, " + key + " found");
	}
	Map_Land(cx, cy);
}

// the island in the cells round the ship changed: "Земля!" with the name and the flag of it (message 8 of MAP.dll, the sound mapisland)
// the nearest island of the 3x3 cells; the nations of the islands go as the flags of the ships (0 England, 1 pirates, 2 France, 3 Spain, 4 Libertalia), -1 none
void Map_Land(int cx, int cy)
{
	string near = "";
	int best = 100;
	string key;
	string at;
	for (int i = 0; i < mapIslandCount; i++)
	{
		at = "i" + i;
		key = MapIslands.(at);
		int dx = abs(makeint(Map_IslandX(key) / MAP_FOG_CELL) - cx);
		int dy = abs(makeint(Map_IslandY(key) / MAP_FOG_CELL) - cy);
		if (dx > 1 || dy > 1) { continue; }
		if (dx + dy < best) { best = dx + dy; near = key; }
	}
	if (near == mapLastIsland) { return; }
	mapLastIsland = near;
	if (near == "" || encShown) { return; }
	int nation = sti(PdmIslands.(near).nation);
	string name = PdmIslands.(near).label;
	string text = Enc_Format(Enc_Text("MapparamIslandNoNation"), name);
	if (nation >= 0)
	{
		string nations = "mapEngland";
		if (nation == 1) { nations = "mapPirate"; }
		if (nation == 2) { nations = "mapFrance"; }
		if (nation == 3) { nations = "mapSpain"; }
		if (nation == 4) { nations = "mapAmerica"; }
		text = Enc_Format(Enc_Format(Enc_Text("Mapparammessage8"), name), Enc_Text(nations));
	}
	Trace("PDM map: land " + near + " (" + text + ")");
	if (TownAuto == 6) { PostEvent("Map_AutoQuit", 1500); }
	Sound_Once("mapisland");
	Enc_Show(5, text);
}

// the island stamp on the island (ours: at its middle, MAP.dll puts it at the middle of its cell)
void Map_FogIsland(string key)
{
	int x = Map_IslandX(key);
	int y = Map_IslandY(key);
	SendMessage(&GameInterface, "lsllll", MSG_INTERFACE_MSG_TO_NODE, "MAP", 9, MAP_FOG_ISLAND, x, y);
}

void Map_SailTo(int index)
{
	if (index < 0 || index >= mapListCount || !mapActive) { return; }
	string at = "l" + index;
	mapTarget = MapList.(at);
	// a voyage is followed by the view again
	mapManual = false;
	mapToX = Map_IslandX(mapTarget);
	mapToY = Map_IslandY(mapTarget);
	Trace("PDM map: sail to " + mapTarget + " at " + mapToX + ", " + mapToY);
}

int Map_MonthDays(int mon)
{
	if (mon == 1) { return 28; }
	if (mon == 3 || mon == 5 || mon == 8 || mon == 10) { return 30; }
	return 31;
}

int Map_MonthIndex()
{
	int day = (makeint(gameHours) / 24) % 365;
	int mon = 0;
	while (day >= Map_MonthDays(mon)) { day = day - Map_MonthDays(mon); mon++; }
	return mon;
}

// the note without buttons (message 7 of MAP.dll): stays while the ship is at anchor, goes with weighing it
void Map_Note(string text)
{
	int e = mapEdge;
	int t = mapTopEdge;
	Enc_Node("MSGSCROLL", ENC_SCROLL_L + e, ENC_SCROLL_T + t, ENC_SCROLL_R + e, ENC_SCROLL_B + t);
	Enc_Node("EDITMESSAGES", 240 + e, 190 + t, 550 + e, 340 + t);
	Enc_SetText("EDITMESSAGES", text);
	mapNote = true;
}

void Map_NoteHide()
{
	if (!mapNote) { return; }
	mapNote = false;
	Enc_Node("MSGSCROLL", 0, 0, 0, 0);
	Enc_Node("EDITMESSAGES", 0, 0, 0, 0);
	Trace("PDM map: note hidden");
}

// the day of the month (0-based) of the game date
int Map_MonthDay()
{
	int day = (makeint(gameHours) / 24) % 365;
	int mon = 0;
	while (day >= Map_MonthDays(mon)) { day = day - Map_MonthDays(mon); mon++; }
	return day;
}

// a new week of the month (day / 7) while the month is the one seen last and no window is open: the sound mapweek
// (MAP.dll 0x10007800 region; the window of the week that the original opens after it is not made)
// the storm (message 10, the step of the sail in MAP.dll 0x10005666): when the hour of the day becomes 15, 1 in 384
// (rand % 384 == 128); the ship stops, the window only says it, OK closes it
bool Map_Storm()
{
	int hour = makeint(gameHours) % 24;
	int before = mapHour;
	mapHour = hour;
	if (hour != 15 || before == 15 || before < 0) { return false; }
	if (TownAuto != 42 && rand(383) != 128) { return false; }
	mapTarget = "";
	Map_NoteHide();
	Trace("PDM map: storm message");
	Enc_Show(10, Enc_Text("MapMessageTornado"));
	return true;
}

void Map_Week()
{
	if (mapPayMonth < 0 || Map_MonthIndex() != mapPayMonth || encShown) { return; }
	int week = Map_MonthDay() / 7;
	if (week == mapWeek) { return; }
	bool first = mapWeek < 0;
	mapWeek = week;
	if (first) { return; }
	Trace("PDM map: week " + week);
	Sound_Once("mapweek");
	if (!mapDebt || week == 0) { return; }
	if (Enc_Bunt(true))
	{
		Map_NoteHide();
		Trace("PDM map: bunt");
		Enc_Show(12, Enc_Text("MapMessageBunt"));
		return;
	}
	// in debt: a reminder with the text for the reputation of the captain; Yes pays everything at once
	int sum = Pdm_Count(&PlayerShipCard, "crew") * 5;
	Map_NoteHide();
	Trace("PDM map: week pay window " + Map_RepMessage());
	Enc_Show(32, Enc_Format(Enc_Text("MapMessageReputation" + Map_RepMessage()), "" + sum));
	encPay = sum;
}

// which of the seven texts MapMessageReputation0-6 the reminder uses (SetReputationMessage, MAP.dll 0x10008a50): the reputation
// (not below -35) moved 5 away from 0, tenths cut, within -3..3, then 3 added
int Map_RepMessage()
{
	int rep = Pdm_Count(PlayerCard, "reputation");
	if (rep < -35) { rep = -35; }
	int q = 0;
	if (rep < 0) { q = (rep - 5) / 10; }
	else { q = (rep + 5) / 10; }
	if (q < -3) { q = -3; }
	if (q > 3) { q = 3; }
	return q + 3;
}

// the end of the month: the crew wants its pay (message 6; ours: 5 per man of the crew, MAP.dll sums it up from fields not decoded)
void Map_Pay()
{
	int mon = Map_MonthIndex();
	if (mapPayMonth < 0) { mapPayMonth = mon; return; }
	if (mon == mapPayMonth) { return; }
	mapPayMonth = mon;
	int sum = Pdm_Count(&PlayerShipCard, "crew") * 5;
	if (sum <= 0 || encShown) { return; }
	Map_NoteHide();
	Trace("PDM map: pay " + sum);
	Sound_Once("mapevent2");
	Enc_Show(6, Enc_Format(Enc_Text("Mapparammessage6"), "" + sum));
	encPay = sum;
}

// the date of a record of the journal, as CORE.dll writes it into english.qst ("%s %d, %d, %d.%d": the English month, day, year,
// hour and minutes, both without a leading zero: "June 12, 1601, 17.0")
string Map_RecordDate(int total)
{
	int day = (total / 24) % 365;
	int mon = 0;
	while (day >= Map_MonthDays(mon)) { day = day - Map_MonthDays(mon); mon++; }
	string months = "January,February,March,April,May,June,July,August,September,October,November,December";
	int from = 0;
	for (int i = 0; i < mon; i++) { from = findSubStr(months, ",", from) + 1; }
	int to = findSubStr(months, ",", from);
	if (to < 0) { to = strlen(months); }
	return strcut(months, from, to - 1) + " " + (day + 1) + ", " + (1601 + total / 8760) + ", " + (total % 24) + ".0";
}

string Map_DateText(bool withTime)
{
	int total = makeint(gameHours);
	int day = (total / 24) % 365;
	int hour = total % 24;
	int mon = 0;
	while (day >= Map_MonthDays(mon)) { day = day - Map_MonthDays(mon); mon++; }
	string months = Enc_Text("months");
	int from = 0;
	for (int i = 0; i < mon; i++) { from = findSubStr(months, ",", from) + 1; }
	int to = findSubStr(months, ",", from);
	if (to < 0) { to = strlen(months); }
	string text = (day + 1) + " " + strcut(months, from, to - 1);
	if (withTime)
	{
		int h12 = hour % 12;
		if (h12 == 0) { h12 = 12; }
		string ampm = "am";
		if (hour >= 12) { ampm = "pm"; }
		string mins = "00";
		text = text + "\n" + h12 + ":" + mins + " " + ampm;
	}
	return text;
}

// the rows of the anchors (the six of [Anchors]) while the ship stands, nothing while it sails or waits at anchor
void Map_ShowAnchors()
{
	bool want = false;
	if (mapTarget == "" && mapAnchorTo < 0.0 && mapAnchorMeet == false && encShown == false) { want = true; }
	if (want == mapAnchorListed) { return; }
	mapAnchorListed = want;
	if (!want) { Map_MoveNode("EDITANCHOR", 0, 0, 0, 0); return; }
	Map_MoveNode("EDITANCHOR", 650 + 2 * mapEdge, 428, 778 + 2 * mapEdge, 512);
}

// the six rows of the list of anchors, once: the node is moved in and out of sight
void Map_FillAnchors()
{
	string keys = "Untilsunrise,Untilsunset,Oneday,Twodays,Threedays,Untilencounter";
	int from = 0;
	int to;
	for (int i = 0; i < 6; i++)
	{
		to = findSubStr(keys, ",", from);
		if (to < 0) { to = strlen(keys); }
		string name = Enc_Text("Mapparam" + strcut(keys, from, to - 1));
		SendMessage(&GameInterface, "lsle", MSG_INTERFACE_MSG_TO_NODE, "EDITANCHOR", 0, &name);
		from = to + 1;
	}
}

// the anchor n of the list: the hours it lasts to (days of 24 h; sunrise and sunset at 6 and 18 are ours, not measured)
void Map_Anchor(int n)
{
	if (mapTarget != "" || mapAnchorTo >= 0.0 || mapAnchorMeet) { return; }
	int hour = makeint(gameHours) % 24;
	float day0 = gameHours - hour;
	if (n == 0) { mapAnchorTo = day0 + MAP_SUNRISE; if (hour >= MAP_SUNRISE) { mapAnchorTo = mapAnchorTo + 24.0; } }
	if (n == 1) { mapAnchorTo = day0 + MAP_SUNSET; if (hour >= MAP_SUNSET) { mapAnchorTo = mapAnchorTo + 24.0; } }
	if (n >= 2 && n <= 4) { mapAnchorTo = gameHours + 24.0 * (n - 1); }
	if (n == 5) { mapAnchorMeet = true; }
	Trace("PDM map anchor: " + n);
	Sound_Once("yakor");
	Map_ShowAnchors();
	Map_Note(Enc_Text("Mapparammessage7"));
}

void Map_ShowDate()
{
	// on the way only the date, at anchor the time as well (the clock is hidden while the ship sails)
	string text = Map_DateText(mapTarget == "");
	Enc_SetText("EDITTIME", text);
	if (text != mapDateShown) { mapDateShown = text; Trace("PDM map date: " + text); }
}

// the cursor of the map (MAP.dll): the flame arrow, and at the edge of the window, 10 px wide, an arrow to the side the map goes
void Map_Pointer(int dir)
{
	if (dir == mapPointer) { return; }
	mapPointer = dir;
	Trace("PDM map: pointer " + dir);
	string name = "map";
	if (dir > 0) { name = "map" + (dir - 1); }
	if (!CheckAttribute(&PdmScreens, "pointer." + name)) { return; }
	string line = PdmScreens.pointer.(name);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_SET_MOUSE_POINTER, line);
}

// the side of the edge the mouse is at: 1 up, 2 up-right, 3 right, 4 down-right, 5 down, 6 down-left, 7 left, 8 up-left, 0 none
// (MAP.dll, the same numbers; the window of the interface in its coordinates)
int Map_EdgeDir(float mx, float my)
{
	float w = 800 + 2 * mapEdge;
	float h = 600 + 2 * mapTopEdge;
	int dx = 0;
	int dy = 0;
	if (mx < MAP_EDGE_PX) { dx = -1; }
	if (mx > w - MAP_EDGE_PX) { dx = 1; }
	if (my < MAP_EDGE_PX) { dy = -1; }
	if (my > h - MAP_EDGE_PX) { dy = 1; }
	if (dx == 0 && dy == -1) { return 1; }
	if (dx == 1 && dy == -1) { return 2; }
	if (dx == 1 && dy == 0) { return 3; }
	if (dx == 1 && dy == 1) { return 4; }
	if (dx == 0 && dy == 1) { return 5; }
	if (dx == -1 && dy == 1) { return 6; }
	if (dx == -1 && dy == 0) { return 7; }
	if (dx == -1 && dy == -1) { return 8; }
	return 0;
}

// the mouse at the edge of the window scrolls the map, MAP_SCROLL_PX per tick (the original: 1 px per 10 ms), up to its edges
void Map_Scroll()
{
	if (!CheckAttribute(&GameInterface, "mousepos.x")) { return; }
	int dir = Map_EdgeDir(stf(GameInterface.mousepos.x), stf(GameInterface.mousepos.y));
	Map_Pointer(dir);
	Map_ScrollDir(dir);
}

void Map_SetFast()
{
	mapFast = 1;
	if (mapShiftDown) { mapFast = 2; }
	if (mapLmbDown) { mapFast = 4; }
}

void Map_KeyDown()
{
	string control = GetEventData();
	if (control == "Map_Shift") { mapShiftDown = true; }
	if (control == "Map_Lmb") { mapLmbDown = true; }
	Map_SetFast();
}

void Map_KeyUp()
{
	string control = GetEventData();
	if (control == "Map_Shift") { mapShiftDown = false; }
	if (control == "Map_Lmb") { mapLmbDown = false; }
	Map_SetFast();
}

void Map_ScrollDir(int dir)
{
	float px = MAP_SCROLL_PX * mapFast;
	if (dir == 0) { return; }
	float dx = 0.0;
	float dy = 0.0;
	if (dir == 2 || dir == 3 || dir == 4) { dx = px; }
	if (dir == 6 || dir == 7 || dir == 8) { dx = -px; }
	if (dir == 1 || dir == 2 || dir == 8) { dy = -px; }
	if (dir == 4 || dir == 5 || dir == 6) { dy = px; }
	float left = mapLeft + dx;
	float top = mapTop + dy;
	if (left > MAP_W - mapViewW) { left = MAP_W - mapViewW; }
	if (top > MAP_H - mapViewH) { top = MAP_H - mapViewH; }
	if (left < 0.0) { left = 0.0; }
	if (top < 0.0) { top = 0.0; }
	if (left == mapLeft && top == mapTop) { return; }
	mapManual = true;
	mapLeft = left;
	mapTop = top;
	Map_View();
}

// the test of the scroll: the mouse cannot be moved by the script, so the edge is given directly (the left edge, then the upper one)
int mapAutoScrolls = 0;
void Map_AutoScroll()
{
	if (!mapActive) { return; }
	float l0 = mapLeft;
	float t0 = mapTop;
	// the keys cannot be pressed by the script: the held Shift is given directly (TOWN_AUTO=32)
	if (TownAuto == 32) { mapShiftDown = true; Map_SetFast(); }
	Map_Pointer(7);
	Map_ScrollDir(7);
	Map_ScrollDir(1);
	mapAutoScrolls++;
	if (mapAutoScrolls < 40) { PostEvent("Map_AutoScroll", MAP_TICK_MS); return; }
	Trace("PDM map: scrolled " + (mapLeft - l0) + " " + (mapTop - t0) + " manual " + mapManual + " fast " + mapFast);
	PostEvent("Map_AutoQuit", 1500);
}

void Map_Tick()
{
	if (!mapActive) { return; }
	if (!encShown) { Map_Scroll(); }
	// the window of an encounter stops the ship until it is answered (encounter.c)
	if (encShown) { mapAnchorTo = -1.0; mapAnchorMeet = false; mapNote = false; Map_ShowAnchors(); PostEvent("Map_Tick", MAP_TICK_MS); return; }
	if (encForce == 1) { Enc_Tick(MAP_TICK_MS); }
	if (mapTarget != "")
	{
		float dx = mapToX - mapX;
		float dy = mapToY - mapY;
		float d = sqrt(dx * dx + dy * dy);
		float step = MAP_SPEED * MAP_TICK_MS / 1000.0;
		// the ship reaches the edge of the island and not its flag (in the original the same: wdmMoveShips of worldmap.c moves
		// ships to islands by their exit_r), exit_r from the data is in meters: 50 of them to one px of the map
		// and the flag stands at the middle of an island (islands_loader.c sets worldMap.z of it by the island cell),
		// so that the ship goes to sea from the edge and not from the point of the flag
		float edge = step;
		if (CheckAttribute(&PdmIslands, mapTarget + ".exit_r")) { edge = stf(PdmIslands.(mapTarget).exit_r) / MAP_TO_SEA_SCALE; }
		if (d <= edge)
		{
			mapAY = atan2(dx, dy);
			// the ship keeps the point where it arrived at the edge: no more it is pulled to the flag
			Map_Fog();
			Map_View();
			PostEvent("Map_Arrive", 0);
			return;
		}
		mapAY = atan2(dx, dy);
		mapX = mapX + dx * step / d;
		mapY = mapY + dy * step / d;
		Map_Fog();
		Map_View();
		gameHours = gameHours + MAP_HOURS_PER_TICK;
		if (Map_Storm()) { PostEvent("Map_Tick", MAP_TICK_MS); return; }
		// the map tests (6) sail without the random sails of the sea: the window of one would hide what they check
		if (TownAuto != 6 && TownAuto != 28) { Enc_Tick(MAP_TICK_MS); }
	}
	else if (mapAnchorTo >= 0.0 || mapAnchorMeet)
	{
		// the time runs at anchor as on the way, the sails of the sea can meet the ship
		gameHours = gameHours + MAP_HOURS_PER_TICK;
		if (mapAnchorTo >= 0.0 && gameHours >= mapAnchorTo)
		{
			gameHours = mapAnchorTo;
			mapAnchorTo = -1.0;
			Map_NoteHide();
			Trace("PDM map anchor: weighed");
			if (TownAuto == 27) { PostEvent("Map_AutoQuit", 500); }
		}
		else { Enc_Tick(MAP_TICK_MS); }
	}
	Map_Pay();
	Map_Week();
	Map_ShowAnchors();
	Map_ShowDate();
	PostEvent("Map_Tick", MAP_TICK_MS);
}

void Map_Activate()
{
	string node = GetEventData();
	int index = GetEventData();
	if (node == "ISLANDS") { Map_SailTo(index); }
	if (node == "EDITANCHOR") { Map_Anchor(index); }
}

void Map_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command != "click" && command != "activate") { return; }
	if (node == "LB_OK" || node == "LB_YES" || node == "LB_NO") { Enc_Command(node); return; }
	if (encShown) { return; }
	if (node == "MAP") { Map_Click(); return; }
	int index = SendMessage(&GameInterface, "lsl", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 11);
	if (node == "LB_ISLANDUP" && index > 0) { index--; }
	if (node == "LB_ISLANDDOWN" && index + 1 < mapListCount) { index++; }
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, index);
	// the button is still being pressed: the interface goes away after the event (menu.c)
	if (node == "LB_EXIT") { PostEvent("Map_Exit", 0); }
}

// the island nearest to the mouse on the map, within MAP_CLICK_R; mousepos of the xinterface is on the
// whole window, like the positions of the nodes
void Map_Click()
{
	if (!CheckAttribute(&GameInterface, "mousepos.x")) { return; }
	float x = stf(GameInterface.mousepos.x) - mapViewX + mapLeft;
	float y = stf(GameInterface.mousepos.y) - mapViewY + mapTop;
	float best = MAP_CLICK_R * MAP_CLICK_R;
	int index = -1;
	string at, key;
	float dx, dy;
	for (int i = 0; i < mapListCount; i++)
	{
		at = "l" + i;
		key = MapList.(at);
		dx = Map_IslandX(key) - x;
		dy = Map_IslandY(key) - y;
		if (dx * dx + dy * dy < best) { best = dx * dx + dy * dy; index = i; }
	}
	Trace("PDM map: click at " + x + ", " + y + ", island " + index);
	if (index < 0) { return; }
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, index);
	Map_SailTo(index);
}

void Map_Release()
{
	mapActive = false;
	DelEventHandler("ievnt_command", "Map_Command");
	DelEventHandler("FormatedTextActivate", "Map_Activate");
	DelEventHandler("Map_Tick", "Map_Tick");
	DelEventHandler("Map_Arrive", "Map_Arrive");
	DelEventHandler("Map_Exit", "Map_Exit");
	DelEventHandler("Map_AutoSail", "Map_AutoSail");
	DelEventHandler("Map_AutoQuit", "Map_AutoQuit");
	DelEventHandler("Map_AutoScroll", "Map_AutoScroll");
	DelEventHandler("Control Activation", "Map_KeyDown");
	DelEventHandler("Control Deactivation", "Map_KeyUp");
	DelEventHandler("Map_AutoAnchor", "Map_AutoAnchor");
	DelEventHandler("Enc_Auto", "Enc_Auto");
	SendMessage(&GameInterface, "l", MSG_INTERFACE_RELEASE);
	DeleteClass(&GameInterface);
}

void Map_Arrive()
{
	if (!mapActive) { return; }
	string island = mapTarget;
	Map_Release();
	Trace("PDM map: arrived at " + island);
	Sea_Arrive(island, mapX, mapY, mapAY);
}

// an encounter that is fought: the sea of the island nearest to the place, the enemy of the pattern (encounter.c, battle.c)
void Map_Fight(string island)
{
	if (!mapActive) { return; }
	Map_Release();
	Trace("PDM map: encounter, battle near " + island);
	battleEncounter = true;
	SetEventHandler("Enc_AutoQuit", "Enc_AutoQuit", 0);
	seaBattle = true;
	Sea_Arrive(island, mapX, mapY, mapAY);
}

// "Выход": back to the sea of the island the ship left
void Map_Exit()
{
	if (!mapActive) { return; }
	Map_Release();
	Sea_Arrive(mapFrom, mapX, mapY, mapAY);
}

// clicks the island on the map the way the player does: mousepos is where it is on the window
// TOWN_AUTO=27: the second anchor of the list ("until sunset"), then "on a day"
void Map_AutoAnchor()
{
	if (mapAnchorTo < 0.0 && !mapAnchorMeet) { Map_Anchor(2); }
	else { PostEvent("Map_AutoAnchor", MAP_AUTO_MS); }
}

// the tests 27 and 28 have said what they check: the game ends, so that the run does not wait for the timeout
void Map_AutoQuit()
{
	Battle_Release();
	ExitProgram();
}

void Map_AutoSail()
{
	string to = "Highrock";
	if (mapFrom == "Highrock") { to = "avilia"; }
	GameInterface.mousepos.x = mapViewX + Map_IslandX(to) - mapLeft;
	GameInterface.mousepos.y = mapViewY + Map_IslandY(to) - mapTop;
	Map_Click();
}
