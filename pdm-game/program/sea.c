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
object SeaCameras;
object ShipCamera;
// the ship type: the engine reads its parameters and the model name, ships\<Name>\<Name>.gm
object BaseShip;
// the character the ship entity lives on
object Player;
// textures of the sails, returned to the sail entity by GetSailTextureData
object SailTextures;

float fogHeight = 150.0;
#define SEA_TICK_MS 40
float cameraAngle = 1.6;

void Sea_Start()
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

	CreateWorld();
	CreateShip();
	CreateCamera();
	// the camera flies round the ship until the player takes the mouse; the run needs no input
	SetEventHandler("Sea_Tick", "Sea_Tick", 0);
	PostEvent("Sea_Tick", SEA_TICK_MS);
	Trace("PDM: sea loaded");
}

// Sea, sky and weather as in the sea demo, with the day preset; the wind blows the sails.
void CreateWorld()
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

// The ship: rigging entities first (the ship sends them its model when it is created), then the
// type, the character and the ship entity on it.
void CreateShip()
{
	// sail reads resource\ini\rigging.ini; it is drawn and traced right after the ship
	CreateEntity(&Sail, "sail");
	LayerAddObject(EXECUTE, &Sail, iShipPriorityExecute + 1);
	LayerAddObject(REALIZE, &Sail, iShipPriorityRealize + 1);
	LayerAddObject(SAILS_TRACE, &Sail, 10);
	LayerAddObject(SEA_REFLECTION2, &Sail, 3);
	// the sail texture of each hull is written by pdm_ship.py next to its other textures
	SailTextures.normalTex = "ships\" + PlayerShipType.id + "\parus_all.tga";
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


	// the type of the hero's ship from WORLDS\Ships.idf: speed in knots, turn rate, crew, hold
	BaseShip.Name = PlayerShipType.id;
	BaseShip.Class = sti(PlayerShipType.class);
	BaseShip.SpeedRate = stf(PlayerShipType.speedrate);
	BaseShip.TurnRate = stf(PlayerShipType.turnrate);
	BaseShip.MinCrew = sti(PlayerShipType.mincrew);
	BaseShip.MaxCrew = sti(PlayerShipType.maxcrew);
	BaseShip.Capacity = sti(PlayerShipType.capacity);
	BaseShip.HP = sti(PlayerShipType.hitpoint);
	BaseShip.Weight = 300.0;
	BaseShip.SpeedDependWeight = 0.2;
	BaseShip.SubSeaDependWeight = 0.6;
	BaseShip.TurnDependWeight = 0.2;
	BaseShip.TurnDependSpeed = 0.3;
	BaseShip.WaterLine = 0.0;
	// how fast the ship follows its target speed (x sideways, y turning, z ahead) and stops
	BaseShip.InertiaAccelerationX = 0.2;
	BaseShip.InertiaBrakingX = 2.0;
	BaseShip.InertiaAccelerationY = 6.0;
	BaseShip.InertiaBrakingY = 3.0;
	BaseShip.InertiaAccelerationZ = 4.0;
	BaseShip.InertiaBrakingZ = 3.0;

	Player.id = PlayerCard.id;
	Player.index = 0;
	Player.nation = sti(PlayerCard.nation);
	// the ship of the main character reads the Ship_* controls itself
	Player.MainCharacter = 1;
	Player.ship.pos.x = 0.0;
	Player.ship.pos.z = 0.0;
	Player.ship.ang.y = 0.0;
	// a positive speed starts with the sails set
	Player.Ship.Speed.z = 1.0;

	// the ship asks for its layers, polls Shp_UpdParams for its top speeds and the sails ask
	// for their textures; all of them are raised while the ship is being created
	SetEventHandler("SeaGetLayers", "Sea_ShipLayers", 0);
	SetEventHandler("Shp_UpdParams", "Sea_ShipParameters", 0);
	SetEventHandler("GetSailTextureData", "Sea_SailTextures", 0);
	CreateEntity(&Player, "ship");
	SendMessage(&Player, "laa", MSG_SHIP_CREATE, &Player, &BaseShip);
	// lit by the sun of the weather; without a technique the vertex colours are drawn as is
	SendMessage(&Player, "ls", 20510, "DLightModel");
	Sea_UpdateSpeeds(1.0);
}

void CreateCamera()
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
	SendMessage(&SeaCameras, "lia", AI_CAMERAS_SET_CAMERA, &ShipCamera, &Player);
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

// Top speeds of the ship: the sails give a share of the wind from 0 to 1, the ship multiplies it
// by MaxSpeedZ (knots); the turn controls give -1..1 and the ship multiplies that by MaxSpeedY.
void Sea_ShipParameters()
{
	int index = GetEventData();
	float sailState = GetEventData();
	Sea_UpdateSpeeds(sailState);
}

void Sea_UpdateSpeeds(float sailState)
{
	Player.Ship.MaxSpeedZ = stf(BaseShip.SpeedRate);
	// a ship under sail turns faster than one drifting
	Player.Ship.MaxSpeedY = stf(BaseShip.TurnRate) / 160.0 * (0.4 + 0.6 * sailState);
}

ref Sea_SailTextures()
{
	int index = GetEventData();
	return &SailTextures;
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

