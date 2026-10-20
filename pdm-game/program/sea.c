// The sea of the original world: the weather and the sea of the engine demos, the ship of the hero
// built from its type in WORLDS\Ships.idf (the hull is models\ships\<filename>, assembled by
// tools/pdm_ship.py from DESC\<filename>.def). A/D turn, W/S sails, the mouse turns the camera.

// shared/layers.h: mirrored into the sea reflection (sky in the first, ships in the second)
#define SEA_REFLECTION 15
#define SEA_REFLECTION2 16
// shared/layers.h: what the cannon balls and cameras trace against
#define SAILS_TRACE 19

// shared/messages.h and shared/sea_ai/script_defines.h
#define MSG_SHIP_CREATE 50300
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
float cameraAngle = 1.6;

// The hero on his ship; the camera flies round it until the player takes the mouse, the run needs no input.
void Sea_Start()
{
	Sea_MapShipKeys();
	Sea_CreateWorld();
	int hero = Sea_AddShip(PlayerCard, PlayerShipCard.type_key, 0.0, 0.0, 0.0);
	SeaShips[hero].MainCharacter = 1;
	Sea_CreateCamera(hero);
	SetEventHandler("Sea_Tick", "Sea_Tick", 0);
	PostEvent("Sea_Tick", SEA_TICK_MS);
	Trace("PDM: sea loaded");
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
	Weather.Wind.Speed = 10.0;
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
	Sea.Sea2.Amp1 = 3.0;
	Sea.Sea2.AnimSpeed1 = 1.5;
	Sea.Sea2.Scale1 = 0.6;
	Sea.Sea2.MoveSpeed1 = "2.0, 0.0, 0.0";
	Sea.Sea2.Amp2 = 0.8;
	Sea.Sea2.AnimSpeed2 = 15.0;
	Sea.Sea2.Scale2 = 3.8;
	Sea.Sea2.MoveSpeed2 = "1.0, 0.0, 1.0";
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
	// how fast the ship follows its target speed (x sideways, y turning, z ahead) and stops
	SeaShipTypes[i].InertiaAccelerationX = 0.2;
	SeaShipTypes[i].InertiaBrakingX = 2.0;
	SeaShipTypes[i].InertiaAccelerationY = 6.0;
	SeaShipTypes[i].InertiaBrakingY = 3.0;
	SeaShipTypes[i].InertiaAccelerationZ = 4.0;
	SeaShipTypes[i].InertiaBrakingZ = 3.0;

	SeaShips[i].id = card.id;
	SeaShips[i].index = i;
	SeaShips[i].nation = sti(card.nation);
	SeaShips[i].ship.pos.x = x;
	SeaShips[i].ship.pos.z = z;
	SeaShips[i].ship.ang.y = ay;
	// a positive speed starts with the sails set
	SeaShips[i].Ship.Speed.z = 1.0;

	CreateEntity(&SeaShips[i], "ship");
	SendMessage(&SeaShips[i], "laa", MSG_SHIP_CREATE, &SeaShips[i], &SeaShipTypes[i]);
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

// SHIP_CAMERA.AngleY: the camera angle around the ship, 0 behind the stern
void Sea_Tick()
{
	cameraAngle = cameraAngle + 0.006;
	ShipCamera.AngleY = cameraAngle;
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

