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
string mapTarget = "";
string mapFrom = "";
bool mapActive = false;
// the window over the map on this screen: wider than map_rect on a wide window (Map_Layout)
int mapViewX = MAP_VIEW_X;
int mapViewY = MAP_VIEW_Y;
int mapViewW = MAP_VIEW_W;
int mapViewH = MAP_VIEW_H;
// the left top of the map picture in the window (Map_View)
float mapLeft = 0.0;
float mapTop = 0.0;
int mapIslandCount = 0;
// the keys of PdmIslands in the order of the list
object MapIslands;
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
	mapTarget = "";
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
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\mainmap.ini");
	Map_Layout();
	Map_FillIslands();
	Map_FogReplay();
	Map_Fog();
	Map_View();
	Sound_StopLocation();
	Sound_Music("map");
	mapActive = true;
	PostEvent("Map_Tick", MAP_TICK_MS);
	Trace("PDM map: from " + fromIsland + " at " + mapX + ", " + mapY);
	if (TownAuto == 6) { PostEvent("Map_AutoSail", MAP_AUTO_MS); }
}

// the islands of islands_x.idf with a model at sea; the dead towns (Highrock_) stand on the living ones
void Map_FillIslands()
{
	DeleteAttribute(&MapIslands, "");
	mapIslandCount = 0;
	int n = GetAttributesNum(&PdmIslands);
	aref island;
	string key, name, at;
	int from = 0;
	for (int i = 0; i < n; i++)
	{
		island = GetAttributeN(&PdmIslands, i);
		key = GetAttributeName(island);
		if (!CheckAttribute(island, "port_x") || !CheckAttribute(island, "map_cell")) { continue; }
		if (strcut(key, strlen(key) - 1, strlen(key) - 1) == "_") { continue; }
		at = "i" + mapIslandCount;
		MapIslands.(at) = key;
		if (key == mapFrom) { from = mapIslandCount; }
		name = island.class;
		if (CheckAttribute(island, "label")) { name = island.label; }
		SendMessage(&GameInterface, "lsle", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 0, &name);
		mapIslandCount++;
	}
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, from);
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
	SendMessage(&GameInterface, "lslllll", MSG_INTERFACE_MSG_TO_NODE, "SHIP", 0, x, y, x + MAP_SHIP_W, y + MAP_SHIP_H);
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
		Trace("PDM map: fog, " + key + " found");
	}
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
	if (index < 0 || index >= mapIslandCount || !mapActive) { return; }
	string at = "i" + index;
	mapTarget = MapIslands.(at);
	mapToX = Map_IslandX(mapTarget);
	mapToY = Map_IslandY(mapTarget);
	Trace("PDM map: sail to " + mapTarget + " at " + mapToX + ", " + mapToY);
}

void Map_Tick()
{
	if (!mapActive) { return; }
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
	}
	PostEvent("Map_Tick", MAP_TICK_MS);
}

void Map_Activate()
{
	string node = GetEventData();
	int index = GetEventData();
	if (node == "ISLANDS") { Map_SailTo(index); }
}

void Map_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command != "click" && command != "activate") { return; }
	if (node == "MAP") { Map_Click(); return; }
	int index = SendMessage(&GameInterface, "lsl", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 11);
	if (node == "LB_ISLANDUP" && index > 0) { index--; }
	if (node == "LB_ISLANDDOWN" && index + 1 < mapIslandCount) { index++; }
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
	for (int i = 0; i < mapIslandCount; i++)
	{
		at = "i" + i;
		key = MapIslands.(at);
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

// "Выход": back to the sea of the island the ship left
void Map_Exit()
{
	if (!mapActive) { return; }
	Map_Release();
	Sea_Arrive(mapFrom, mapX, mapY, mapAY);
}

// clicks the island on the map the way the player does: mousepos is where it is on the window
void Map_AutoSail()
{
	string to = "Highrock";
	if (mapFrom == "Highrock") { to = "avilia"; }
	GameInterface.mousepos.x = mapViewX + Map_IslandX(to) - mapLeft;
	GameInterface.mousepos.y = mapViewY + Map_IslandY(to) - mapTop;
	Map_Click();
}
