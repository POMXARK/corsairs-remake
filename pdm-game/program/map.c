// The world map of the original (MAP.dll): the parchment of the Caribbean, IMAGES\MAP\RUSSIAN\map_open.tga
// (1200 x 900, the islands drawn on it), seen through the window of [MainMap] of INI/map.ini; the screen is
// converted by tools/pdm_ui.py into resource\ini\interfaces\mainmap.ini. The ship of the hero sails over it
// to the island chosen in the list (Up/Down or the scroll buttons, Enter or a click to sail) and comes to
// the sea at that island (sea.c Sea_Arrive). The sea opens the map when the ship sails off its island
// (exit_r of tools/pdm_island.py) or on M.
// TOWN_AUTO=6 sails by itself from the island it left to Highrock (or from Highrock to Granda Avilia).

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

float mapX = 0.0;
float mapY = 0.0;
float mapToX = 0.0;
float mapToY = 0.0;
string mapTarget = "";
string mapFrom = "";
bool mapActive = false;
int mapIslandCount = 0;
// the keys of PdmIslands in the order of the list
object MapIslands;

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

void Map_Start(string fromIsland)
{
	Menu_InterfaceKeys();
	mapFrom = fromIsland;
	mapTarget = "";
	if (fromIsland != "" && CheckAttribute(&PdmIslands, fromIsland + ".map_cell"))
	{
		mapX = Map_IslandX(fromIsland);
		mapY = Map_IslandY(fromIsland);
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
	Map_FillIslands();
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
		SendMessage(&GameInterface, "lsle", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 0, &name);
		mapIslandCount++;
	}
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, from);
}

// the window over the map follows the ship
void Map_View()
{
	float left = mapX - MAP_VIEW_W / 2;
	float top = mapY - MAP_VIEW_H / 2;
	if (left > MAP_W - MAP_VIEW_W) { left = MAP_W - MAP_VIEW_W; }
	if (top > MAP_H - MAP_VIEW_H) { top = MAP_H - MAP_VIEW_H; }
	if (left < 0.0) { left = 0.0; }
	if (top < 0.0) { top = 0.0; }
	SendMessage(&GameInterface, "lslffff", MSG_INTERFACE_MSG_TO_NODE, "MAP", 1,
		left / MAP_TEX_W, (left + MAP_VIEW_W) / MAP_TEX_W, top / MAP_TEX_H, (top + MAP_VIEW_H) / MAP_TEX_H);
	// an int takes a float rounded down
	int x = MAP_VIEW_X + mapX - left - MAP_SHIP_W / 2;
	int y = MAP_VIEW_Y + mapY - top - MAP_SHIP_H / 2;
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
		if (d <= step)
		{
			mapX = mapToX;
			mapY = mapToY;
			Map_View();
			PostEvent("Map_Arrive", 0);
			return;
		}
		mapX = mapX + dx * step / d;
		mapY = mapY + dy * step / d;
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
	int index = SendMessage(&GameInterface, "lsl", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 11);
	if (node == "LB_ISLANDUP" && index > 0) { index--; }
	if (node == "LB_ISLANDDOWN" && index + 1 < mapIslandCount) { index++; }
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, index);
	// the button is still being pressed: the interface goes away after the event (menu.c)
	if (node == "LB_EXIT") { PostEvent("Map_Exit", 0); }
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
	Sea_Arrive(island);
}

// "Выход": back to the sea of the island the ship left
void Map_Exit()
{
	if (!mapActive) { return; }
	Map_Release();
	Sea_Arrive(mapFrom);
}

void Map_AutoSail()
{
	string to = "Highrock";
	if (mapFrom == "Highrock") { to = "avilia"; }
	string at;
	for (int i = 0; i < mapIslandCount; i++)
	{
		at = "i" + i;
		if (MapIslands.(at) == to)
		{
			SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "ISLANDS", 1, i);
			Map_SailTo(i);
		}
	}
}
