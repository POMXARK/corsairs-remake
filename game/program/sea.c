// The sea battle, the first scene of the game: the player's brig «Ласточка» against the brig «Ворон»
// at an island, with the HUD over it. Built from the engine demos (sea, ship, island, enemy ship,
// HUD): SEA_AI steers the enemy and aims the guns of both, touch keeps the ships off the shore and
// each other, battle_interface draws the navigator and the ship panel.
// The scene lives in layers EXECUTE/REALIZE (and the sea reflection ones). Going to the menu only
// freezes them, so the battle stays as it was until the player continues.
// Space fires the guns that bear, R starts a new battle, Z and X zoom the minimap. A/D turn, W/S set
// and furl the sails, the mouse turns the camera, Escape opens the menu.

#define EXECUTE 0
#define REALIZE 1
// shared/layers.h: mirrored into the sea reflection (sky in the first, ships in the second)
#define SEA_REFLECTION 15
#define SEA_REFLECTION2 16
// shared/layers.h: what the cannon balls and cameras trace against
#define SAILS_TRACE 19

// shared/messages.h: "lsss", the foam dir under resource\foam\, the models dir under
// resource\models\ and the name of the island model
#define MSG_ISLAND_LOAD_GEO 50100

// shared/sea_ai/script_defines.h
#define AI_MESSAGE_ADD_SHIP 51001
#define AI_MESSAGE_CANNON_FIRE 51002
#define AI_MESSAGE_SET_CAMERAS_ATTRIBUTE 51004
#define AI_MESSAGE_GROUP_SET_XYZ_AY 51010
#define AI_MESSAGE_SHIP_SET_TASK 51011
#define AI_MESSAGE_SET_LAYERS 51015
#define AI_MESSAGE_GROUP_SET_COMMANDER 51022
#define AI_MESSAGE_CHARACTER_DEAD 51026
#define AI_CAMERAS_SET_CAMERA 55001
#define AITASK_ATTACK 1
#define PRIMARY_TASK 0
#define RELATION_FRIEND 1
#define RELATION_ENEMY 3
#define SHIP_MAST_TOUCH_BALL 2

// "lsffffffl": name, position, angles, lifetime in ms (0 burns until the system ends itself)
#define PS_CREATE 10000

#define MSG_SOUND_PLAY 77003
#define MSG_SOUND_SET_MASTER_VOLUME 77021
#define PCM_3D 1
#define MP3_STEREO 2
#define VOLUME_FX 1
#define VOLUME_MUSIC 2

// shared/battle_interface/msg_control.h
#define BI_IN_CREATE_SHIP 46011
#define BI_IN_DEAD_SHIP 46009
#define BI_RELATION_ENEMY 0
#define BI_RELATION_FRIEND 1
// the cells of hud\icons.tga (make_hud.py)
#define ICON_BALLS 0
#define ICON_SAILS_FURLED 1
#define ICON_WIND_CALM 4

#define LOG_ADD_STRING 45020
#define LOG_AND_ACTIONS_INIT 45022

#define PI 3.14159265
// the muzzle speed of a ball in m/s and the highest elevation of the guns: together they give a
// reach of about 250 m (AICannon::CalcMaxFireDistance): after its broadside the enemy may fall
// back well past ATTACK_DISTANCE, a shorter reach leaves the player nothing to fire at
#define BALL_SPEED 80.0
#define GUN_ELEVATION 0.2
#define ATTACK_DISTANCE 110.0
// the guns of a side fire within this angle around its beam
#define FIRE_ZONE 1.4
#define RELOAD_TIME 8.0
// the guns of a broadside go off one after another within this time
#define FIRE_SPREAD 0.6
// the aim point is scattered around the target in a circle growing with the distance
#define SCATTER 0.04
#define HULL 100
#define HULL_HIT_DAMAGE 4
// a blow on the shore costs this much hull per knot of the impact
#define GROUND_DAMAGE 2.0
// a ship resting on the shore under sail keeps touching it at ~0.5 kn: not a blow
#define GROUND_MIN_POWER 1.0
// touch pushes a ship back where the depth map is this shallow under one point of its hull
#define COLLISION_DEPTH -4.0
#define MAST_HIT_DAMAGE 0.34
#define ENEMY_SPEED 9.0
// the player south of the island, heading for it; the enemy west of the player, within the map of
// the navigator, so the fight starts at once
#define PLAYER_START_X -150.0
#define PLAYER_START_Z -380.0
#define ENEMY_START_X -380.0
#define ENEMY_START_Z -160.0

int iShipPriorityExecute = 2;
int iShipPriorityRealize = 31;

object Render;
object Scene;
object Weather;
object Sky;
object Sea;
object Sail;
object SeaCameras;
object ShipCamera;
object ScreenLog;
object Particles;
object Sound;
// the land, its sea floor and the depth map of the waters around
object Island;
// pushes the ships off the shore and off each other
object Touch;
// steers the enemy, aims and loads the guns of both ships
object AISea;
// what SEA_AI reads about the camera: OutsideCamera makes it aim the player's guns at the enemy
// rather than along the view
object AICameras;
object AIBalls;
object BaseShip;
// characters 0 and 1: the ship entities and SEA_AI find each other's owner by the index attribute
object Player;
object Enemy;
object SailTextures;
// the HUD: the navigator and the ship panel
object BattleInterface;
// what GetCurrentCharge returns: the icons of the charge, the sails and the wind, the powder
int hudIcons[5];

int battleOver = 0;
// the broadsides of the player; Ship_Bort_Fire comes inside the fire message, so a key press that
// does not change it found no side bearing on the enemy
int playerBroadsides = 0;
int shots = 0;
int hits = 0;
int islandHits = 0;
int shallowsCalled = 0;

float fogHeight = 150.0;

int sceneCreated = 0;

void Scene_MapControls()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	MapKey("Ship_TurnLeft", 65, 0);
	MapKey("Ship_TurnRight", 68, 0);
	MapKey("Ship_SailUp", 87, 0);
	MapKey("Ship_SailDown", 83, 0);
	MapKey("ShipCamera_Turn_H", 256, 0);
	MapKey("ShipCamera_Turn_V", 257, 0);
	MapKey("Sea_Fire", 32, 0);
	MapKey("Sea_NewBattle", 82, 0);
	// read every frame while held: the minimap zooms smoothly
	MapKey("MiniMapZoomIn", 90, 0);
	MapKey("MiniMapZoomOut", 88, 0);
	MapKey("Scene_Menu", 27, 0);
}

// a new game: builds the scene once, later starts a new battle in it
void Scene_Start()
{
	if (sceneCreated != 0)
	{
		Sea_NewBattle();
		return;
	}
	sceneCreated = 1;
	Weather.Wind.Angle = 0.0;
	Weather.Wind.Speed = 12.0;

	Render.BackColor = argb(255, 0, 0, 0);
	CreateEntity(&Scene, "Scene");
	LayerAddObject(EXECUTE, &Scene, 0);
	CreateWorld();
	CreateIsland();
	CreateSail();
	CreateLog();
	CreateEffects();
	CreateBattle();
	CreateCamera();
	CreateHud();

	SetEventHandler("Sea_StartBattle", "Sea_StartBattle", 0);
	Log("Враг на западе. Пробел — огонь, R — новый бой");
	Trace("SEA: scene loaded");
}

void Scene_Freeze(int freeze)
{
	LayerFreeze(EXECUTE, freeze);
	LayerFreeze(REALIZE, freeze);
	LayerFreeze(SEA_REFLECTION, freeze);
	LayerFreeze(SEA_REFLECTION2, freeze);
}

// Sounds, particles and the cannonballs. AIBalls reads the ball types once, on isDone.
void CreateEffects()
{
	CreateEntity(&Particles, "particles");

	CreateEntity(&Sound, "Sound");
	SendMessage(&Sound, "lfff", MSG_SOUND_SET_MASTER_VOLUME, 1.0, 0.5, 1.0);
	SendMessage(&Sound, "lslllllllf", MSG_SOUND_PLAY, "music\battle.wav", MP3_STEREO, VOLUME_MUSIC,
		false, true, false, 3000, 0, 1.0);

	// AIBalls takes the renderer from the helper of SEA_AI: SEA_AI comes first
	CreateSeaAI();
	CreateEntity(&AIBalls, "AIBalls");
	LayerAddObject(EXECUTE, &AIBalls, 10);
	LayerAddObject(REALIZE, &AIBalls, 10);
	AIBalls.Texture = "demo\ball.tga";
	AIBalls.SubTexX = 1;
	AIBalls.SubTexY = 1;
	AIBalls.SpeedMultiply = 1.0;
	AIBalls.BallFlySoundDistance = 0.0;
	AIBalls.BallFlySoundStereoMultiplyer = 1.0;
	AIBalls.Balls.Balls.SubTexIndex = 0;
	AIBalls.Balls.Balls.GoodIndex = 0;
	AIBalls.Balls.Balls.Size = 0.5;
	AIBalls.Balls.Balls.Weight = 1.0;
	AIBalls.isDone = "";

	SetEventHandler("Shp_HullHit", "Sea_HullHit", 0);
	SetEventHandler("Ball_WaterHit", "Sea_WaterHit", 0);
	SetEventHandler("ShpMastDamage", "Sea_MastDamage", 0);

	// SEA_AI asks these and reads the answer: without a handler it reads nothing and asserts
	SetEventHandler("GetRelationEvent", "Sea_Relation", 0);
	SetEventHandler("Shp_GetCurBallsNum", "Sea_BallsNum", 0);
	SetEventHandler("CannGRTime", "Sea_ReloadTime", 0);
	SetEventHandler("CannGFTime", "Sea_FireDelay", 0);
	SetEventHandler("CannGFHeight", "Sea_FireHeight", 0);
	SetEventHandler("CannLoad", "Sea_CannonLoad", 0);
	SetEventHandler("ShpGetBortFireDelta", "Sea_FireScatter", 0);
	// and calls these back
	SetEventHandler("CannFire", "Sea_CannonFire", 0);
	SetEventHandler("Ship_Bort_Fire", "Sea_BroadsideFired", 0);
	SetEventHandler("Shp_BortReloaded", "Sea_BroadsideReloaded", 0);
}

// The island comes before SEA_AI, touch and the ships: each of them looks it up once, when it is
// created, and SEA_AI checks the depth under a ship as soon as it is placed.
void CreateIsland()
{
	CreateEntity(&Island, "island");
	// the island draws itself with its own fog density and without the lights of the scene: the
	// light is baked into its texture, an empty path means no precomputed vertex colours
	Island.LightingPath = "";
	Island.dynamicLightsOn = 0;
	Island.Technique = "DLightModel";
	Island.FogDensity = 0.0015;
	// past this distance from the camera the island sinks a little to hide under the horizon
	Island.ImmersionDistance = 3000.0;
	Island.ImmersionDepth = 25.0;
	// resource\models\islands\isle\isle.gm and resource\foam\islands\isle.{tga,ini}
	SendMessage(&Island, "lsss", MSG_ISLAND_LOAD_GEO, "islands", "islands\isle", "isle");
	// before the sea: the sea is drawn over the shallows and the sea floor
	LayerAddObject(REALIZE, &Island, 4);

	SetEventHandler("Shp_ShipIslColl", "Sea_ShipIslandCollision", 0);
	SetEventHandler("Shp2Strand", "Sea_Shallows", 0);
	SetEventHandler("Ball_IslandHit", "Sea_IslandHit", 0);
	SetEventHandler("Sea_GroundClear", "Sea_GroundClear", 0);
	SetEventHandler("Sea_ShallowsClear", "Sea_ShallowsClear", 0);
}

// touch registers every ship created after it: made again with the ships of every battle
void CreateTouch()
{
	CreateEntity(&Touch, "touch");
	LayerAddObject(EXECUTE, &Touch, 1);
	Touch.CollisionDepth = COLLISION_DEPTH;
}

void CreateSeaAI()
{
	CreateEntity(&AISea, "SEA_AI");
	LayerAddObject(EXECUTE, &AISea, 0);
	LayerAddObject(REALIZE, &AISea, 0);
}

// SEA_AI and its two groups: the player alone south of the island, the enemy north of it. A
// ship is placed at the position of its group; isDone, after the last ship, settles the start
// positions. The task is given last, when SEA_AI knows both ships.
void CreateBattle()
{
	battleOver = 0;
	AICameras.Crosshair.OutsideCamera = 1;
	AICameras.Crosshair.Texture = "demo\ball.tga";
	SendMessage(&AISea, "la", AI_MESSAGE_SET_CAMERAS_ATTRIBUTE, &AICameras);

	PrepareCharacter(&Player, "Player", 0, "PlayerGroup");
	Player.MainCharacter = 1;
	Player.Ship.Name = "Ласточка";
	PrepareCharacter(&Enemy, "Enemy", 1, "EnemyGroup");
	Enemy.Ship.Name = "Ворон";
	Enemy.Ship.Mode = "war";
	Enemy.Ship.SeaAI.Init.AttackDistance = ATTACK_DISTANCE;

	CreateTouch();
	AddShip(&Player, "PlayerGroup", PLAYER_START_X, PLAYER_START_Z, 0.0);
	AddShip(&Enemy, "EnemyGroup", ENEMY_START_X, ENEMY_START_Z, PI);
	AISea.isDone = "";

	SendMessage(&AISea, "lllaa", AI_MESSAGE_SHIP_SET_TASK, AITASK_ATTACK, PRIMARY_TASK, &Enemy, &Player);
}

// The character of a ship: its index, its group, the guns and the hull. Cannons.Borts gets a class
// per side from SEA_AI with the charge and the reach of the side.
void PrepareCharacter(ref character, string id, int index, string group)
{
	DeleteAttribute(character, "");
	character.id = id;
	character.index = index;
	character.nation = index;
	character.SeaAI.Group.Name = group;
	character.Ship.HP = HULL;
	character.Ship.SP = 100;
	character.Ship.SailState = 1.0;
	character.Ship.Crew.quantity = 96;
	character.Ship.Grounded = 0;
	character.Ship.Touched = 0;
	character.Ship.Cannons.Type = 0;
	character.Ship.Cannons.SpeedV0 = BALL_SPEED;
	character.Ship.Cannons.Borts = "";
	character.Ship.Speed.z = 1.0;
}

void AddShip(ref character, string group, float x, float z, float heading)
{
	SendMessage(&AISea, "lsa", AI_MESSAGE_GROUP_SET_COMMANDER, group, character);
	SendMessage(&AISea, "lsffff", AI_MESSAGE_GROUP_SET_XYZ_AY, group, x, 0.0, z, heading);
	CreateEntity(character, "ship");
	SendMessage(&AISea, "liaa", AI_MESSAGE_ADD_SHIP, character, character, &BaseShip);
	SendMessage(character, "ls", 20510, "DLightModel");
}

// A new battle: deleting SEA_AI deletes its ships and their entities, then both are made again.
// SEA_AI keeps its ships in static lists and its destructor runs at the end of the frame: made
// in the same frame, the new ships would be deleted with the old ones, so they wait a frame.
void Sea_NewBattle()
{
	// the HUD keeps pointers to the ships SEA_AI is about to delete: it goes first and is made again
	DeleteClass(&BattleInterface);
	DeleteClass(&AISea);
	DeleteClass(&Touch);
	PostEvent("Sea_StartBattle", 1);
}

void Sea_StartBattle()
{
	CreateSeaAI();
	shots = 0;
	hits = 0;
	islandHits = 0;
	CreateBattle();
	SendMessage(&SeaCameras, "lia", AI_CAMERAS_SET_CAMERA, &ShipCamera, &Player);
	CreateHud();
	Log("Новый бой");
	Trace("SEA: new battle");
}

int Sea_Relation()
{
	int index1 = GetEventData();
	int index2 = GetEventData();
	if (index1 == index2) { return RELATION_FRIEND; }
	return RELATION_ENEMY;
}

// the balls in the hold; a side fires only when there is a ball for each of its guns
int Sea_BallsNum()
{
	aref character = GetEventData();
	return 100;
}

float Sea_ReloadTime()
{
	aref character = GetEventData();
	return RELOAD_TIME + frnd() * 1.0;
}

// the delay between the order and the shot, different for every gun: the broadside rolls along
float Sea_FireDelay()
{
	aref character = GetEventData();
	return frnd() * FIRE_SPREAD;
}

// the guns aim this high above the waterline of the target: at the hull
float Sea_FireHeight()
{
	aref character = GetEventData();
	aref enemy = GetEventData();
	return 1.5;
}

// 1: a ball is rammed home
int Sea_CannonLoad()
{
	aref character = GetEventData();
	return 1;
}

float Sea_FireScatter()
{
	aref character = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float dx = x - stf(character.ship.pos.x);
	float dz = z - stf(character.ship.pos.z);
	return SCATTER * sqrt(dx * dx + dz * dz);
}

// "lisffffff": a side has been ordered to fire, at the point given
void Sea_BroadsideFired()
{
	int index = GetEventData();
	int ship = GetEventData();
	string bort = GetEventData();
	string side = "правым";
	if (bort == "cannonl") { side = "левым"; }
	if (index == sti(Player.index))
	{
		playerBroadsides++;
		Log("Залп " + side + " бортом!");
	}
	else { Log("Враг даёт залп " + side + " бортом!"); }
	Trace("SEA: " + index + " fires " + bort);
}

// "as": the guns of a side are loaded again
void Sea_BroadsideReloaded()
{
	aref character = GetEventData();
	string bort = GetEventData();
	if (sti(character.index) != sti(Player.index) || battleOver) { return; }
	if (bort == "cannonl") { Log("Левый борт заряжен"); }
	else { Log("Правый борт заряжен"); }
}

// "afffffffff": one gun goes off. SEA_AI gives the muzzle, the heading and elevation it has aimed
// the shot at and the reach of the gun; the ball is handed to AIBalls as in the battle demo.
void Sea_CannonFire()
{
	aref character = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float speed = GetEventData();
	float heading = GetEventData();
	float elevation = GetEventData();
	float gunHeading = GetEventData();
	float reach = GetEventData();
	float rawAngle = GetEventData();

	AIBalls.Type = "Balls";
	AIBalls.CharacterIndex = character.index;
	AIBalls.x = x;
	AIBalls.y = y;
	AIBalls.z = z;
	AIBalls.SpdV0 = speed;
	AIBalls.HeightMultiply = 1.0;
	AIBalls.SizeMultiply = 1.0;
	AIBalls.TimeSpeedMultiply = 1.0;
	AIBalls.CannonType = 0;
	AIBalls.MaxFireDistance = reach;
	AIBalls.Ang = elevation;
	AIBalls.Dir = heading;
	AIBalls.RawAng = rawAngle;
	AIBalls.Event = "";
	AIBalls.add = "";

	SendMessage(&Sound, "lsllllllfff", MSG_SOUND_PLAY, "cannon", PCM_3D, VOLUME_FX, false, false, false, 0, x, y, z);
	if (sti(character.index) == sti(Player.index)) { shots++; }
}

// "illffflf": the ship hit, the owner of the ball, the index of the ship hit and the point.
void Sea_HullHit()
{
	aref ship = GetEventData();
	int owner = GetEventData();
	int index = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	SendMessage(&Particles, "lsffffffl", PS_CREATE, "explosion", x, y, z, 0.0, 0.0, 0.0, 0);
	string hit = "demo\hit1.wav";
	if (rand(1) == 1) { hit = "demo\hit2.wav"; }
	SendMessage(&Sound, "lsllllllfffff", MSG_SOUND_PLAY, hit, PCM_3D, VOLUME_FX, false, false, false, 0,
		x, y, z, 20.0, 500.0);
	if (battleOver || owner == index) { return; }
	if (index == sti(Enemy.index))
	{
		hits++;
		DamageHull(&Enemy, HULL_HIT_DAMAGE, "Попадание! Корпус врага ");
	}
	else
	{
		DamageHull(&Player, HULL_HIT_DAMAGE, "В нас попали! Корпус ");
	}
}

void DamageHull(ref character, float damage, string message)
{
	float hull = stf(character.Ship.HP) - damage;
	if (hull < 0.0) { hull = 0.0; }
	character.Ship.HP = hull;
	Trace("SEA: " + character.id + " hull " + makeint(hull));
	if (hull > 0.0)
	{
		Log(message + makeint(hull) + "%");
		return;
	}
	battleOver = 1;
	// SEA_AI stops steering and firing the ship and sinks it
	SendMessage(&AISea, "la", AI_MESSAGE_CHARACTER_DEAD, character);
	// the navigator paints the wreck grey
	SendMessage(&BattleInterface, "ll", BI_IN_DEAD_SHIP, sti(character.index));
	if (sti(character.index) == sti(Enemy.index))
	{
		Log("Враг тонет! Попаданий " + hits + " из " + shots + ", R — новый бой");
		Trace("SEA: enemy sinks after " + hits + " hits of " + shots + " shots");
		return;
	}
	Log("Мы тонем! R — новый бой");
	Trace("SEA: player sinks");
}

// "llfflfff": touch has pushed a ship off the shore: its index, -1 for the island, the power of the
// blow in knots, how much of it went into sliding along the shore, the hull point and its position.
// It comes every frame the hull grinds on: the damage and the log count only a blow after the ship
// has been clear of the shore for 1.5 s, or a ship the wind keeps pressing on it would sink.
void Sea_ShipIslandCollision()
{
	int index = GetEventData();
	int other = GetEventData();
	float power = abs(GetEventData());
	float slide = abs(GetEventData());
	int point = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	ref character;
	makeref(character, Player);
	if (index == sti(Enemy.index)) { makeref(character, Enemy); }
	if (battleOver || stf(character.Ship.HP) <= 0.0) { return; }
	// still on the shore: Sea_GroundClear waits another 1.5 s
	character.Ship.Touched = 1;
	if (!sti(character.Ship.Grounded) && power > GROUND_MIN_POWER)
	{
		SendMessage(&Particles, "lsffffffl", PS_CREATE, "splash", x, 0.0, z, 0.0, 0.0, 0.0, 0);
		SendMessage(&Sound, "lsllllllfffff", MSG_SOUND_PLAY, "demo\hit2.wav", PCM_3D, VOLUME_FX, false, false, false, 0,
			x, y, z, 20.0, 500.0);
		if (index == sti(Player.index)) { Log("Мы налетели на берег!"); }
		else { Log("Враг налетел на берег!"); }
		Trace("SEA: " + character.id + " strikes the shore at " + makeint(x) + "," + makeint(z) + ", " + power + " kn");
		character.Ship.Grounded = 1;
		character.Ship.Touched = 0;
		PostEvent("Sea_GroundClear", 1500, "l", index);
		DamageHull(character, (1.0 - slide) * power * GROUND_DAMAGE, "Корпус ");
	}
}

void Sea_GroundClear()
{
	int index = GetEventData();
	ref character;
	makeref(character, Player);
	if (index == sti(Enemy.index)) { makeref(character, Enemy); }
	if (sti(character.Ship.Touched))
	{
		character.Ship.Touched = 0;
		PostEvent("Sea_GroundClear", 1500, "l", index);
		return;
	}
	character.Ship.Grounded = 0;
}

// "ll": the depth map under the keel of a ship has changed between deep and shallow water
void Sea_Shallows()
{
	int index = GetEventData();
	int shallow = GetEventData();
	Trace("SEA: " + index + " shallows " + shallow);
	// the keel crosses the edge of the shallows back and forth on the waves: one call in 5 s
	if (index != sti(Player.index) || !shallow || shallowsCalled) { return; }
	Log("Лотовый: мелководье!");
	shallowsCalled = 1;
	PostEvent("Sea_ShallowsClear", 5000);
}

void Sea_ShallowsClear()
{
	shallowsCalled = 0;
}

// "lfff": a ball has hit the island model, who fired it and where
void Sea_IslandHit()
{
	int owner = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	islandHits++;
	SendMessage(&Particles, "lsffffffl", PS_CREATE, "explosion", x, y, z, 0.0, 0.0, 0.0, 0);
	SendMessage(&Sound, "lsllllllfffff", MSG_SOUND_PLAY, "demo\hit1.wav", PCM_3D, VOLUME_FX, false, false, false, 0,
		x, y, z, 20.0, 500.0);
	if (owner == sti(Player.index)) { Log("Наше ядро попало в остров"); }
	Trace("SEA: ball of " + owner + " hits the island");
}

void Sea_WaterHit()
{
	int owner = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	SendMessage(&Particles, "lsffffffl", PS_CREATE, "splash", x, y, z, 0.0, 0.0, 0.0, 0);
	SendMessage(&Sound, "lsllllllfffff", MSG_SOUND_PLAY, "demo\splash.wav", PCM_3D, VOLUME_FX, false, false, false, 0,
		x, y, z, 15.0, 300.0);
}

// The ship asks the script how much a mast is damaged after a touch; it breaks at 1.0.
float Sea_MastDamage()
{
	int touch = GetEventData();
	int mast = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float damage = GetEventData();
	if (touch != SHIP_MAST_TOUCH_BALL) { return damage; }
	return damage + MAST_HIT_DAMAGE;
}

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
	// the entity takes the wind only when it is assigned after its creation (AttributeChanged)
	Weather.Wind.Angle = stf(Weather.Wind.Angle);
	Weather.Wind.Speed = stf(Weather.Wind.Speed);
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
	Sea.Sea2.Amp1 = 1.8;
	Sea.Sea2.AnimSpeed1 = 1.5;
	Sea.Sea2.Scale1 = 0.6;
	Sea.Sea2.MoveSpeed1 = "2.0, 0.0, 0.0";
	Sea.Sea2.Amp2 = 0.6;
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

// The sail entity serves the sails of every ship; the ship type is shared by both brigs. Its sides
// name the label groups of the gun ports in the model: FireDir is the beam of the side (from the
// bow, clockwise), FireZone the arc the guns cover, FireAngMax their highest elevation.
void CreateSail()
{
	CreateEntity(&Sail, "sail");
	LayerAddObject(EXECUTE, &Sail, iShipPriorityExecute + 1);
	LayerAddObject(REALIZE, &Sail, iShipPriorityRealize + 1);
	LayerAddObject(SAILS_TRACE, &Sail, 10);
	LayerAddObject(SEA_REFLECTION2, &Sail, 3);
	SailTextures.normalTex = "ships\brig\sail.tga";

	BaseShip.Name = "Brig";
	BaseShip.Class = 4;
	BaseShip.HP = HULL;
	BaseShip.SP = 100;
	BaseShip.SpeedRate = 12.0;
	BaseShip.TurnRate = 40.0;
	BaseShip.MinCrew = 20;
	BaseShip.MaxCrew = 120;
	BaseShip.Capacity = 1500;
	BaseShip.Weight = 300.0;
	BaseShip.SpeedDependWeight = 0.2;
	BaseShip.SubSeaDependWeight = 0.6;
	BaseShip.TurnDependWeight = 0.2;
	BaseShip.TurnDependSpeed = 0.3;
	BaseShip.WaterLine = 0.0;
	BaseShip.InertiaAccelerationX = 0.2;
	BaseShip.InertiaBrakingX = 2.0;
	BaseShip.InertiaAccelerationY = 6.0;
	BaseShip.InertiaBrakingY = 3.0;
	BaseShip.InertiaAccelerationZ = 4.0;
	BaseShip.InertiaBrakingZ = 3.0;
	BaseShip.Cannons.Borts.cannonl.FireZone = FIRE_ZONE;
	BaseShip.Cannons.Borts.cannonl.FireDir = PI * 1.5;
	BaseShip.Cannons.Borts.cannonl.FireAngMin = -0.1;
	BaseShip.Cannons.Borts.cannonl.FireAngMax = GUN_ELEVATION;
	BaseShip.Cannons.Borts.cannonr.FireZone = FIRE_ZONE;
	BaseShip.Cannons.Borts.cannonr.FireDir = PI * 0.5;
	BaseShip.Cannons.Borts.cannonr.FireAngMin = -0.1;
	BaseShip.Cannons.Borts.cannonr.FireAngMax = GUN_ELEVATION;

	SetEventHandler("SeaGetLayers", "Sea_ShipLayers", 0);
	SetEventHandler("Shp_UpdParams", "Sea_ShipParameters", 0);
	SetEventHandler("GetSailTextureData", "Sea_SailTextures", 0);
}

// The HUD. battle_interface reads its attributes in Init, so they are set before the entity is made.
// Positions are in screen pixels of the 800x600 window; the arcs are in degrees clockwise from the
// bow. The navigator draws the map, the ships on it, the fire zones, the frame, the compass, the
// arcs of the sides, the wind arrow, the speeds and the icons in this order, all turned with the
// heading; the ship panel draws the picture of the ship under its frame and the gauges.
void CreateHud()
{
	DeleteAttribute(&BattleInterface, "");
	BattleInterface.MainChrIndex = sti(Player.index);
	BattleInterface.ShowNavigator = 1;
	// the ship panel is drawn by the command menu: without ShowCommands there is no panel. The key that
	// opens the menu is not mapped, so it stays a panel
	BattleInterface.ShowCommands = 1;
	BattleInterface.MaxWind = 30.0;
	BattleInterface.MaxShipSpeed = 20.0;
	BattleInterface.ShipSpeedScaler = 1.0;

	aref nav;
	makearef(nav, BattleInterface.navigation);
	nav.navigatorWidth = 220;
	nav.navigatorHeight = 220;
	nav.rightPos = 790;
	nav.topPos = 10;
	// make_hud.py leaves the inner 0.35 of the width for the map
	nav.mapRadius = 77;
	nav.horizontRadius = 400;
	nav.minScale = 0.5;
	nav.maxScale = 2.0;
	nav.curScale = 1.0;
	nav.scaleStep = 0.02;
	nav.shipShowRadius = 6.0;
	nav.windWidth = 18;
	nav.windHeight = 144;
	nav.argbSeaColor = argb(255, 22, 56, 82);
	nav.argbFireZoneColor = argb(90, 140, 200, 230);
	nav.argbEnemyShipColor = argb(255, 230, 60, 40);
	nav.argbFrendShipColor = argb(255, 90, 220, 90);
	nav.argbNeutralShipColor = argb(255, 210, 210, 210);
	nav.argbDeadShipColor = argb(255, 90, 90, 90);
	nav.argbReadyCannonColor = argb(255, 90, 220, 90);
	nav.argbChargeCannonColor = argb(255, 230, 170, 40);
	nav.argbDamageCannonColor = argb(255, 200, 40, 30);
	// the sides of the ship: port and starboard, no guns at the bow and the stern
	nav.leftChargeBegAngle = 220;
	nav.leftChargeEndAngle = 320;
	nav.rightChargeBegAngle = 140;
	nav.rightChargeEndAngle = 40;
	nav.forwardChargeBegAngle = 0;
	nav.forwardChargeEndAngle = 0;
	nav.backwardChargeBegAngle = 0;
	nav.backwardChargeEndAngle = 0;
	nav.speedShowFont = "interface_normal";
	nav.fontScale = 0.8;
	// the speeds go in the row of the icons, outside the rim the compass letters turn on
	nav.speedOutYOffset = 118;
	nav.shipSpeedXOffset = 100;
	nav.windSpeedXOffset = -100;
	nav.compasTexture = "hud\compass.tga";
	nav.cannonsTexture = "hud\cannons.tga";
	nav.emptyTexture = "hud\frame.tga";
	nav.windTexture = "hud\wind.tga";
	nav.chargeTexture = "hud\icons.tga";
	nav.chargeTextureGreed = "4,2";
	nav.chargePos = "-58,128";
	nav.chargePictureSize = "36,36";
	nav.sailstateTexture = "hud\icons.tga";
	nav.sailstateTextureGreed = "4,2";
	nav.sailstatePos = "0,128";
	nav.sailstatePictureSize = "36,36";
	nav.windStateTexture = "hud\icons.tga";
	nav.windTextureGreed = "4,2";
	nav.windPos = "58,128";
	nav.windPictureSize = "36,36";

	aref icon;
	makearef(icon, BattleInterface.ShipIcon);
	icon.iconoffset1 = "84,512";
	icon.backtexturename = "hud\panel.tga";
	icon.backuv = "0,0,1,1";
	icon.backoffset = "0,0";
	icon.backiconsize = "128,128";
	icon.shiptexturename = "hud\ship.tga";
	icon.xsize = 1;
	icon.ysize = 1;
	icon.shipoffset = "0,-4";
	icon.shipiconsize = "96,96";
	icon.shipstatetexturename = "hud\state.tga";
	icon.shiphpuv = "0,0,0.5,1";
	icon.shiphpoffset = "-52,0";
	icon.shiphpiconsize = "10,96";
	icon.shipspuv = "0.5,0,1,1";
	icon.shipspoffset = "52,0";
	icon.shipspiconsize = "10,96";
	// no class picture: a size of zero keeps the default 128x128 square from being drawn
	icon.shipclasstexturename = "hud\state.tga";
	icon.shipclassuv = "0,0,0,0";
	icon.shipclassoffset = "0,0";
	icon.shipclassiconsize = "0,0";
	icon.sailorfontid = "interface_normal";
	icon.sailorfontcolor = argb(255, 255, 245, 215);
	icon.sailorfontscale = 0.8;
	icon.sailorfontoffset = "0,38";
	icon.shipnamefontid = "interface_normal";
	icon.shipnamefontcolor = argb(255, 255, 220, 140);
	icon.shipnamefontscale = 0.9;
	icon.shipnamefontoffset = "0,-76";

	// the battle border: the HUD frames the screen while an enemy is near enough to stop the ship
	// leaving for the map. The default is a white frame for 1024x768; here a red glow that pulses
	// between the two alphas, from the edges of the screen to 24 px in
	aref border;
	makearef(border, BattleInterface.battleborder);
	border.used = 1;
	border.texture = "hud\border.tga";
	border.color1 = argb(200, 255, 255, 255);
	border.color2 = argb(60, 255, 255, 255);
	border.extpos = "0,0,800,600";
	border.intpos1 = "24,24,776,576";
	border.intpos2 = "14,14,786,586";
	border.speed = 1.2;

	// the command menu is always made; idle it would draw an empty 64x64 square
	BattleInterface.CommandList.ActiveIcon_Size = "0,0";

	CreateEntity(&BattleInterface, "battle_interface");
	LayerAddObject(EXECUTE, &BattleInterface, 65534);
	LayerAddObject(REALIZE, &BattleInterface, 65534);

	// the ships are found among the "ship" entities by their index, so they must exist by now
	SendMessage(&BattleInterface, "llaall", BI_IN_CREATE_SHIP, sti(Player.index), &Player, &BaseShip, 1, BI_RELATION_FRIEND);
	SendMessage(&BattleInterface, "llaall", BI_IN_CREATE_SHIP, sti(Enemy.index), &Enemy, &BaseShip, 0, BI_RELATION_ENEMY);

	SetEventHandler("GetCurrentCharge", "Hud_GetCurrentCharge", 0);
	SetEventHandler("ShpSailDamage", "Hud_SailDamage", 0);
}

// Asked by the navigator every frame: the cells of the icons of the charge, the sails and the wind
// and the powder. The array is global: the engine reads it after the function returns.
ref Hud_GetCurrentCharge()
{
	float sails = stf(Player.Ship.SailState);
	int sailIcon = ICON_SAILS_FURLED;
	if (sails > 0.25) { sailIcon = ICON_SAILS_FURLED + 1; }
	if (sails > 0.75) { sailIcon = ICON_SAILS_FURLED + 2; }
	float wind = stf(Weather.Wind.Speed);
	int windIcon = ICON_WIND_CALM;
	if (wind > 5.0) { windIcon = ICON_WIND_CALM + 1; }
	if (wind > 11.0) { windIcon = ICON_WIND_CALM + 2; }
	hudIcons[0] = ICON_BALLS;
	hudIcons[1] = sailIcon;
	hudIcons[2] = windIcon;
	hudIcons[3] = 0;
	hudIcons[4] = 0;
	return &hudIcons;
}

// "lfffl": a ball has torn a sail: the index of the ship, the point and the owner of the ball.
// The panel draws Ship.SP against BaseShip.SP.
void Hud_SailDamage()
{
	int index = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	int owner = GetEventData();
	ref character = &Enemy;
	if (index == sti(Player.index)) { character = &Player; }
	float sails = stf(character.Ship.SP) - 2.0;
	if (sails < 0.0) { sails = 0.0; }
	character.Ship.SP = sails;
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
	ShipCamera.MaxAngleX = -0.2;
	ShipCamera.MinAngleX = -1.4;
	ShipCamera.Distance = 0.5;
	ShipCamera.MinDistance = 25.0;
	ShipCamera.MaxDistance = 1500.0;
	ShipCamera.MinHeightOnSea = 1.0;
	ShipCamera.MaxHeightOnShip = 5.0;
	ShipCamera.InvertMouseX = 1.0;
	ShipCamera.InvertMouseY = -1.0;
	SendMessage(&SeaCameras, "lia", AI_CAMERAS_SET_CAMERA, &ShipCamera, &Player);
	SendMessage(&Scene, "si", "SetActiveCamera", &ShipCamera);
}

void CreateLog()
{
	ScreenLog.Log.left = 16;
	ScreenLog.Log.up = 12;
	// narrower than the screen: the navigator takes the top right corner
	ScreenLog.Log.width = 540;
	ScreenLog.Log.height = 140;
	ScreenLog.Log.font = "interface_normal";
	ScreenLog.Log.fontscale = 1.0;
	ScreenLog.Log.color = argb(0, 255, 245, 215);
	ScreenLog.Log.offsetString = 26;
	ScreenLog.Log.speed = 0.1;
	ScreenLog.Log.color_speed = 0.03;
	CreateEntity(&ScreenLog, "ILogAndActions");
	LayerAddObject(EXECUTE, &ScreenLog, 100);
	LayerAddObject(REALIZE, &ScreenLog, 65535);
	SendMessage(&ScreenLog, "lll", LOG_AND_ACTIONS_INIT, 0, 1);
}

void Log(string text)
{
	SendMessage(&ScreenLog, "lls", LOG_ADD_STRING, 0, text);
}

void Sea_ShipLayers()
{
	aref ship = GetEventData();
	SendMessage(ship, "lll", AI_MESSAGE_SET_LAYERS, EXECUTE, REALIZE);
}

// "lf": the sails of a ship have changed: SEA_AI sets them for the enemy, the keys for the player.
// The top speed is scaled by the sails in the ship; the turn rate is given here.
void Sea_ShipParameters()
{
	int index = GetEventData();
	float sails = GetEventData();
	float turn = stf(BaseShip.TurnRate) / 160.0 * (0.4 + 0.6 * sails);
	if (index == sti(Player.index))
	{
		Player.Ship.SailState = sails;
		Player.Ship.MaxSpeedZ = stf(BaseShip.SpeedRate);
		Player.Ship.MaxSpeedY = turn;
		return;
	}
	// the enemy sails a little slower than the player, who can run or close in
	Enemy.Ship.MaxSpeedZ = ENEMY_SPEED;
	Enemy.Ship.MaxSpeedY = turn;
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

// called by menu.c for the controls pressed while the scene is shown
void Scene_Control(string control)
{
	if (control == "Sea_Fire" && !battleOver)
	{
		int before = playerBroadsides;
		SendMessage(&AISea, "lal", AI_MESSAGE_CANNON_FIRE, &Player, 1);
		if (playerBroadsides == before) { Log("Ни один заряженный борт не смотрит на врага"); }
	}
	if (control == "Sea_NewBattle") { Sea_NewBattle(); }
}
