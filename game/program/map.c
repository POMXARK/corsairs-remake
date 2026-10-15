// The world map between the port and the battle: «Ласточка» sails the archipelago of the WORLDMAP
// entity (the engine demo worldmap, its make_worldmap.py builds the islands, the ships, the clouds
// and the interface). Gull Island, the Crag and Palm Key have ports (trade.c): Enter in their waters
// goes ashore. Out at sea «Ворон» comes after the brig, sooner when she carries cargo, and when he
// catches her (or Enter is pressed with him near) the sea battle begins. Storms batter the hull. The entity draws its own sea and sky, so the world's
// (world.c) leave the layers while the map is shown.
// W / S raise and lower the sails, A / D turn, the mouse turns the camera, the wheel zooms.

// shared/messages.h
#define MSG_WORLDMAP_CREATESTORM 31000
#define MSG_WORLDMAP_CREATEENC_FLW 31110
#define MSG_WORLDMAP_CREATEENC_RELEASE 31200

// the island of the port, a model name of make_worldmap.py
#define HOME_ISLAND "gull"
// «Ворон» comes this many seconds after the brig is out (and again after he is lost from sight)
#define RAVEN_DELAY 6.0
#define RAVEN_DELAY_CARGO 3.0
#define RAVEN_LIFE 60.0
#define STORM_PERIOD 45.0
// a storm takes this much of the hull every STORM_HIT_PERIOD seconds, down to STORM_HULL_MIN
#define STORM_HIT 2
#define STORM_HIT_PERIOD 5.0
#define STORM_HULL_MIN 20

object worldMap;

int inMap = 0;
float ravenTimer = RAVEN_DELAY;
float stormTimer = 20.0;
float stormHitTimer = 0.0;
string mapIsland = "";

void Map_MapControls()
{
	MapKey("WMapShipSailUp", 87, 0);
	MapKey("WMapShipSailDown", 83, 0);
	MapKey("WMapShipTurnLeft", 65, 0);
	MapKey("WMapShipTurnRight", 68, 0);
	MapKey("WMapTurnH", 256, 0);
	MapKey("WMapTurnV", 257, 0);
	MapKey("WMapForward", 258, 0);
	MapKey("WMapBackward", 259, 0);
	MapKey("WMapCancel", 13, 0);
}

// A new game starts the map off the port, on open water east of Gull Island (whose waters reach
// 255 m from its centre at -430, 320): «Ворон» comes from any side and must not run into the land.
// Bow to the east, the morning of the first day.
void Map_Reset()
{
	DeleteAttribute(&worldMap, "");
	Map_Home();
	worldMap.wdmCameraY = 250.0;
	worldMap.wdmCameraAY = 0.0;
	worldMap.date.hour = 9;
	worldMap.date.min = 0;
	worldMap.date.day = 15;
	worldMap.date.month = 6;
	worldMap.date.year = 1665;
}

// a sunk brig is towed home: she sails out again where a new game starts
void Map_Home()
{
	worldMap.playerShipX = -150.0;
	worldMap.playerShipZ = 220.0;
	worldMap.playerShipAY = PI / 2.0;
}

void Map_Enter()
{
	inMap = 1;
	World_ShowSea(0);
	World_Ambient(0);
	World_Music("music\calm.wav");
	if (!CheckAttribute(&worldMap, "playerShipX")) { Map_Reset(); }
	// the encounters of the last visit would come back with the entity and catch the brig at once
	DeleteAttribute(&worldMap, "encounters");
	DeleteAttribute(&worldMap, "autopilot");
	worldMap.playerShipActionRadius = 20.0;
	worldMap.enemyshipViewDistMin = 300.0;
	worldMap.enemyshipViewDistMax = 500.0;
	worldMap.enemyshipDistKill = 800.0;
	worldMap.enemyshipBrnDistMin = 250.0;
	worldMap.enemyshipBrnDistMax = 400.0;
	worldMap.stormViewDistMin = 300.0;
	worldMap.stormViewDistMax = 500.0;
	worldMap.stormDistKill = 900.0;
	worldMap.stormBrnDistMin = 300.0;
	worldMap.stormBrnDistMax = 450.0;
	worldMap.stormZone = 90.0;
	// a game hour passes in two seconds of the map
	worldMap.date.hourPerSec = 0.5;
	worldMap.date.font = "wdm_date";
	// the date under the clock: "15 июня 1665"
	worldMap.date.monthnames.m01 = "января";
	worldMap.date.monthnames.m02 = "февраля";
	worldMap.date.monthnames.m03 = "марта";
	worldMap.date.monthnames.m04 = "апреля";
	worldMap.date.monthnames.m05 = "мая";
	worldMap.date.monthnames.m06 = "июня";
	worldMap.date.monthnames.m07 = "июля";
	worldMap.date.monthnames.m08 = "августа";
	worldMap.date.monthnames.m09 = "сентября";
	worldMap.date.monthnames.m10 = "октября";
	worldMap.date.monthnames.m11 = "ноября";
	worldMap.date.monthnames.m12 = "декабря";
	Map_Label("gull", "Остров Чаек");
	Map_Label("crag", "Утёс");
	Map_Label("palm", "Пальмовый");
	Map_Label("reef", "Риф");
	CreateEntity(&worldMap, "worldmap");

	SetEventHandler("WorldMap_EncounterCreate", "Map_EncounterCreate", 0);
	SetEventHandler("WorldMap_ShipEncounter", "Map_ShipEncounter", 0);
	SetEventHandler("WorldMap_PlayerInStorm", "Map_PlayerInStorm", 0);
	SetEventHandler("ExitFromWorldMap", "Map_Exit", 0);
	SetEventHandler("WorldMap_GetMoral", "Map_GetMorale", 0);
	SetEventHandler("WorldMap_GetFood", "Map_GetFood", 0);
	SetEventHandler("WorldMap_GetRum", "Map_GetRum", 0);

	ravenTimer = RAVEN_DELAY;
	if (Cargo_Total() > 0) { ravenTimer = RAVEN_DELAY_CARGO; }
	stormHitTimer = 0.0;
	mapIsland = "";
	if (lastBattle == "win") { Log("Курс на Остров Чаек: Том ждёт с наградой. Enter у острова — в порт"); }
	else { Log("В море. W/S — паруса, A/D — поворот, Enter у острова с портом — в порт"); }
	Log("Корпус " + shipHull + "%, команда " + shipCrew + ", в трюме: " + Cargo_List());
	Trace("MAP: scene loaded");
}

void Map_Leave()
{
	inMap = 0;
	DelEventHandler("WorldMap_EncounterCreate", "Map_EncounterCreate");
	DelEventHandler("WorldMap_ShipEncounter", "Map_ShipEncounter");
	DelEventHandler("WorldMap_PlayerInStorm", "Map_PlayerInStorm");
	DelEventHandler("ExitFromWorldMap", "Map_Exit");
	DelEventHandler("WorldMap_GetMoral", "Map_GetMorale");
	DelEventHandler("WorldMap_GetFood", "Map_GetFood");
	DelEventHandler("WorldMap_GetRum", "Map_GetRum");
	DeleteClass(&worldMap);
	World_ShowSea(1);
	Trace("MAP: left");
}

void Map_Label(string id, string text)
{
	string attr = "labels." + id;
	worldMap.(attr).id = id;
	worldMap.(attr).locator = id;
	worldMap.(attr).text = text;
	worldMap.(attr).font = "wdm_label";
	// over the camera, or the name is not drawn
	worldMap.(attr).heightView = 400.0;
}

// "Воды Утёса": the names in the genitive
string Map_Waters(string id)
{
	if (id == "gull") { return "Воды Острова Чаек"; }
	if (id == "crag") { return "Воды Утёса"; }
	if (id == "palm") { return "Воды Пальмового"; }
	if (id == "reef") { return "Воды Рифа"; }
	return "Воды острова";
}

// every second: the time since the last call and where the brig is
void Map_EncounterCreate()
{
	float dltTime = GetEventData();
	float x = GetEventData();
	float z = GetEventData();
	float ay = GetEventData();
	if (!inMap) { return; }

	string island = worldMap.island;
	if (island != mapIsland)
	{
		if (Trade_Market(island) >= 0) { Log(Map_Waters(island) + ". Enter — в порт"); }
		else
		{
			if (island != "") { Log(Map_Waters(island) + ". Порта здесь нет"); }
		}
		mapIsland = island;
	}
	if (stormHitTimer > 0.0) { stormHitTimer = stormHitTimer - dltTime; }

	stormTimer = stormTimer - dltTime;
	if (stormTimer <= 0.0)
	{
		stormTimer = STORM_PERIOD;
		SendMessage(&worldMap, "ll", MSG_WORLDMAP_CREATESTORM, false);
		Log("Собирается шторм");
	}

	// a «Ворон» sunk and not paid for yet: the pirates keep away until Tom has paid
	if (lastBattle == "win") { return; }
	ravenTimer = ravenTimer - dltTime;
	if (ravenTimer > 0.0) { return; }
	ravenTimer = RAVEN_LIFE;
	SendMessage(&worldMap, "lsff", MSG_WORLDMAP_CREATEENC_FLW, "pirate", 0.9, RAVEN_LIFE);
	if (Cargo_Total() > 0) { Log("Чёрные паруса на горизонте: «Ворон» почуял груз"); }
	else { Log("Чёрные паруса на горизонте: «Ворон» идёт за нами"); }
	Trace("MAP: raven");
}

// «Ворон» caught the brig, or Enter was pressed with him near: the sea battle
void Map_ShipEncounter()
{
	float x = GetEventData();
	float z = GetEventData();
	float ay = GetEventData();
	int index = GetEventData();
	// the event comes every frame while he is alongside, and the map goes at the end of the frame
	if (!inMap) { return; }
	SendMessage(&worldMap, "l", MSG_WORLDMAP_CREATEENC_RELEASE);
	Trace("MAP: encounter at " + makeint(x) + ", " + makeint(z));
	Game_GoTo("sea");
}

void Map_PlayerInStorm()
{
	float x = GetEventData();
	float z = GetEventData();
	float ay = GetEventData();
	int index = GetEventData();
	if (!inMap || stormHitTimer > 0.0) { return; }
	stormHitTimer = STORM_HIT_PERIOD;
	if (shipHull - STORM_HIT < STORM_HULL_MIN) { Log("Шторм! Корпус держится на " + shipHull + "%"); return; }
	shipHull = shipHull - STORM_HIT;
	Log("Шторм треплет «Ласточку»: корпус " + shipHull + "%");
	Trace("MAP: storm, hull " + shipHull);
}

// Enter with no ship near
void Map_Exit()
{
	if (!inMap) { return; }
	string island = worldMap.island;
	if (Trade_Market(island) >= 0)
	{
		portIsland = island;
		Trace("MAP: to port " + island);
		Game_GoTo("port");
		return;
	}
	Log("Порты — на Острове Чаек, Утёсе и Пальмовом");
}

// the plate under the clock: morale by the crew, food by the round shot in the hold
float Map_GetMorale() { return MakeFloat(shipCrew) * 100.0 / MakeFloat(SHIP_CREW); }
float Map_GetFood() { return MakeFloat(shipBalls); }
float Map_GetRum() { return 0.0; }
