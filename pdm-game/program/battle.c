// The sea battle (П4): the ships of the sea go to SEA_AI, as in the enemy ship demo (engine demos/ai-ship).
// SEA_AI steers the enemy, aims and loads the guns of both ships; the guns are the labels of the hull
// (tools/pdm_ship.py: a label per Cannon item of DESC\<ship>.def in the group of its side). The hull
// points are the hitpoint of WORLDS\Ships.idf, the guns the cannon of the ship (weapon_type, a line of
// cannons.idf): its reload time, range and damage. At zero the ship is reported dead to SEA_AI and sinks.
// F fires the sides that bear on the enemy (ours: the original fires by the toolbar).
// SCENE=battle starts at sea at the island of the hero with an enemy ahead; TOWN_AUTO=7 fires by itself
// until the enemy sinks and quits. Within BOARD_DISTANCE the enemy can be boarded (boarding.c).

// shared/sea_ai/script_defines.h
#define AI_MESSAGE_ADD_SHIP 51001
#define AI_MESSAGE_CANNON_FIRE 51002
#define AI_MESSAGE_SET_CAMERAS_ATTRIBUTE 51004
#define AI_MESSAGE_GROUP_SET_XYZ_AY 51010
#define AI_MESSAGE_SHIP_SET_TASK 51011
#define AI_MESSAGE_GROUP_SET_COMMANDER 51022
#define AI_MESSAGE_CHARACTER_DEAD 51026
#define AITASK_ATTACK 1
#define AITASK_ABORDAGE 5
#define PRIMARY_TASK 0
#define RELATION_FRIEND 1
#define RELATION_ENEMY 3
#define SHIP_MAST_TOUCH_BALL 2
// shared/battle_interface/msg_control.h
#define BI_IN_DEAD_SHIP 46009
#define BI_RELATION_ENEMY 0
// "lsffffffl": name, position, angles, lifetime in ms (0 burns until the system ends itself)
#define PS_CREATE 10000
// sound_service/include/sound_defines.h
#define PCM_3D 1
#define BATTLE_PI 3.14159265

// the pirate of the first battle: a sloop against the pink of the hero (ours)
#define BATTLE_ENEMY "Umberto__Lump_"
#define BATTLE_FIRE_KEY 70
// the enemy appears this far ahead of the hero, coming at him
#define BATTLE_ENEMY_DISTANCE 120.0
#define BATTLE_ATTACK_DISTANCE 50.0
// the guns of a side fire within this angle around its beam, the chasers of the bow and the stern
// within a narrower one; the highest elevation of the guns
#define BATTLE_FIRE_ZONE 1.4
#define BATTLE_CHASE_ZONE 0.6
#define BATTLE_GUN_ELEVATION 0.2
// cannons.idf in game units (ours): firerange 12.5 .. 14 times this is the reach in m, the reload
// time in s of the original is long for a battle of a few minutes, the damage is per ball
#define BATTLE_RANGE_SCALE 8.0
#define BATTLE_RELOAD_SCALE 0.25
#define BATTLE_DAMAGE_SCALE 10.0
#define BATTLE_GRAVITY 9.81
// the guns of a broadside go off one after another within this time; the aim point is scattered
// around the target in a circle growing with the distance
#define BATTLE_FIRE_SPREAD 0.6
#define BATTLE_SCATTER 0.04
#define BATTLE_MAST_HIT_DAMAGE 0.34
// TOWN_AUTO=7 and 8: SEA_AI sails and fires the hero too (Sea_AddShip leaves him no MainCharacter); the
// autotest quits this long after a ship sinks
#define BATTLE_AUTO_EXIT_MS 8000
// the enemy can be boarded this close (ours, boarding.c); SEA_AI brings the hero to BOARD_APPROACH of it
#define BOARD_DISTANCE 40.0
#define BOARD_APPROACH 25.0
// "Плыть к" puts the hero this far abeam of the enemy, within BOARD_DISTANCE (ours)
#define BATTLE_SAIL_TO 30.0
#define MSG_SHIP_TELEPORT 50317

// steers the enemy, aims and loads the guns of every ship
object AISea;
// what SEA_AI reads about the camera: OutsideCamera aims the guns of the hero at the enemy, not along the view
object AICameras;
object AIBalls;
object Particles;
bool battleOver = false;
int battleEnemy = -1;
int battleShots = 0;
int battleHits = 0;
int battleBroadsides = 0;

// SCENE=battle: at sea by the island of the hero, the enemy coming
void Battle_Start()
{
	seaBattle = true;
	Sea_Start(PlayerCard.address.island);
}

// SEA_AI before the first ship, AIBalls after SEA_AI (it takes the renderer from its helper)
void Battle_Create()
{
	battleOver = false;
	battleEnemy = -1;
	battleShots = 0;
	battleHits = 0;
	battleBroadsides = 0;
	CreateEntity(&Particles, "particles");
	CreateEntity(&AISea, "SEA_AI");
	LayerAddObject(EXECUTE, &AISea, 0);
	LayerAddObject(REALIZE, &AISea, 0);
	AICameras.Crosshair.OutsideCamera = 1;
	SendMessage(&AISea, "la", AI_MESSAGE_SET_CAMERAS_ATTRIBUTE, &AICameras);

	CreateEntity(&AIBalls, "AIBalls");
	LayerAddObject(EXECUTE, &AIBalls, 10);
	LayerAddObject(REALIZE, &AIBalls, 10);
	// the ball sprite and the shot holes of the battle demo (make_battle.py)
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

	SetEventHandler("Shp_HullHit", "Battle_HullHit", 0);
	SetEventHandler("Ball_WaterHit", "Battle_WaterHit", 0);
	SetEventHandler("ShpMastDamage", "Battle_MastDamage", 0);
	// SEA_AI asks these and reads the answer: without a handler it reads nothing and asserts
	SetEventHandler("GetRelationEvent", "Battle_Relation", 0);
	SetEventHandler("Shp_GetCurBallsNum", "Battle_BallsNum", 0);
	SetEventHandler("CannGRTime", "Battle_ReloadTime", 0);
	SetEventHandler("CannGFTime", "Battle_FireDelay", 0);
	SetEventHandler("CannGFHeight", "Battle_FireHeight", 0);
	SetEventHandler("CannLoad", "Battle_CannonLoad", 0);
	SetEventHandler("ShpGetBortFireDelta", "Battle_FireScatter", 0);
	// and calls these back
	SetEventHandler("CannFire", "Battle_CannonFire", 0);
	SetEventHandler("Ship_Bort_Fire", "Battle_BroadsideFired", 0);
	SetEventHandler("Shp_BortReloaded", "Battle_BroadsideReloaded", 0);
	SetEventHandler("Battle_AutoExit", "Battle_AutoExit", 0);
	SetEventHandler("Board_Start", "Board_Start", 0);
	SetEventHandler("Battle_SailTo", "Battle_SailTo", 0);
	SetEventHandler("Battle_SailToCheck", "Battle_SailToCheck", 0);
	MapKey("Battle_Fire", BATTLE_FIRE_KEY);
}

// deleting SEA_AI deletes its ships and their entities
void Battle_Release()
{
	if (!seaBattle) { return; }
	seaBattle = false;
	DelEventHandler("Shp_HullHit", "Battle_HullHit");
	DelEventHandler("Ball_WaterHit", "Battle_WaterHit");
	DelEventHandler("ShpMastDamage", "Battle_MastDamage");
	DelEventHandler("GetRelationEvent", "Battle_Relation");
	DelEventHandler("Shp_GetCurBallsNum", "Battle_BallsNum");
	DelEventHandler("CannGRTime", "Battle_ReloadTime");
	DelEventHandler("CannGFTime", "Battle_FireDelay");
	DelEventHandler("CannGFHeight", "Battle_FireHeight");
	DelEventHandler("CannLoad", "Battle_CannonLoad");
	DelEventHandler("ShpGetBortFireDelta", "Battle_FireScatter");
	DelEventHandler("CannFire", "Battle_CannonFire");
	DelEventHandler("Ship_Bort_Fire", "Battle_BroadsideFired");
	DelEventHandler("Shp_BortReloaded", "Battle_BroadsideReloaded");
	DelEventHandler("Battle_AutoExit", "Battle_AutoExit");
	DelEventHandler("Board_Start", "Board_Start");
	DelEventHandler("Battle_SailTo", "Battle_SailTo");
	DelEventHandler("Battle_SailToCheck", "Battle_SailToCheck");
	DeleteClass(&AIBalls);
	DeleteClass(&AISea);
	DeleteClass(&Particles);
}

// The sides of the type: the label groups of pdm_ship.py. FireDir is the beam of the side from the
// bow, clockwise; a side without labels on the hull has no guns.
void Battle_SetBorts(ref type)
{
	Battle_SetBort(type, "cannonf", 0.0, BATTLE_CHASE_ZONE);
	Battle_SetBort(type, "cannonr", BATTLE_PI * 0.5, BATTLE_FIRE_ZONE);
	Battle_SetBort(type, "cannonb", BATTLE_PI, BATTLE_CHASE_ZONE);
	Battle_SetBort(type, "cannonl", BATTLE_PI * 1.5, BATTLE_FIRE_ZONE);
}

void Battle_SetBort(ref type, string bort, float dir, float zone)
{
	type.Cannons.Borts.(bort).FireZone = zone;
	type.Cannons.Borts.(bort).FireDir = dir;
	type.Cannons.Borts.(bort).FireAngMin = -0.1;
	type.Cannons.Borts.(bort).FireAngMax = BATTLE_GUN_ELEVATION;
}

// the cannon of a ship: weapon_type of its card is the line of cannons.idf, the first where there is no such line
int Battle_CannonLine(int i)
{
	int line = 0;
	string shipKey = "";
	if (CheckAttribute(&SeaShips[i], "ship_key")) { shipKey = SeaShips[i].ship_key; }
	if (shipKey != "" && CheckAttribute(&PdmShips, shipKey + ".weapon_type")) { line = sti(PdmShips.(shipKey).weapon_type); }
	if (line < 0 || line >= GetAttributesNum(&PdmCannons)) { line = 0; }
	return line;
}

// A ship of SEA_AI: a group of its own placed where the ship starts, the guns of its cannon. The
// muzzle speed gives the reach of the cannon at the highest elevation (AICannon::CalcMaxFireDistance).
void Battle_AddShip(int i, float x, float z, float ay)
{
	if (!IsEntity(&AISea)) { Battle_Create(); }
	string group = "BattleGroup" + i;
	aref cannon = GetAttributeN(&PdmCannons, Battle_CannonLine(i));
	float reach = stf(cannon.firerange) * BATTLE_RANGE_SCALE;
	SeaShips[i].SeaAI.Group.Name = group;
	SeaShips[i].Ship.HP = sti(SeaShipTypes[i].HP);
	SeaShips[i].Ship.Cannons.Type = 0;
	SeaShips[i].Ship.Cannons.SpeedV0 = sqrt(reach * BATTLE_GRAVITY / sin(2.0 * BATTLE_GUN_ELEVATION));
	SeaShips[i].Ship.Cannons.Borts = "";
	// under full sail from the start (SHIP::InitSailState): the ships close in at once
	SeaShips[i].Ship.Speed.z = 1.0;
	// SEA_AI reads it once, when the ship is added
	SeaShips[i].SeaAI.Init.AttackDistance = BATTLE_ATTACK_DISTANCE;
	SeaShips[i].SeaAI.Init.AbordageDistance = BOARD_APPROACH;
	SeaShips[i].Ship.Mode = "war";
	Battle_SetBorts(&SeaShipTypes[i]);
	SendMessage(&AISea, "lsa", AI_MESSAGE_GROUP_SET_COMMANDER, group, &SeaShips[i]);
	SendMessage(&AISea, "lsffff", AI_MESSAGE_GROUP_SET_XYZ_AY, group, x, 0.0, z, ay);
	CreateEntity(&SeaShips[i], "ship");
	SendMessage(&AISea, "liaa", AI_MESSAGE_ADD_SHIP, &SeaShips[i], &SeaShips[i], &SeaShipTypes[i]);
}

// After the hero: the enemy ahead of him, heading at him, with the task to attack; isDone after the last
// ship settles the start positions
void Battle_AddEnemy(float x, float z, float ay)
{
	// an attribute name in .(...) has to be a variable
	string enemyKey = BATTLE_ENEMY;
	aref card;
	makearef(card, PdmCharacters.(enemyKey));
	string shipKey = card.ship_key;
	string typeKey = PdmShips.(shipKey).type_key;
	float ex = x + sin(ay) * BATTLE_ENEMY_DISTANCE;
	float ez = z + cos(ay) * BATTLE_ENEMY_DISTANCE;
	battleEnemy = Sea_AddShip(card, typeKey, ex, ez, ay + BATTLE_PI);
	AISea.isDone = "";
	// on the navigator of the toolbar
	SeaShips[battleEnemy].Ship.Name = PdmShips.(shipKey).name;
	SeaShips[battleEnemy].Ship.SP = 100;
	SeaShipTypes[battleEnemy].SP = 100;
	SendMessage(&BattleInterface, "llaall", BI_IN_CREATE_SHIP, battleEnemy, &SeaShips[battleEnemy], &SeaShipTypes[battleEnemy], 0, BI_RELATION_ENEMY);
	SendMessage(&AISea, "lllaa", AI_MESSAGE_SHIP_SET_TASK, AITASK_ATTACK, PRIMARY_TASK, &SeaShips[battleEnemy], &SeaShips[seaHero]);
	Sound_Music(Battle_Music(sti(card.nation)));
	string report = "PDM: battle, " + card.id + " on " + PdmShips.(shipKey).name + " (" + typeKey + "), hull ";
	report = report + SeaShips[battleEnemy].Ship.HP + " against " + SeaShips[seaHero].Ship.HP;
	Trace(report);
	Hud_Log(card.name + " атакует!");
	if (TownAuto == 7) { SendMessage(&AISea, "lllaa", AI_MESSAGE_SHIP_SET_TASK, AITASK_ATTACK, PRIMARY_TASK, &SeaShips[seaHero], &SeaShips[battleEnemy]); }
	// TOWN_AUTO=8: the ships sail to each other to board (boarding.c)
	if (TownAuto == 8)
	{
		SendMessage(&AISea, "lllaa", AI_MESSAGE_SHIP_SET_TASK, AITASK_ABORDAGE, PRIMARY_TASK, &SeaShips[seaHero], &SeaShips[battleEnemy]);
		SendMessage(&AISea, "lllaa", AI_MESSAGE_SHIP_SET_TASK, AITASK_ABORDAGE, PRIMARY_TASK, &SeaShips[battleEnemy], &SeaShips[seaHero]);
	}
	// TOWN_AUTO=9: the hero gives "Плыть к" and is brought to the enemy
	if (TownAuto == 9) { PostEvent("Battle_SailTo", 1000); }
}

// the battle music of mmusic.ini by the nation of the enemy (nations.idf: england, pirate, france, spain)
string Battle_Music(int nation)
{
	if (nation == 0) { return "ebattle"; }
	if (nation == 2) { return "fbattle"; }
	if (nation == 3) { return "sbattle"; }
	return "cbattle";
}

void Battle_Control(string control)
{
	if (control != "Battle_Fire" || !seaBattle || battleOver) { return; }
	int before = battleBroadsides;
	SendMessage(&AISea, "lal", AI_MESSAGE_CANNON_FIRE, &SeaShips[seaHero], 1);
	if (battleBroadsides == before) { Hud_Log("Ни один заряженный борт не смотрит на врага"); }
}

// "Плыть к" (SQUAD_CONTROL.dll sail_to) moves the ship of the hero at once (MSG_SHIP_TELEPORT): it is put
// abeam of the enemy, on the side it came from, at BATTLE_SAIL_TO m, heading as the enemy (ours), so the enemy
// is within boarding
bool Battle_CanSailTo()
{
	return seaBattle && !battleOver && battleEnemy >= 0 && !Board_Can();
}

void Battle_SailTo()
{
	if (!Battle_CanSailTo()) { return; }
	float ex = stf(SeaShips[battleEnemy].ship.pos.x);
	float ez = stf(SeaShips[battleEnemy].ship.pos.z);
	float ay = stf(SeaShips[battleEnemy].ship.ang.y);
	// the starboard of the enemy is (cos ay, -sin ay); the hero stays on his side of it
	float rx = cos(ay);
	float rz = -sin(ay);
	float side = BATTLE_SAIL_TO;
	if ((stf(SeaShips[seaHero].ship.pos.x) - ex) * rx + (stf(SeaShips[seaHero].ship.pos.z) - ez) * rz < 0.0) { side = -side; }
	SendMessage(&SeaShips[seaHero], "lfff", MSG_SHIP_TELEPORT, ex + rx * side, ez + rz * side, ay);
	Hud_Log(PdmHud.note.sail_to + " " + SeaShips[battleEnemy].Ship.Name);
	Trace("PDM: battle, sail to " + SeaShips[battleEnemy].id + ", " + side + " m abeam");
	if (TownAuto == 9) { PostEvent("Battle_SailToCheck", 500); }
}

// TOWN_AUTO=9: the frame after the teleport the ships write their places again
void Battle_SailToCheck()
{
	Trace("PDM: battle, sail to done, boarding " + Board_Can());
	PostEvent("Battle_AutoExit", BATTLE_AUTO_EXIT_MS);
}

void Battle_AutoExit()
{
	Trace("PDM: autotest done, battle");
	ExitProgram();
}

// the hero and the enemy are enemies, the rest friends
int Battle_Relation()
{
	int index1 = GetEventData();
	int index2 = GetEventData();
	int heroes = 0;
	if (index1 == seaHero) { heroes++; }
	if (index2 == seaHero) { heroes++; }
	if (heroes == 1) { return RELATION_ENEMY; }
	return RELATION_FRIEND;
}

// the balls in the hold; a side fires only when there is a ball for each of its guns
// the hero fires what is in his hold (the panel of the charges counts it down), the enemy never runs out (ours)
int Battle_BallsNum()
{
	aref character = GetEventData();
	if (sti(character.index) == seaHero) { return Hud_ChargeLeft(); }
	return 100;
}

float Battle_ReloadTime()
{
	aref character = GetEventData();
	aref cannon = GetAttributeN(&PdmCannons, Battle_CannonLine(sti(character.index)));
	return stf(cannon.reloadtime) * BATTLE_RELOAD_SCALE + frnd();
}

// the delay between the order and the shot, different for every gun: the broadside rolls along
float Battle_FireDelay()
{
	aref character = GetEventData();
	return frnd() * BATTLE_FIRE_SPREAD;
}

// the guns aim this high above the waterline of the target: at the hull
float Battle_FireHeight()
{
	aref character = GetEventData();
	aref enemy = GetEventData();
	return 1.5;
}

// 1: a ball is rammed home
int Battle_CannonLoad()
{
	aref character = GetEventData();
	return 1;
}

float Battle_FireScatter()
{
	aref character = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float dx = x - stf(character.ship.pos.x);
	float dz = z - stf(character.ship.pos.z);
	return BATTLE_SCATTER * sqrt(dx * dx + dz * dz);
}

// "lisffffff": a side has been ordered to fire
void Battle_BroadsideFired()
{
	int index = GetEventData();
	int ship = GetEventData();
	string bort = GetEventData();
	if (index == seaHero) { battleBroadsides++; }
	Trace("PDM: battle, " + index + " fires " + bort);
}

// "as": the guns of a side are loaded again; the gunner of the original reports the side
void Battle_BroadsideReloaded()
{
	aref character = GetEventData();
	string bort = GetEventData();
	if (sti(character.index) != seaHero || battleOver) { return; }
	if (bort == "cannonl") { Battle_Sound("gunreadyleft", 0.0, 0.0, 0.0, false); }
	if (bort == "cannonr") { Battle_Sound("gunreadyright", 0.0, 0.0, 0.0, false); }
}

// a sound of the original by its alias (resource/ini/aliases/pdm.ini) or file, at a point of the sea or,
// not placed, at the camera
void Battle_Sound(string alias, float x, float y, float z, bool placed)
{
	if (!placed)
	{
		SendMessage(&Sound, "lslllll", MSG_SOUND_PLAY, alias, PCM_STEREO, VOLUME_FX, false, false, false, 0);
		return;
	}
	SendMessage(&Sound, "lsllllllfffff", MSG_SOUND_PLAY, alias, PCM_3D, VOLUME_FX, false, false, false, 0,
		x, y, z, 20.0, 600.0);
}

// "afffffffff": one gun goes off at the heading and elevation SEA_AI has aimed it; the ball goes to AIBalls
void Battle_CannonFire()
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

	if (sti(character.index) == seaHero) { Hud_SpendCharge(); }
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

	Battle_Sound("sfire", x, y, z, true);
	if (sti(character.index) == seaHero) { battleShots++; }
}

// "illffflf": the ship hit, the owner of the ball, the index of the ship hit and the point
void Battle_HullHit()
{
	aref ship = GetEventData();
	int owner = GetEventData();
	int index = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	SendMessage(&Particles, "lsffffffl", PS_CREATE, "explosion", x, y, z, 0.0, 0.0, 0.0, 0);
	Battle_Sound("ship_damage", x, y, z, true);
	if (battleOver || owner == index) { return; }
	if (owner == seaHero) { battleHits++; }
	aref cannon = GetAttributeN(&PdmCannons, Battle_CannonLine(owner));
	int hull = sti(SeaShips[index].Ship.HP) - makeint(stf(cannon.damage) * BATTLE_DAMAGE_SCALE);
	if (hull < 0) { hull = 0; }
	SeaShips[index].Ship.HP = hull;
	Trace("PDM: battle, " + SeaShips[index].id + " hull " + hull);
	if (hull > 0) { return; }
	battleOver = true;
	// SEA_AI stops steering and firing the ship and sinks it
	SendMessage(&AISea, "la", AI_MESSAGE_CHARACTER_DEAD, &SeaShips[index]);
	SendMessage(&BattleInterface, "ll", BI_IN_DEAD_SHIP, index);
	Battle_Sound("ship_sink", x, y, z, true);
	if (index == seaHero)
	{
		Sound_Music("die");
		Hud_Log("Наш корабль тонет!");
		Trace("PDM: battle, the hero sinks");
		if (TownAuto == 7 || TownAuto == 8) { PostEvent("Battle_AutoExit", BATTLE_AUTO_EXIT_MS); }
		return;
	}
	Sound_Music("win");
	Hud_Log("Враг идёт ко дну! Попаданий " + battleHits + " из " + battleShots);
	Trace("PDM: battle, the enemy sinks after " + battleHits + " hits of " + battleShots + " shots");
	if (TownAuto == 7 || TownAuto == 8) { PostEvent("Battle_AutoExit", BATTLE_AUTO_EXIT_MS); }
}

void Battle_WaterHit()
{
	int owner = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	SendMessage(&Particles, "lsffffffl", PS_CREATE, "splash", x, y, z, 0.0, 0.0, 0.0, 0);
	string splash = "pdm\_splash0.wav";
	if (rand(1) == 1) { splash = "pdm\_splash1.wav"; }
	Battle_Sound(splash, x, y, z, true);
}

// The ship asks the script how much a mast is damaged after a touch; it breaks at 1.0
float Battle_MastDamage()
{
	int touch = GetEventData();
	int mast = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float damage = GetEventData();
	if (touch != SHIP_MAST_TOUCH_BALL) { return damage; }
	if (damage + BATTLE_MAST_HIT_DAMAGE >= 1.0) { Battle_Sound("mast_fall", x, y, z, true); }
	return damage + BATTLE_MAST_HIT_DAMAGE;
}
