// The sea battle: the player's brig «Ласточка» against the brig «Ворон» at an island, with the HUD
// over it. Built from the engine demos (sea, ship, island, enemy ship, HUD): SEA_AI steers the enemy
// and aims the guns of both, touch keeps the ships off the shore and each other, battle_interface
// draws the navigator and the ship panel. The sea, the sky and the sound are the world's (world.c).
// Space fires the guns that bear, R starts a new battle, Z and X zoom the minimap, Enter after the
// battle goes on over the world map (map.c) after a win, to the port after a loss. B boards a «Ворон» the guns have half wrecked when he is close (deck.c). A/D turn, W/S set and furl the sails, the mouse turns the camera.

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

// shared/battle_interface/msg_control.h
#define BI_IN_CREATE_SHIP 46011
#define BI_IN_DEAD_SHIP 46009
#define BI_RELATION_ENEMY 0
#define BI_RELATION_FRIEND 1
// the cells of hud\icons.tga (make_hud.py)
#define ICON_BALLS 0
#define ICON_SAILS_FURLED 1
#define ICON_WIND_CALM 4
#define ICON_KNIPPELS 7
#define ICON_GRAPES 8

#define PI 3.14159265
// the muzzle speed of a ball in m/s and the highest elevation of the guns: together they give a
// reach of about 250 m (AICannon::CalcMaxFireDistance): after its broadside the enemy may fall
// back well past ATTACK_DISTANCE, a shorter reach leaves the player nothing to fire at
#define BALL_SPEED 80.0
// chain shot and grape shot are lighter and spread: they fly slower and so not as far
// (the reach goes with the square of the speed: about 205 and 180 m against 250)
#define KNIPPELS_SPEED 72.0
#define GRAPES_SPEED 68.0
// the guns aim this high over the waterline of the target: round shot at the hull, chain shot at
// the bulwark under the sails, grape shot at the deck. Aimed higher, at a long distance the balls
// pass over the hull and seldom catch a sail: a chain shot at 6 m hit 0 of 48 times
#define HULL_AIM_HEIGHT 1.5
#define SAILS_AIM_HEIGHT 3.0
#define DECK_AIM_HEIGHT 2.5
// a chain shot through a sail tears this much of the sails, a round shot or grape shot this much
// (a ball passes several sails, each is a hit); a chain shot that hits the hull sweeps the rigging
// over it for KNIPPELS_RIGGING_DAMAGE
#define KNIPPELS_SAIL_DAMAGE 2.5
#define SAIL_HIT_DAMAGE 0.5
#define KNIPPELS_RIGGING_DAMAGE 5.0
// a ship with torn sails keeps this part of her speed at the least
#define TORN_SAILS_SPEED 0.3
// SAIL punches one visible hole per this many torn percent (msg_control.h: the script processing
// message of SAIL, its "RandomSailsDmg" asks evntRandomSailDmg how much a hole takes)
#define SAIL_HOLE_STEP 4.0
#define MSG_SAIL_SCRIPT_PROCESSING 40099
#define GUN_ELEVATION 0.2
#define ATTACK_DISTANCE 110.0
// the guns of a side fire within this angle around its beam
#define FIRE_ZONE 1.4
// the two chasers at the bow and at the stern (make_ship.py) fire in a narrow arc along the keel
#define CHASER_ZONE 0.6
#define RELOAD_TIME 8.0
// the guns of a side (the locators of make_ship.py): a broadside takes this many balls
#define BROADSIDE_GUNS 6
// the guns of a broadside go off one after another within this time
#define FIRE_SPREAD 0.6
// the aim point is scattered around the target in a circle growing with the distance
#define SCATTER 0.04
#define HULL 100
#define HULL_HIT_DAMAGE 4
// the "Raven" is lighter built: two broadsides sink her even when only half of the balls hit
// (6 hits of 12), the battle stays short
#define ENEMY_HIT_DAMAGE 17
// chain shot and grape shot barely scratch the hull; grape shot takes this many sailors more
#define KNIPPELS_HIT_DAMAGE 2
#define GRAPES_HIT_DAMAGE 1
#define GRAPES_CREW_KILL 5
// what is left of a sunk brig when the harbour has raised it and fished the sailors out
#define LOSS_HULL 30
#define LOSS_CREW 40
// a blow on the shore costs this much hull per knot of the impact
#define GROUND_DAMAGE 2.0
// a ship resting on the shore under sail keeps touching it at ~0.5 kn: not a blow
#define GROUND_MIN_POWER 1.0
// touch pushes a ship back where the depth map is this shallow under one point of its hull
#define COLLISION_DEPTH -4.0
#define MAST_HIT_DAMAGE 0.34
#define ENEMY_SPEED 9.0
// B boards «Ворон» when his hull is down to this and he is this close
#define BOARD_HULL 50.0
#define BOARD_DISTANCE 150.0
// what every level of «Ворон» (world.c, Raven_Level) adds: the hull takes this part less of a hit,
// his guns hit harder and reload faster, his crew is bigger and he sails faster
#define RAVEN_LEVEL_HULL 0.2
#define RAVEN_LEVEL_HIT_DAMAGE 0.5
#define RAVEN_LEVEL_RELOAD 0.05
#define RAVEN_LEVEL_CREW 12
#define RAVEN_LEVEL_SPEED 0.4
// the player south of the island, heading for it; the enemy west of the player, within the map of
// the navigator, so the fight starts at once
#define PLAYER_START_X -150.0
#define PLAYER_START_Z -380.0
#define ENEMY_START_X -380.0
#define ENEMY_START_Z -160.0

int iShipPriorityExecute = 2;
int iShipPriorityRealize = 31;

object Sail;
object SeaCameras;
object ShipCamera;
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
// what GetCurrentCharge returns: the icons of the charge, the sails and the wind, the powder, and
// the charges left, printed under the charge icon
int hudIcons[6];

int battleOver = 0;
// the broadsides of the player; Ship_Bort_Fire comes inside the fire message, so a key press that
// does not change it found no side bearing on the enemy
int playerBroadsides = 0;
int shots = 0;
int hits = 0;
int islandHits = 0;
int shallowsCalled = 0;
// the log has told that «Ворон» can be boarded
int boardHinted = 0;

void Sea_MapControls()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	MapKey("Ship_TurnLeft", 65, 0);
	MapKey("Ship_TurnRight", 68, 0);
	MapKey("Ship_SailUp", 87, 0);
	MapKey("Ship_SailDown", 83, 0);
	MapKey("ShipCamera_Turn_H", 256, 0);
	MapKey("ShipCamera_Turn_V", 257, 0);
	MapKey("Sea_Fire", 32, 0);
	MapKey("Sea_ChargeBalls", 49, 0);
	MapKey("Sea_ChargeKnippels", 50, 0);
	MapKey("Sea_ChargeGrapes", 51, 0);
	MapKey("Sea_NewBattle", 82, 0);
	MapKey("Sea_ToPort", 13, 0);
	MapKey("Sea_CameraTarget", 84, 0);
	MapKey("Sea_Board", 66, 0);
	// the right mouse button, held
	MapKey("Sea_Aim", 2, 0);
	// read every frame while held: the minimap zooms smoothly
	MapKey("MiniMapZoomIn", 90, 0);
	MapKey("MiniMapZoomOut", 88, 0);
}

// Out of the harbour: the open sea rises and the battle music comes in. The world (world.c) is
// there already; the island, the ships and the HUD are made here and deleted by Sea_Leave.
void Sea_Enter()
{
	World_Waves(1.8, 0.6, 50.0);
	World_Ambient(0);
	World_Music("music\battle.wav");
	shots = 0;
	hits = 0;
	islandHits = 0;
	CreateIsland();
	CreateSail();
	CreateEffects();
	CreateBattle();
	CreateCamera();
	CreateHud();

	SetEventHandler("Sea_StartBattle", "Sea_StartBattle", 0);
	Log("«Ворон» на западе! Пробел — огонь");
	Raven_Intro();
	Log("Корпус " + shipHull + "%, команда " + shipCrew);
	Log("1 ядра " + shipBalls + ", 2 книппели " + shipKnippels + ", 3 картечь " + shipGrapes);
	Trace("SEA: scene loaded");
}

// The entities go at the end of the frame, so the port is made in the next one (menu.c,
// Game_GoTo). SEA_AI deletes its ships with it.
void Sea_Leave()
{
	Sea_KeepShip();
	DeleteClass(&BattleInterface);
	DeleteClass(&AISea);
	DeleteClass(&Touch);
	DeleteClass(&AIBalls);
	DeleteClass(&Island);
	DeleteClass(&Sail);
	DeleteClass(&ShipCamera);
	DeleteClass(&SeaCameras);
	Trace("SEA: left");
}

// SEA_AI and the cannonballs. AIBalls reads the ball types once, on isDone.
void CreateEffects()
{
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
	// GoodIndex comes back in AIBalls.CurrentBallType while the balls of the type are traced: the
	// hit handlers read it there
	AIBalls.Balls.Knippels.SubTexIndex = 0;
	AIBalls.Balls.Knippels.GoodIndex = CHARGE_KNIPPELS;
	AIBalls.Balls.Knippels.Size = 0.65;
	AIBalls.Balls.Knippels.Weight = 1.0;
	AIBalls.Balls.Grapes.SubTexIndex = 0;
	AIBalls.Balls.Grapes.GoodIndex = CHARGE_GRAPES;
	AIBalls.Balls.Grapes.Size = 0.3;
	AIBalls.Balls.Grapes.Weight = 1.0;
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
	// after the sky and the sea: the aim lines are drawn without the depth test and would be painted over
	LayerAddObject(REALIZE, &AISea, 65531);
}

// SEA_AI and its two groups: the player alone south of the island, the enemy north of it. A
// ship is placed at the position of its group; isDone, after the last ship, settles the start
// positions. The task is given last, when SEA_AI knows both ships.
void CreateBattle()
{
	battleOver = 0;
	boardHinted = 0;
	AICameras.Crosshair.OutsideCamera = 1;
	AICameras.Crosshair.Texture = "demo\ball.tga";
	SendMessage(&AISea, "la", AI_MESSAGE_SET_CAMERAS_ATTRIBUTE, &AICameras);

	PrepareCharacter(&Player, "Player", 0, "PlayerGroup");
	Player.MainCharacter = 1;
	Player.Ship.Name = "Ласточка";
	Player.Ship.HP = shipHull;
	Player.Ship.Crew.quantity = shipCrew;
	Player.Ship.Cannons.SpeedV0 = Charge_Speed(shipCharge);
	PrepareCharacter(&Enemy, "Enemy", 1, "EnemyGroup");
	Enemy.Ship.Name = "Ворон";
	Enemy.Ship.Mode = "war";
	Enemy.Ship.SeaAI.Init.AttackDistance = ATTACK_DISTANCE;
	Enemy.Ship.Crew.quantity = SHIP_CREW + Raven_Level() * RAVEN_LEVEL_CREW;

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
	character.Ship.Torn = 0;
	character.Ship.Holes = 0;
	character.Ship.SailState = 1.0;
	character.Ship.Crew.quantity = SHIP_CREW;
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
	Sea_KeepShip();
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
	Raven_Intro();
	Trace("SEA: new battle");
}

int Sea_Relation()
{
	int index1 = GetEventData();
	int index2 = GetEventData();
	if (index1 == index2) { return RELATION_FRIEND; }
	return RELATION_ENEMY;
}

// the balls in the hold; a side fires only when there is a ball for each of its guns. The enemy
// never runs out.
int Sea_BallsNum()
{
	aref character = GetEventData();
	if (sti(character.index) == sti(Player.index)) { return Charge_Count(shipCharge); }
	return 100;
}

float Charge_Speed(int charge)
{
	if (charge == CHARGE_KNIPPELS) { return KNIPPELS_SPEED; }
	if (charge == CHARGE_GRAPES) { return GRAPES_SPEED; }
	return BALL_SPEED;
}

// 1/2/3: the next broadsides fire this charge; SEA_AI reads the muzzle speed for the reach and the
// aim zone from the character
void Sea_SetCharge(int charge)
{
	shipCharge = charge;
	Player.Ship.Cannons.SpeedV0 = Charge_Speed(charge);
	Log("Заряжаем: " + Charge_Name(charge) + ", в трюме " + Charge_Count(charge));
}

// a short-handed crew loads slower: half the sailors, twice the time
float Sea_ReloadTime()
{
	aref character = GetEventData();
	int crew = sti(character.Ship.Crew.quantity);
	if (crew > SHIP_CREW) { crew = SHIP_CREW; }
	if (crew < SHIP_CREW / 2) { crew = SHIP_CREW / 2; }
	float time = (RELOAD_TIME + frnd() * 1.0) * SHIP_CREW / crew;
	if (sti(character.index) == sti(Enemy.index)) { time = time * (1.0 - RAVEN_LEVEL_RELOAD * Raven_Level()); }
	return time;
}

// the brig after the battle, for the port: a sunk one is raised by the harbour, barely afloat
void Sea_KeepShip()
{
	shipHull = makeint(stf(Player.Ship.HP));
	shipCrew = sti(Player.Ship.Crew.quantity);
	if (lastBattle == "loss")
	{
		shipHull = LOSS_HULL;
		if (shipCrew < LOSS_CREW) { shipCrew = LOSS_CREW; }
	}
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
	if (sti(character.index) != sti(Player.index)) { return HULL_AIM_HEIGHT; }
	if (shipCharge == CHARGE_KNIPPELS) { return SAILS_AIM_HEIGHT; }
	if (shipCharge == CHARGE_GRAPES) { return DECK_AIM_HEIGHT; }
	return HULL_AIM_HEIGHT;
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
	string side = Bort_Name(bort, "правым бортом", "левым бортом", "с носа", "с кормы");
	if (index == sti(Player.index))
	{
		playerBroadsides++;
		Log("Залп " + side + "!");
	}
	else { Log("Враг даёт залп " + side + "!"); }
	Trace("SEA: " + index + " fires " + bort);
}

// "as": the guns of a side are loaded again
void Sea_BroadsideReloaded()
{
	aref character = GetEventData();
	string bort = GetEventData();
	if (sti(character.index) != sti(Player.index) || battleOver) { return; }
	string side = Bort_Name(bort, "Правый борт", "Левый борт", "Нос", "Корма");
	Log(side + " заряжен, " + Charge_Name(shipCharge) + " в трюме: " + Charge_Count(shipCharge));
}

// the name of a side in the log, by the label group of its guns
string Bort_Name(string bort, string right, string left, string bow, string stern)
{
	if (bort == "cannonl") { return left; }
	if (bort == "cannonf") { return bow; }
	if (bort == "cannonb") { return stern; }
	return right;
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

	int charge = CHARGE_BALLS;
	if (sti(character.index) == sti(Player.index)) { charge = shipCharge; }
	AIBalls.Type = Charge_Type(charge);
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
	if (sti(character.index) == sti(Player.index))
	{
		shots++;
		if (Charge_Count(charge) > 0) { Charge_Add(charge, -1); }
	}
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
		// the type of the ball that is traced now (AIBalls sets it for each type)
		int charge = sti(AIBalls.CurrentBallType);
		if (charge == CHARGE_GRAPES)
		{
			KillCrew(&Enemy, GRAPES_CREW_KILL);
			DamageHull(&Enemy, GRAPES_HIT_DAMAGE, "Картечь косит команду! Команда врага " + Enemy.Ship.Crew.quantity + ", корпус ");
			return;
		}
		KillCrew(&Enemy, 0);
		if (charge == CHARGE_KNIPPELS)
		{
			// the chain that hits the hull still sweeps the rigging over it
			TearSails(&Enemy, KNIPPELS_RIGGING_DAMAGE);
			DamageHull(&Enemy, KNIPPELS_HIT_DAMAGE, "Книппели! Паруса врага " + makeint(100.0 - stf(Enemy.Ship.Torn)) + "%, корпус ");
			return;
		}
		DamageHull(&Enemy, ENEMY_HIT_DAMAGE / (1.0 + RAVEN_LEVEL_HULL * Raven_Level()), "Попадание! Корпус врага ");
	}
	else
	{
		KillCrew(&Player, 0);
		DamageHull(&Player, HULL_HIT_DAMAGE + RAVEN_LEVEL_HIT_DAMAGE * Raven_Level(), "В нас попали! Корпус ");
	}
}

// a ball through the hull takes 1 to 3 sailors: the number on the ship panel goes down with the bar
// grape shot takes `extra` more on top
// from the second «Ворон» on: how strong this one is
void Raven_Intro()
{
	int level = Raven_Level();
	if (level == 0) { return; }
	int bounty = Raven_Bounty();
	Log("Пиратов на «Вороне»: " + Enemy.Ship.Crew.quantity + ", награда " + bounty + " песо");
}

void KillCrew(ref character, int extra)
{
	int crew = sti(character.Ship.Crew.quantity) - 1 - rand(2) - extra;
	if (crew < 0) { crew = 0; }
	character.Ship.Crew.quantity = crew;
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
		if (sti(character.index) == sti(Enemy.index) && hull <= BOARD_HULL && !boardHinted)
		{
			boardHinted = 1;
			Log("«Ворон» еле держится! Ближе " + makeint(BOARD_DISTANCE) + " м — B, на абордаж");
		}
		return;
	}
	battleOver = 1;
	// SEA_AI stops steering and firing the ship and sinks it
	SendMessage(&AISea, "la", AI_MESSAGE_CHARACTER_DEAD, character);
	// the navigator paints the wreck grey
	SendMessage(&BattleInterface, "ll", BI_IN_DEAD_SHIP, sti(character.index));
	if (sti(character.index) == sti(Enemy.index))
	{
		// Tom pays for every «Ворон» sunk when the player is back in the port
		lastBattle = "win";
		unpaidGold = unpaidGold + Raven_Bounty();
		unpaidWins++;
		Log("Враг тонет! Попаданий " + hits + " из " + shots + ". Enter — на карту, R — новый бой");
		Trace("SEA: enemy sinks after " + hits + " hits of " + shots + " shots");
		return;
	}
	lastBattle = "loss";
	Log("Мы тонем! Enter — в порт, R — новый бой");
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
	BaseShip.Cannons.Borts.cannonf.FireZone = CHASER_ZONE;
	BaseShip.Cannons.Borts.cannonf.FireDir = 0.0;
	BaseShip.Cannons.Borts.cannonf.FireAngMin = -0.1;
	BaseShip.Cannons.Borts.cannonf.FireAngMax = GUN_ELEVATION;
	BaseShip.Cannons.Borts.cannonb.FireZone = CHASER_ZONE;
	BaseShip.Cannons.Borts.cannonb.FireDir = PI;
	BaseShip.Cannons.Borts.cannonb.FireAngMin = -0.1;
	BaseShip.Cannons.Borts.cannonb.FireAngMax = GUN_ELEVATION;

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
	// the sides of the ship: port and starboard, and the narrow arcs of the bow and stern chasers
	nav.leftChargeBegAngle = 220;
	nav.leftChargeEndAngle = 320;
	nav.rightChargeBegAngle = 140;
	nav.rightChargeEndAngle = 40;
	nav.forwardChargeBegAngle = -25;
	nav.forwardChargeEndAngle = 25;
	nav.backwardChargeBegAngle = 155;
	nav.backwardChargeEndAngle = 205;
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
	nav.chargeTextureGreed = "4,3";
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
	SetEventHandler("evntRandomSailDmg", "Sea_RandomSailHole", 0);
}

// Asked by the navigator every frame: the cells of the icons of the charge, the sails and the wind
// and the powder. The array is global: the engine reads it after the function returns.
ref Hud_GetCurrentCharge()
{
	Sea_KeepSails(&Player);
	Sea_KeepSails(&Enemy);
	float sails = stf(Player.Ship.SailState);
	int sailIcon = ICON_SAILS_FURLED;
	if (sails > 0.25) { sailIcon = ICON_SAILS_FURLED + 1; }
	if (sails > 0.75) { sailIcon = ICON_SAILS_FURLED + 2; }
	float wind = stf(Weather.Wind.Speed);
	int windIcon = ICON_WIND_CALM;
	if (wind > 5.0) { windIcon = ICON_WIND_CALM + 1; }
	if (wind > 11.0) { windIcon = ICON_WIND_CALM + 2; }
	hudIcons[0] = ICON_BALLS;
	if (shipCharge == CHARGE_KNIPPELS) { hudIcons[0] = ICON_KNIPPELS; }
	if (shipCharge == CHARGE_GRAPES) { hudIcons[0] = ICON_GRAPES; }
	hudIcons[1] = sailIcon;
	hudIcons[2] = windIcon;
	hudIcons[3] = 0;
	hudIcons[4] = 0;
	hudIcons[5] = Charge_Count(shipCharge);
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
	float damage = SAIL_HIT_DAMAGE;
	if (sti(AIBalls.CurrentBallType) == CHARGE_KNIPPELS) { damage = KNIPPELS_SAIL_DAMAGE; }
	TearSails(character, damage);
}

// The torn part of the sails is kept in Ship.Torn: SAIL rewrites Ship.SP from the holes of its
// meshes whenever the sails are set or furled (sail.cpp), which would wipe the damage out.
void TearSails(ref character, float damage)
{
	float torn = stf(character.Ship.Torn) + damage;
	if (torn > 100.0) { torn = 100.0; }
	character.Ship.Torn = torn;
	character.Ship.SP = 100.0 - torn;
	// the holes SAIL draws follow the torn part
	int holes = sti(character.Ship.Holes);
	while (holes < makeint(torn / SAIL_HOLE_STEP))
	{
		SendMessage(&Sail, "lslf", MSG_SAIL_SCRIPT_PROCESSING, "RandomSailsDmg", sti(character.index), 1.0);
		holes++;
	}
	character.Ship.Holes = holes;
}

// "lslfflll" from RandomSailsDmg: the whole damage goes into one hole
float Sea_RandomSailHole()
{
	return 1.0;
}

// every frame, after SAIL: the panel draws Ship.SP
void Sea_KeepSails(ref character)
{
	character.Ship.SP = 100.0 - stf(character.Ship.Torn);
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
	// the camera swings behind our ship, away from the enemy, and keeps him in view past the stern
	ShipCamera.Target = sti(Enemy.index);
	SendMessage(&SeaCameras, "lia", AI_CAMERAS_SET_CAMERA, &ShipCamera, &Player);
	SendMessage(&Scene, "si", "SetActiveCamera", &ShipCamera);
}

void Sea_ShipLayers()
{
	aref ship = GetEventData();
	SendMessage(ship, "lll", AI_MESSAGE_SET_LAYERS, EXECUTE, REALIZE);
}

// "lf": the sails of a ship have changed: SEA_AI sets them for the enemy, the keys for the player.
// The top speed is scaled by the sails in the ship; the turn rate is given here.
// torn sails catch less wind: the part of the speed the sails (Ship.SP) still give
float Sea_SailsLeft(ref character)
{
	return TORN_SAILS_SPEED + (1.0 - TORN_SAILS_SPEED) * (100.0 - stf(character.Ship.Torn)) / 100.0;
}

void Sea_ShipParameters()
{
	int index = GetEventData();
	float sails = GetEventData();
	float turn = stf(BaseShip.TurnRate) / 160.0 * (0.4 + 0.6 * sails);
	if (index == sti(Player.index))
	{
		Player.Ship.SailState = sails;
		Player.Ship.MaxSpeedZ = stf(BaseShip.SpeedRate) * Sea_SailsLeft(&Player);
		Player.Ship.MaxSpeedY = turn;
		return;
	}
	// the enemy sails a little slower than the player, who can run or close in
	Enemy.Ship.MaxSpeedZ = (ENEMY_SPEED + RAVEN_LEVEL_SPEED * Raven_Level()) * Sea_SailsLeft(&Enemy);
	Enemy.Ship.MaxSpeedY = turn;
}

ref Sea_SailTextures()
{
	int index = GetEventData();
	return &SailTextures;
}

// called by menu.c for the controls pressed while the sea is shown
void Sea_Control(string control)
{
	if (control == "Sea_Fire" && !battleOver)
	{
		if (Charge_Count(shipCharge) < BROADSIDE_GUNS)
		{
			Log("Кончились " + Charge_Name(shipCharge) + "! 1/2/3 — другой заряд, пополнить — у Тома в порту");
			return;
		}
		int before = playerBroadsides;
		SendMessage(&AISea, "lal", AI_MESSAGE_CANNON_FIRE, &Player, 1);
		if (playerBroadsides == before) { Log("Ни один заряженный борт не смотрит на врага"); }
	}
	if (control == "Sea_NewBattle") { Sea_NewBattle(); }
	if (control == "Sea_ChargeBalls") { Sea_SetCharge(CHARGE_BALLS); }
	if (control == "Sea_ChargeKnippels") { Sea_SetCharge(CHARGE_KNIPPELS); }
	if (control == "Sea_ChargeGrapes") { Sea_SetCharge(CHARGE_GRAPES); }
	// SEA_AI tints the water the balls of the side past the ship can reach
	if (control == "Sea_Aim") { Player.Ship.Cannons.Aim = 1; }
	if (control == "Sea_CameraTarget")
	{
		if (sti(ShipCamera.Target) < 0)
		{
			ShipCamera.Target = sti(Enemy.index);
			Log("Камера следит за врагом");
		}
		else
		{
			ShipCamera.Target = -1;
			Log("Камера свободна");
		}
	}
	// a win sails on over the map to the port, a sunk brig is towed there
	if (control == "Sea_ToPort" && battleOver) { Sea_AfterBattle(); }
	if (control == "Sea_Board" && !battleOver) { Sea_Board(); }
}

// a sunk brig is towed home to Gull Island, the pirates keep her cargo (trade.c)
void Sea_AfterBattle()
{
	if (lastBattle == "win") { Game_GoTo("map"); return; }
	Cargo_Lose();
	portIsland = HOME_ISLAND;
	Map_Home();
	Game_GoTo("port");
}

float Sea_EnemyDistance()
{
	float dx = stf(Enemy.Ship.Pos.x) - stf(Player.Ship.Pos.x);
	float dz = stf(Enemy.Ship.Pos.z) - stf(Player.Ship.Pos.z);
	return sqrt(dx * dx + dz * dz);
}

// The grapnels go over: the battle ends at sea and goes on on the deck of «Ворон» with the pirates
// the guns have left. The ships keep their state (Sea_Leave).
void Sea_Board()
{
	if (stf(Enemy.Ship.HP) > BOARD_HULL)
	{
		Log("«Ворон» ещё крепок: сначала корпус до " + makeint(BOARD_HULL) + "%");
		return;
	}
	float distance = Sea_EnemyDistance();
	if (distance > BOARD_DISTANCE)
	{
		Log("До «Ворона» " + makeint(distance) + " м, нужно ближе " + makeint(BOARD_DISTANCE));
		return;
	}
	battleOver = 1;
	boardEnemyCrew = sti(Enemy.Ship.Crew.quantity);
	Trace("SEA: boarding at " + makeint(distance) + " m, enemy crew " + boardEnemyCrew);
	Game_GoTo("deck");
}

void Sea_ControlUp(string control)
{
	if (control == "Sea_Aim") { Player.Ship.Cannons.Aim = 0; }
}
