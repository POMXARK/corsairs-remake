// The sea of the original world: the weather and the sea of the engine demos, the ship of the hero
// built from its type in WORLDS\Ships.idf (the hull is models\ships\<filename>, assembled by
// tools/pdm_ship.py from DESC\<filename>.def). A/D turn, W/S sails, the mouse turns the camera,
// Tab opens the commands of the toolbar (hud.c): to the land at the harbour, the map, the time.

// shared/layers.h: mirrored into the sea reflection (sky in the first, ships in the second)
#define SEA_REFLECTION 15
#define SEA_REFLECTION2 16
// shared/layers.h: what the cannon balls and cameras trace against
#define SAILS_TRACE 19

// shared/messages.h and shared/sea_ai/script_defines.h
#define MSG_SHIP_CREATE 50300
#define MSG_ISLAND_LOAD_GEO 50100
#define AI_MESSAGE_SET_LAYERS 51015
#define AI_CAMERAS_SET_CAMERA 55001

// priorities of the ship in the execute and realize layers; the ship entity reads these globals
// by name and its sails, blots and camera are placed right after it
int iShipPriorityExecute = 2;
int iShipPriorityRealize = 31;

object Weather;
object Sky;
object Sea;
object Sail;
object Rope;
object Vant;
object VantL;
object Flag;
// the flag of a ship: the column and the row in the flag atlas of pdm_ship.py (a column per nation)
int SeaFlagTexture[2];
object SeaCameras;
// the island of the town the ship sails from (tools/pdm_island.py) and the entity that pushes the ships
// off its shore; touch registers the ships created after it
object Island;
object Touch;
// touch pushes a ship back where the depth map is this shallow under its hull (the island demo)
#define SEA_COLLISION_DEPTH -4.0
object ShipCamera;
#define SEA_MAX_SHIPS 48
// the most sails with the coat of arms on one ship
#define SEA_MAX_EMBLEMS 6
// the characters the ship entities live on; the index in the array is their .index, by which the
// ship and sail entities ask the script about them. 0 is the hero
object SeaShips[SEA_MAX_SHIPS];
// their ship types: the engine reads the parameters and the model name, ships\<Name>\<Name>.gm
object SeaShipTypes[SEA_MAX_SHIPS];
// textures of the sails, returned to the sail entity by GetSailTextureData
object SeaSailTextures[SEA_MAX_SHIPS];
int seaShipCount = 0;
// 0 holds every ship where it is (the fleet review)
float seaSpeedScale = 1.0;

float fogHeight = 150.0;
#define SEA_TICK_MS 40
// gusts (ours): the wind of the weather swings by these shares of its speed and radians of its angle
// over the periods in s, incommensurate so the gusts do not repeat; the sail entity reads the
// weather every frame: the belly and the ripples of the sails, the flags and the ship speed follow
#define SEA_PI2 6.2831853
#define SEA_WIND_SPEED 10.0
#define SEA_GUST 0.18
#define SEA_GUST_FAST 0.07
#define SEA_GUST_PERIOD 23.0
#define SEA_GUST_FAST_PERIOD 4.7
#define SEA_WIND_VEER 0.08
#define SEA_WIND_VEER_PERIOD 61.0
float seaTime = 0.0;
// sailing into the port (ours): the ship enters it when it comes back to the harbour as near as
// where it appeared plus SEA_PORT_REACH m, after it has sailed SEA_PORT_ARM m farther off than that
#define SEA_PORT_REACH 30.0
#define SEA_PORT_ARM 100.0
// TOWN_AUTO=5: the ship starts this much farther off on the line to the harbour and sails in by itself
#define SEA_AUTO_OFFSET 250.0
int seaHero = -1;
string seaIsland = "";
float seaPortDistance = 0.0;
bool seaPortArmed = false;
float cameraAngle = 1.6;
bool seaActive = false;
// TOWN_AUTO=4: the autotest lands this long after it has sailed out
#define SEA_AUTO_PORT_MS 5000
// M opens the world map (ours: the original opens it by sailing off the island)
#define SEA_MAP_KEY 77
#define SEA_AUTO_MAP_MS 3000
// coming from the map the ship appears this far out from its place at the harbour, sailing in (ours)
#define SEA_ARRIVE_OFFSET 400.0
// TOWN_AUTO=5 and 6: the ship sails in at about 2 m/s, minutes of sea; the autotest runs the time faster (ours)
#define SEA_AUTO_TIME_SCALE 6.0
// R at sea runs the time x1, x3, x6 in turn, kept from island to island (ours: the islands are km apart)
#define SEA_TIME_KEY 82
#define SEA_TIME_FAST 3.0
float seaTimeScale = 1.0;
bool seaFromMap = false;
bool seaAutoMapDone = false;
// SCENE=battle (battle.c): Sea_AddShip gives the ships to SEA_AI, an enemy comes after the hero
bool seaBattle = false;
// the island Sea_Start was given, for a save (seaIsland is "" where the island has no harbour)
string seaAt = "";
// a loaded game (save.c) puts the ship where it was saved, not at the port
bool seaLoadPos = false;
float seaLoadX = 0.0;
float seaLoadZ = 0.0;
float seaLoadAy = 0.0;

// The hero on his ship at the harbour of an island (a key of PdmIslands); the camera flies round it
// until the player takes the mouse, the run needs no input.
void Sea_Start(string islandKey)
{
	Sea_MapShipKeys();
	MapKey("Sea_ToMap", SEA_MAP_KEY);
	MapKey("Sea_Time", SEA_TIME_KEY);
	Sound_StopLocation();
	Sound_Music("Freesailing");
	Sea_CreateWorld();
	float x = 0.0;
	float z = 0.0;
	float ay = 0.0;
	if (Sea_CreateIsland(islandKey))
	{
		x = stf(PdmIslands.(islandKey).port_x);
		z = stf(PdmIslands.(islandKey).port_z);
		ay = stf(PdmIslands.(islandKey).port_ay);
	}
	seaIsland = "";
	seaPortArmed = false;
	if (CheckAttribute(&PdmIslands, islandKey + ".harbour_x"))
	{
		seaIsland = islandKey;
		seaPortDistance = Sea_HarbourDistance(x, z);
		float offset = 0.0;
		if (TownAuto == 5) { offset = SEA_AUTO_OFFSET; }
		if (seaFromMap) { offset = SEA_ARRIVE_OFFSET; }
		if (offset > 0.0 && seaPortDistance > 0.0)
		{
			float k = 1.0 + offset / seaPortDistance;
			x = stf(PdmIslands.(islandKey).harbour_x) + k * (x - stf(PdmIslands.(islandKey).harbour_x));
			z = stf(PdmIslands.(islandKey).harbour_z) + k * (z - stf(PdmIslands.(islandKey).harbour_z));
			// sailing in: the bow to the harbour, port_ay is the heading out of the port (ours); the ship
			// goes along (sin ay, cos ay). Avilia has no real harbour in the data (harbour 0,0, port next
			// to it), the ship there misses the port and sails off to the world map
			ay = atan2(stf(PdmIslands.(islandKey).harbour_x) - x, stf(PdmIslands.(islandKey).harbour_z) - z);
		}
	}
	seaAt = islandKey;
	if (seaLoadPos)
	{
		x = seaLoadX;
		z = seaLoadZ;
		ay = seaLoadAy;
		seaLoadPos = false;
	}
	// the ship entity steers the main character by the keys; SEA_AI takes it at its creation
	seaHero = seaShipCount;
	string heroType = PlayerShipCard.type_key;
	if (seaBattle && TownAuto == 11) { heroType = FORT_AUTO_SHIP; }
	int hero = Sea_AddShip(PlayerCard, heroType, x, z, ay);
	Sea_CreateCamera(hero);
	Hud_Start();
	if (seaBattle) { Battle_AddEnemy(x, z, ay); }
	SetEventHandler("Sea_Tick", "Sea_Tick", 0);
	SetEventHandler("Sea_ToPort", "Sea_ToPort", 0);
	SetEventHandler("Sea_ToMap", "Sea_ToMap", 0);
	PostEvent("Sea_Tick", SEA_TICK_MS);
	seaActive = true;
	seaFromMap = false;
	// TOWN_AUTO=4: the autotest sails out and comes back by itself; 6: out to the world map once
	if (TownAuto == 4) { PostEvent("Sea_ToPort", SEA_AUTO_PORT_MS); }
	if (TownAuto == 6 && !seaAutoMapDone) { seaAutoMapDone = true; PostEvent("Sea_ToMap", SEA_AUTO_MAP_MS); }
	if (TownAuto == 5 || TownAuto == 6) { seaTimeScale = SEA_AUTO_TIME_SCALE; }
	SetTimeScale(seaTimeScale);
	Trace("PDM: sea loaded");
}

void Sea_Control(string control)
{
	// the scene is changed outside the input handler
	if (control == "Sea_Time" && seaActive) { Sea_NextTimeScale(); }
	if (control == "Sea_ToMap" && seaActive) { PostEvent("Sea_ToMap", 0); }
	Battle_Control(control);
	Hud_Control(control);
}

void Sea_NextTimeScale()
{
	if (seaTimeScale < SEA_TIME_FAST) { seaTimeScale = SEA_TIME_FAST; }
	else
	{
		if (seaTimeScale < SEA_AUTO_TIME_SCALE) { seaTimeScale = SEA_AUTO_TIME_SCALE; }
		else { seaTimeScale = 1.0; }
	}
	SetTimeScale(seaTimeScale);
	Trace("PDM: sea, time x" + seaTimeScale);
}

// the town Enter takes the ship to: of the island at sea, or the one it sailed from; "" where the island
// has none (Emuno, Inachetla, Aliando, Chaktcha) or Town_Load does not know it
string Sea_PortTown()
{
	string town = townStreet;
	if (seaIsland != "") { town = PdmIslands.(seaIsland).town; }
	if (town == "" || !CheckAttribute(&PdmLocations, town)) { return ""; }
	return town;
}

// from the world map (map.c) to the sea at an island, the ship sailing in to its harbour
void Sea_Arrive(string islandKey)
{
	seaFromMap = true;
	Sea_Start(islandKey);
}

void Sea_ToMap()
{
	if (!seaActive) { return; }
	string island = seaIsland;
	Sea_Release();
	Trace("PDM: sea, to the world map from " + island);
	Map_Start(island);
}

// deletes what Sea_Start made, so that the next voyage starts afresh
void Sea_Release()
{
	seaActive = false;
	Hud_Release();
	Battle_Release();
	SetTimeScale(1.0);
	DelEventHandler("Sea_Tick", "Sea_Tick");
	DelEventHandler("Sea_ToPort", "Sea_ToPort");
	DelEventHandler("Sea_ToMap", "Sea_ToMap");
	DelEventHandler("WhrCalcFogColor", "Sea_FogColor");
	DelEventHandler("SeaGetLayers", "Sea_ShipLayers");
	DelEventHandler("Shp_UpdParams", "Sea_ShipParameters");
	DelEventHandler("GetSailTextureData", "Sea_SailTextures");
	DelEventHandler("GetRiggingData", "Sea_RiggingData");
	DeleteClass(&ShipCamera);
	DeleteClass(&SeaCameras);
	for (int i = 0; i < seaShipCount; i++) { DeleteClass(&SeaShips[i]); }
	seaShipCount = 0;
	seaHero = -1;
	DeleteClass(&Flag);
	DeleteClass(&VantL);
	DeleteClass(&Vant);
	DeleteClass(&Rope);
	DeleteClass(&Sail);
	DeleteClass(&Touch);
	DeleteClass(&Island);
	DeleteClass(&Sea);
	DeleteClass(&Sky);
	DeleteClass(&Weather);
}

void Sea_MapShipKeys()
{
	// read by the ship entity itself for the main character
	MapKey("Ship_TurnLeft", 65);
	MapKey("Ship_TurnRight", 68);
	MapKey("Ship_SailUp", 87);
	MapKey("Ship_SailDown", 83);
	// read by SHIP_CAMERA; 256/257 are the mouse axes
	MapKey("ShipCamera_Turn_H", 256);
	MapKey("ShipCamera_Turn_V", 257);
	MapKey("ShipCamera_Forward", 81);
	MapKey("ShipCamera_Backward", 69);
}

// Sea, sky and weather as in the sea demo, with the day preset; the wind blows the sails.
void Sea_CreateWorld()
{
	CreateEntity(&Weather, "weather");
	Weather.Fog.Enable = 1;
	Weather.Fog.Start = 0.0;
	Weather.Fog.Density = 0.002;
	Weather.Fog.Color = argb(0, 150, 185, 215);
	Weather.Sun.Color = argb(0, 230, 220, 205);
	Weather.Sun.Ambient = argb(0, 95, 100, 105);
	Weather.Sun.HeightAngle = 0.7;
	Weather.Sun.AzimuthAngle = 2.618;
	// the direction the wind blows to, about y from +z, and its speed in m/s; the sails take
	// 12 m/s as full wind
	Weather.Wind.Angle = 0.0;
	Weather.Wind.Speed = SEA_WIND_SPEED;
	Weather.isDone = "";

	SetEventHandler("WhrCalcFogColor", "Sea_FogColor", 0);
	CreateEntity(&Sky, "Sky");
	Sky.Size = 2048.0;
	Sky.Angle = 0.0;
	Sky.RotateSpeed = 0.0;
	Sky.techSky = "Sky";
	Sky.techSkyBlend = "SkyBlend";
	Sky.techSkyAlpha = "skyblend_alpha";
	Sky.techSkyFog = "SkyFog";
	LayerAddObject(EXECUTE, &Sky, 2);
	LayerAddObject(REALIZE, &Sky, 3);
	LayerAddObject(SEA_REFLECTION, &Sky, 1);
	Sky.Dir.d0 = "weather\skies\day\";
	Sky.Dir = "12";
	Sky.Color = argb(0, 255, 255, 255);
	Sky.isDone = "";

	CreateEntity(&Sea, "sea");
	LayerAddObject(EXECUTE, &Sea, 4);
	LayerAddObject(REALIZE, &Sea, 65530);
	Sea.Sea2.WaterColor = argb(0, 30, 90, 115);
	Sea.Sea2.SkyColor = argb(0, 205, 255, 255);
	// the 64 frames of demos/sea/make_sea.py are waves running round a tile of 128 / Scale m, a wave
	// of k crests per tile goes 1.6 * sqrt(k) times round a loop: deep water (period sqrt(2 pi L / g))
	// only when the loop is 1.6 / sqrt(g Scale / (2 pi 128)) s, so AnimSpeed = 64 / that: 3.42 frames
	// a second for the swell (waves of 24..142 m), 8.61 for the ripples (4..22 m). The day weather of
	// TEHO (1.5 / 15) played the swell twice slower and the ripples twice faster than the sea, and its
	// MoveSpeed slid the whole picture, a texture crawling over the water: the frames move the waves
	Sea.Sea2.Amp1 = 3.0;
	Sea.Sea2.AnimSpeed1 = 3.42;
	Sea.Sea2.Scale1 = 0.6;
	Sea.Sea2.MoveSpeed1 = "0.0, 0.0, 0.0";
	Sea.Sea2.Amp2 = 0.8;
	Sea.Sea2.AnimSpeed2 = 8.61;
	Sea.Sea2.Scale2 = 3.8;
	Sea.Sea2.MoveSpeed2 = "0.0, 0.0, 0.0";
	Sea.Sea2.PosShift = 1.0;
	Sea.Sea2.BumpScale = 0.05;
	Sea.Sea2.Reflection = 0.6;
	Sea.Sea2.Transparency = 0.45;
	Sea.Sea2.Frenel = 0.45;
	Sea.Sea2.Attenuation = 0.3;
	Sea.Sea2.LodScale = 0.5;
	Sea.Sea2.GridStep = 0.1;
	Sea.Sea2.FoamEnable = 1;
	Sea.Sea2.FoamK = 0.2;
	Sea.Sea2.FoamV = 2.0;
	Sea.Sea2.FoamUV = 0.5;
	Sea.Sea2.FoamTexDisturb = 0.7;
	Sea.Sea2.SimpleSea = 0;
	Sea.Fog.Enable = 1;
	Sea.Fog.Start = 0.0;
	Sea.Fog.Color = argb(0, 150, 185, 215);
	Sea.Fog.SeaDensity = 0.001;
	Sea.MaxSeaHeight = 50.0;
	Sea.isDone = "";
}

// The rigging entities: one of each draws the sails, stays and shrouds of all ships; the ship sends
// them its model when it is created, so they come first.
void Sea_CreateRigging()
{
	// sail reads resource\ini\rigging.ini; it is drawn and traced right after the ships
	CreateEntity(&Sail, "sail");
	LayerAddObject(EXECUTE, &Sail, iShipPriorityExecute + 1);
	LayerAddObject(REALIZE, &Sail, iShipPriorityRealize + 1);
	LayerAddObject(SAILS_TRACE, &Sail, 10);
	LayerAddObject(SEA_REFLECTION2, &Sail, 3);
	// rope draws the stays of the original as round ropes between the labels of the model
	CreateEntity(&Rope, "rope");
	LayerAddObject(EXECUTE, &Rope, iShipPriorityExecute + 2);
	LayerAddObject(REALIZE, &Rope, iShipPriorityRealize + 2);
	// vant and vantl draw the shrouds (labels vant1..9 and vanx1..9) as ropes with ratlines
	CreateEntity(&Vant, "vant");
	LayerAddObject(EXECUTE, &Vant, iShipPriorityExecute + 3);
	LayerAddObject(REALIZE, &Vant, iShipPriorityRealize + 3);
	CreateEntity(&VantL, "vantl");
	LayerAddObject(EXECUTE, &VantL, iShipPriorityExecute + 3);
	LayerAddObject(REALIZE, &VantL, iShipPriorityRealize + 3);
	// flag draws the flags (labels flag<N>) in the wind; a ship finds it by the entity name
	CreateEntity(&Flag, "flag");
	LayerAddObject(EXECUTE, &Flag, iShipPriorityExecute + 4);
	LayerAddObject(REALIZE, &Flag, iShipPriorityRealize + 4);
	LayerAddObject(SEA_REFLECTION2, &Flag, 3);
	// the ship asks for its layers, polls Shp_UpdParams for its top speeds and the sails ask
	// for their textures; all of them are raised while the ship is being created
	SetEventHandler("SeaGetLayers", "Sea_ShipLayers", 0);
	SetEventHandler("Shp_UpdParams", "Sea_ShipParameters", 0);
	SetEventHandler("GetSailTextureData", "Sea_SailTextures", 0);
	SetEventHandler("GetRiggingData", "Sea_RiggingData", 0);
}

// The flag asks for its picture: GetShipFlagTexNum, pennant or not, the nation (the index in
// WORLDS\nations.idf, which is the column of the atlas), special or not, the character.
ref Sea_RiggingData()
{
	string request = GetEventData();
	int pennant = GetEventData();
	int nation = GetEventData();
	SeaFlagTexture[0] = nation;
	SeaFlagTexture[1] = 0;
	return &SeaFlagTexture;
}

// A ship of the type typeKey (a key of PdmShipTypes, a record of WORLDS\Ships.idf) under the character
// card (a record of PdmCharacters, or any object with .id and .nation) at x, z heading ay.
// Returns its index in SeaShips.
// The island comes before touch and the ships: they look it up once, when they are created. The depth
// map round it is traced by the engine at the first start and saved in foam\islands.
bool Sea_CreateIsland(string islandKey)
{
	if (islandKey == "" || !CheckAttribute(&PdmIslands, islandKey + ".model")) { return false; }
	string model = PdmIslands.(islandKey).model;
	CreateEntity(&Island, "island");
	// lit by the sun of the weather, as the ships; no precomputed vertex colours
	Island.LightingPath = "";
	Island.dynamicLightsOn = 0;
	Island.Technique = "DLightModel";
	Island.FogDensity = 0.0015;
	Island.ImmersionDistance = 3000.0;
	Island.ImmersionDepth = 25.0;
	SendMessage(&Island, "lsss", MSG_ISLAND_LOAD_GEO, "islands", "islands\" + model, model);
	// before the sea: the sea is drawn over the shallows
	LayerAddObject(REALIZE, &Island, 4);
	CreateEntity(&Touch, "touch");
	LayerAddObject(EXECUTE, &Touch, 1);
	Touch.CollisionDepth = SEA_COLLISION_DEPTH;
	Trace("PDM: sea at the island " + islandKey + " (" + model + ")");
	return true;
}

int Sea_AddShip(aref card, string typeKey, float x, float z, float ay)
{
	if (seaShipCount == 0) { Sea_CreateRigging(); }
	int i = seaShipCount;
	seaShipCount = seaShipCount + 1;
	aref type;
	makearef(type, PdmShipTypes.(typeKey));

	// the sails of the nation (nations.idf): the cloth, and the coat of arms on the yards rey_emblem<n>
	// (the sails of sub 6 in the DEF); pdm_ship.py cut the arms out of emb_sail into ships\gerald
	aref nation = GetAttributeN(&PdmNations, sti(card.nation));
	SeaSailTextures[i].normalTex = "ships\sails\" + nation.sail + ".tga";
	if (nation.emb_sail != nation.sail)
	{
		for (int j = 1; j <= SEA_MAX_EMBLEMS; j++)
		{
			string yard = "rey_emblem" + j;
			SeaSailTextures[i].(yard).Gerald = "ships\gerald\" + nation.name + ".tga";
			// the arms cover the whole sail, as emb_sail did
			SeaSailTextures[i].(yard).hscale = 1.0;
		}
	}

	// the type from WORLDS\Ships.idf: speed in knots, turn rate, crew, hold
	SeaShipTypes[i].Name = type.id;
	SeaShipTypes[i].Class = sti(type.class);
	SeaShipTypes[i].SpeedRate = stf(type.speedrate);
	SeaShipTypes[i].TurnRate = stf(type.turnrate);
	SeaShipTypes[i].MinCrew = sti(type.mincrew);
	SeaShipTypes[i].MaxCrew = sti(type.maxcrew);
	SeaShipTypes[i].Capacity = sti(type.capacity);
	SeaShipTypes[i].HP = sti(type.hitpoint);
	SeaShipTypes[i].Weight = 300.0;
	SeaShipTypes[i].SpeedDependWeight = 0.2;
	SeaShipTypes[i].SubSeaDependWeight = 0.6;
	SeaShipTypes[i].TurnDependWeight = 0.2;
	SeaShipTypes[i].TurnDependSpeed = 0.3;
	SeaShipTypes[i].WaterLine = 0.0;
	// how fast the hull follows the sea under it, a share per second (ship.cpp ShipRocking): without
	// it the engine takes 1.0 and the hull shook with every ripple; the usual values of the TEHO ships
	SeaShipTypes[i].Rocking.y = 0.4;
	SeaShipTypes[i].Rocking.az = 0.035;
	// how fast the ship follows its target speed (x sideways, y turning, z ahead) and stops
	SeaShipTypes[i].InertiaAccelerationX = 0.2;
	SeaShipTypes[i].InertiaBrakingX = 2.0;
	SeaShipTypes[i].InertiaAccelerationY = 6.0;
	SeaShipTypes[i].InertiaBrakingY = 3.0;
	SeaShipTypes[i].InertiaAccelerationZ = 4.0;
	SeaShipTypes[i].InertiaBrakingZ = 3.0;

	DeleteAttribute(&SeaShips[i], "");
	SeaShips[i].id = card.id;
	if (CheckAttribute(card, "ship_key")) { SeaShips[i].ship_key = card.ship_key; }
	// the keys steer the main character; in the battle autotest SEA_AI steers the hero (battle.c)
	// the script compiler does not parse "a && (b || c)"
	bool autopilot = TownAuto == 7 || TownAuto == 8 || TownAuto == 11;
	if (!seaBattle) { autopilot = false; }
	if (i == seaHero && !autopilot) { SeaShips[i].MainCharacter = 1; }
	SeaShips[i].index = i;
	SeaShips[i].nation = sti(card.nation);
	SeaShips[i].ship.pos.x = x;
	SeaShips[i].ship.pos.z = z;
	SeaShips[i].ship.ang.y = ay;
	// a positive speed starts with the sails set
	SeaShips[i].Ship.Speed.z = 1.0;

	if (seaBattle) { Battle_AddShip(i, x, z, ay); }
	else
	{
		CreateEntity(&SeaShips[i], "ship");
		SendMessage(&SeaShips[i], "laa", MSG_SHIP_CREATE, &SeaShips[i], &SeaShipTypes[i]);
	}
	// lit by the sun of the weather; without a technique the vertex colours are drawn as is
	SendMessage(&SeaShips[i], "ls", 20510, "DLightModel");
	Sea_UpdateSpeeds(i, 1.0);
	return i;
}

void Sea_CreateCamera(int i)
{
	CreateEntity(&SeaCameras, "SEA_CAMERAS");
	CreateEntity(&ShipCamera, "SHIP_CAMERA");
	ShipCamera.Perspective = 1.285;
	ShipCamera.SensivityDistance = 30.0;
	ShipCamera.SensivityHeightAngle = 0.02;
	ShipCamera.SensivityHeightAngleOnShip = 0.005;
	ShipCamera.SensivityAzimuthAngle = 0.04;
	ShipCamera.MaxAngleX = 0.07;
	ShipCamera.MinAngleX = -1.4;
	// 0..1 between close to the hull and far out
	ShipCamera.Distance = 0.0;
	ShipCamera.MinDistance = 25.0;
	ShipCamera.MaxDistance = 1500.0;
	ShipCamera.MinHeightOnSea = 1.0;
	ShipCamera.MaxHeightOnShip = 5.0;
	ShipCamera.InvertMouseX = 1.0;
	ShipCamera.InvertMouseY = -1.0;
	// SEA_CAMERAS switches between the sea cameras and gives the active one its character;
	// the scene executes the active camera every frame
	SendMessage(&SeaCameras, "lia", AI_CAMERAS_SET_CAMERA, &ShipCamera, &SeaShips[i]);
	SendMessage(&Scene, "si", "SetActiveCamera", &ShipCamera);
}

float Sea_HarbourDistance(float x, float z)
{
	float dx = x - stf(PdmIslands.(seaIsland).harbour_x);
	float dz = z - stf(PdmIslands.(seaIsland).harbour_z);
	return sqrt(dx * dx + dz * dz);
}

// the distance of the ship of the hero from the harbour, -1 out of an island; the ship entity writes its
// position into ship.pos of its character every frame
float Sea_HeroHarbourDistance()
{
	if (seaIsland == "" || seaHero < 0 || !CheckAttribute(&SeaShips[seaHero], "ship.pos.x")) { return -1.0; }
	return Sea_HarbourDistance(stf(SeaShips[seaHero].ship.pos.x), stf(SeaShips[seaHero].ship.pos.z));
}

// the ship is no farther off the harbour than where it appears leaving the town (and SEA_PORT_REACH m)
bool Sea_NearHarbour(float d)
{
	return d >= 0.0 && d <= seaPortDistance + SEA_PORT_REACH;
}

// the port is the town of the island, as Town_Load knows it (Telltak's Grot is not a town yet)
bool Sea_AtHarbour(float d)
{
	string town = PdmIslands.(seaIsland).town;
	if (d < 0.0 || town == "" || !CheckAttribute(&PdmLocations, town)) { return false; }
	if (d > seaPortDistance + SEA_PORT_ARM) { seaPortArmed = true; }
	if (!seaPortArmed || d > seaPortDistance + SEA_PORT_REACH) { return false; }
	Trace("PDM: sea, the ship at the harbour of " + seaIsland + ", " + d + " m");
	return true;
}

// SHIP_CAMERA.AngleY: the camera angle around the ship, 0 behind the stern; the autotests fly it round
// the ship, the player turns it with the mouse
void Sea_Tick()
{
	// the autotests fly the camera round the ship; in a battle it follows the enemy or the fort (Battle_AddEnemy, Fort_Auto)
	bool cameraFollows = seaBattle && battleEnemy >= 0;
	if (fortAuto) { cameraFollows = true; }
	if (TownAuto != 0 && !cameraFollows)
	{
		cameraAngle = cameraAngle + 0.006;
		ShipCamera.AngleY = cameraAngle;
	}
	seaTime = seaTime + SEA_TICK_MS / 1000.0;
	float gust = SEA_GUST * sin(SEA_PI2 * seaTime / SEA_GUST_PERIOD) + SEA_GUST_FAST * sin(SEA_PI2 * seaTime / SEA_GUST_FAST_PERIOD);
	Weather.Wind.Speed = SEA_WIND_SPEED * (1.0 + gust);
	Weather.Wind.Angle = SEA_WIND_VEER * sin(SEA_PI2 * seaTime / SEA_WIND_VEER_PERIOD);
	float d = Sea_HeroHarbourDistance();
	// the player lands by the command of the toolbar; the autotest sailing in lands by itself
	if (TownAuto != 0 && Sea_AtHarbour(d)) { PostEvent("Sea_ToPort", 0); return; }
	Hud_SeaTick();
	if (seaBattle) { Board_SeaTick(); }
	if (d > 0.0 && CheckAttribute(&PdmIslands, seaIsland + ".exit_r") && d > stf(PdmIslands.(seaIsland).exit_r))
	{
		PostEvent("Sea_ToMap", 0);
		return;
	}
	PostEvent("Sea_Tick", SEA_TICK_MS);
}

void Sea_ShipLayers()
{
	aref ship = GetEventData();
	SendMessage(ship, "lll", AI_MESSAGE_SET_LAYERS, EXECUTE, REALIZE);
}

// Top speeds of a ship: the sails give a share of the wind from 0 to 1, the ship multiplies it
// by MaxSpeedZ (knots); the turn controls give -1..1 and the ship multiplies that by MaxSpeedY.
void Sea_ShipParameters()
{
	int index = GetEventData();
	float sailState = GetEventData();
	Sea_UpdateSpeeds(index, sailState);
}

void Sea_UpdateSpeeds(int i, float sailState)
{
	SeaShips[i].Ship.MaxSpeedZ = stf(SeaShipTypes[i].SpeedRate) * seaSpeedScale;
	// a ship under sail turns faster than one drifting
	SeaShips[i].Ship.MaxSpeedY = stf(SeaShipTypes[i].TurnRate) / 160.0 * (0.4 + 0.6 * sailState);
}

ref Sea_SailTextures()
{
	int index = GetEventData();
	return &SeaSailTextures[index];
}

int Sea_FogColor()
{
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float k = y / fogHeight;
	if (k < 0.0) { k = 0.0; }
	if (k > 1.0) { k = 1.0; }
	int alpha = 255 - makeint(255.0 * k);
	return or(shl(alpha, 24), sti(Weather.Fog.Color));
}

