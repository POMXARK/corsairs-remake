// The fort guns (П5): an island with Cannon items in its DEF has the model of its fort, <Name>_fort.gm, with
// a label cannon<N> per gun (tools/pdm_island.py). In a sea battle AIFort of SEA_AI aims each gun at the
// nearest ship of an enemy within reach and fires it through Battle_CannonFire, as the guns of the ships;
// a ball that hits the fort puts the guns near the hit out of action. The island draws the fort itself (it
// is in <Name>.gm), the fort model here is only aimed from and traced by the balls.
// A fort is the enemy of the ships of the other nations (ours: the diplomacy of the original is not
// ported) and never falls.

// shared/sea_ai/script_defines.h
#define AI_MESSAGE_ADD_FORT 51005
#define AI_MESSAGE_FORT_HIT 51008
#define AI_MESSAGE_UPDATE_RELATIONS 51016
#define FORT_NORMAL 0
// shared/messages.h
#define MSG_MODEL_LOAD_GEO 20500
// the fort is the character of this index to SEA_AI and AIBalls, past the ships of SeaShips
#define FORT_INDEX 100
// the guns of the forts outrange the ships (ours): the reach in m at the highest elevation
#define FORT_REACH 500.0
// a hit within this many m of a gun damages it by FORT_GUN_HIT; at 1.0 it is out (ours)
#define FORT_HIT_DISTANCE 10.0
#define FORT_GUN_HIT 0.5
// TOWN_AUTO=11: the hero on a ship of the first rank (ours, the test only)
#define FORT_AUTO_SHIP "manowar"
#define FORT_AUTO_CAMERA_OFFSET 0.5
#define FORT_AUTO_CAMERA_DISTANCE 0.3

object AIFort;
object ShipLights;
// the model of the fort, the character of the fort and the label of the fort AIFort reads (x, z, fort.model,
// fort.locators)
object FortModel;
object FortCharacter;
object FortLabel;
bool fortActive = false;
// TOWN_AUTO=11: the fort is the enemy of the hero, whatever the nations
bool fortAuto = false;
int fortShots = 0;
int fortGunsOut = 0;

// After the ships (they look the lights up when they are created and should not find these); the fort of
// the island at sea, if it has one
void Fort_Create(string islandKey)
{
	if (islandKey == "" || !CheckAttribute(&PdmIslands, islandKey + ".fort")) { return; }
	string model = PdmIslands.(islandKey).model;
	string dir = "islands\" + model;
	fortShots = 0;
	fortGunsOut = 0;
	// AIFort asks for it and adds the fort to its lights; there are no light types, so none are made
	CreateEntity(&ShipLights, "ShipLights");
	CreateEntity(&AIFort, "AIFort");
	LayerAddObject(EXECUTE, &AIFort, 2);
	AIFort.MinCannonDamageDistance = FORT_HIT_DISTANCE;
	Island.filespath.models = dir;
	CreateEntity(&FortModel, "MODELR");
	SendMessage(&FortModel, "ls", MSG_MODEL_LOAD_GEO, dir + "\" + PdmIslands.(islandKey).fort);

	DeleteAttribute(&FortLabel, "");
	FortLabel.x = PdmIslands.(islandKey).fort_x;
	FortLabel.z = PdmIslands.(islandKey).fort_z;
	FortLabel.fort.model = PdmIslands.(islandKey).fort;
	FortLabel.fort.locators = PdmIslands.(islandKey).fort;

	DeleteAttribute(&FortCharacter, "");
	FortCharacter.id = "fort_" + islandKey;
	FortCharacter.index = FORT_INDEX;
	FortCharacter.nation = sti(PdmIslands.(islandKey).nation);
	// AIFort fires only in this mode
	FortCharacter.Fort.Mode = FORT_NORMAL;
	// cannon, culverin, mortar: the labels of the first kind only, -1 has none
	FortCharacter.Fort.Cannons.Type.1 = 0;
	FortCharacter.Fort.Cannons.Type.2 = -1;
	FortCharacter.Fort.Cannons.Type.3 = -1;
	FortCharacter.Ship.Cannons.Type = 0;
	FortCharacter.Ship.Cannons.SpeedV0 = sqrt(FORT_REACH * BATTLE_GRAVITY / sin(2.0 * BATTLE_GUN_ELEVATION));
	FortCharacter.Ship.Name = PdmIslands.(islandKey).label;

	SetEventHandler("FortCreate", "Fort_Created", 0);
	SetEventHandler("FortCDamage", "Fort_GunDamage", 0);
	SetEventHandler("Ball_FortHit", "Fort_Hit", 0);
	fortActive = true;
	// no blots on the fort: the message to a missing entity is dropped
	SendMessage(&AIFort, "laaaii", AI_MESSAGE_ADD_FORT, &Island, &FortLabel, &FortCharacter, &FortModel, &FortModel);
	SendMessage(&AISea, "l", AI_MESSAGE_UPDATE_RELATIONS);
}

void Fort_Release()
{
	if (!fortActive) { return; }
	Fort_Report();
	fortActive = false;
	fortAuto = false;
	DelEventHandler("FortCreate", "Fort_Created");
	DelEventHandler("FortCDamage", "Fort_GunDamage");
	DelEventHandler("Ball_FortHit", "Fort_Hit");
	DeleteClass(&AIFort);
	DeleteClass(&FortModel);
	DeleteClass(&ShipLights);
}

// the end of the fight with the fort in the log, also from an autotest that quits at sea
void Fort_Report()
{
	if (fortActive) { Trace("PDM: fort, " + fortShots + " shots, " + fortGunsOut + " guns out"); }
}

// "al": the guns found on the model
void Fort_Created()
{
	aref character = GetEventData();
	int guns = GetEventData();
	character.Fort.Cannons.Quantity = guns;
	Trace("PDM: fort of " + character.Ship.Name + ", nation " + character.nation + ", " + guns + " guns");
}

// a fort and a ship are enemies when their nations differ
bool Fort_Enemy(int index)
{
	if (index == FORT_INDEX || index < 0 || index >= seaShipCount) { return false; }
	if (fortAuto && index == seaHero) { return true; }
	return sti(SeaShips[index].nation) != sti(FortCharacter.nation);
}

// "lfff": a ball has hit the fort model; the guns near an enemy hit are damaged (Fort_GunDamage)
void Fort_Hit()
{
	int owner = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	SendMessage(&Particles, "lsffffffl", PS_CREATE, "explosion", x, y, z, 0.0, 0.0, 0.0, 0);
	Battle_Sound("ship_damage", x, y, z, true);
	if (owner == FORT_INDEX || !Fort_Enemy(owner)) { return; }
	SendMessage(&AIFort, "llfff", AI_MESSAGE_FORT_HIT, owner, x, y, z);
}

// "llallfffff": the owner of the ball, the fort, its label, all guns, the guns out, the gun, its distance
// from the hit and its damage; returns the new damage
float Fort_GunDamage()
{
	int owner = GetEventData();
	int fort = GetEventData();
	aref label = GetEventData();
	int guns = GetEventData();
	int out = GetEventData();
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float distance = GetEventData();
	float damage = GetEventData();
	damage = damage + FORT_GUN_HIT;
	if (damage >= 1.0)
	{
		fortGunsOut++;
		Trace("PDM: fort, a gun is out, " + fortGunsOut + " of " + guns);
		if (fortAuto && fortGunsOut >= guns)
		{
			Trace("PDM: fort, all guns out");
			PostEvent("Battle_AutoExit", BATTLE_AUTO_EXIT_MS);
		}
	}
	return damage;
}

// TOWN_AUTO=11: the AI of SEA_AI sails the hero to the fort (AITASK_ATTACK, the attack point off its guns)
// and fires at its guns, the fort fires back; the camera keeps the fort in view past the hero. False when
// the island has no fort
bool Fort_Auto()
{
	if (seaIsland == "" || !CheckAttribute(&PdmIslands, seaIsland + ".fort")) { return false; }
	fortAuto = true;
	Fort_Create(seaIsland);
	SendMessage(&AISea, "lllaa", AI_MESSAGE_SHIP_SET_TASK, AITASK_ATTACK, PRIMARY_TASK, &SeaShips[seaHero], &FortCharacter);
	ShipCamera.Target = -1;
	ShipCamera.TargetX = FortLabel.x;
	ShipCamera.TargetZ = FortLabel.z;
	// the fort is bigger than a ship: further aside, and nearer to the hero, off the rocks of the coast
	ShipCamera.TargetOffset = FORT_AUTO_CAMERA_OFFSET;
	ShipCamera.Distance = FORT_AUTO_CAMERA_DISTANCE;
	ShipCamera.AngleX = BATTLE_AUTO_CAMERA_HEIGHT;
	Sound_Music(Battle_Music(sti(FortCharacter.nation)));
	Trace("PDM: battle, " + SeaShips[seaHero].id + " (" + FORT_AUTO_SHIP + "), hull " + SeaShips[seaHero].Ship.HP + ", against the fort");
	Hud_Log(FortCharacter.Ship.Name + ": форт открывает огонь!");
	return true;
}
