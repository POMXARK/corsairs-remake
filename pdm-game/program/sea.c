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
// one px of the map is 50 m of the sea: the scale from the original (WDM_MAP_TO_SEA_SCALE, worldmap_globals.c)
#define SEA_MAP_TO_SEA_SCALE 50.0
// TOWN_AUTO=5 and 6: the ship sails in at about 2 m/s, minutes of sea; the autotest runs the time faster (ours)
#define SEA_AUTO_TIME_SCALE 6.0
// R at sea runs the time x1, x3, x6 in turn, kept from island to island (ours: the islands are km apart)
#define SEA_TIME_KEY 82
#define SEA_TIME_FAST 3.0
float seaTimeScale = 1.0;
bool seaFromMap = false;
bool seaAutoMapDone = false;
bool seaAutoSailDone = false;
// SCENE=battle (battle.c): Sea_AddShip gives the ships to SEA_AI, an enemy comes after the hero
bool seaBattle = false;
// "Плыть к" outside of battle (ours): the NPC ship the button teleports to, made for TOWN_AUTO=14/15
// of the same data card the battle enemy is made of (PdmCharacters, as BATTLE_ENEMY in battle.c)
#define SEA_NPC_KEY "Umberto__Lump_"
#define SEA_NPC_DISTANCE 150.0
// the hero is put this far abeam of the NPC, like BATTLE_SAIL_TO in battle.c
#define SEA_SAIL_TO 30.0
// its index in SeaShips, -1 when there is no NPC ship on this sea
int seaNpc = -1;
// the target "Плыть к" picked for this press: a place of the game data (a ship, the island's fort
// from PdmIslands.(island).fort_x/fort_z, or its harbour where the transition to another location
// happens); "" while the target stayed unset
string seaSailKind = "";
float seaSailTX = 0.0;
float seaSailTZ = 0.0;
string seaSailName = "";
// its index in SeaShips, -1 for a place of the data instead of a hull
int seaSailIndex = -1;
// "Плыть к" works on what stands this far from the hero: a ship, the island's fort, its harbour
#define SEA_SAIL_TO_RADIUS 400.0
// the hero stops this far off a place of the data (fort, harbour), and moored hulls of an island
// stand this far off its port anchor port_x/port_z, at most that many of them
#define SEA_SAIL_TO_PLACE 60.0
#define SEA_PORT_SHIP_DIST 80.0
#define SEA_PORT_SHIPS_MAX 3
// the island Sea_Start was given, for a save (seaIsland is "" where the island has no harbour)
string seaAt = "";
// a loaded game (save.c) puts the ship where it was saved, not at the port
bool seaLoadPos = false;
float seaLoadX = 0.0;
float seaLoadZ = 0.0;
float seaLoadAy = 0.0;

// the NPC ship for "Плыть к" outside of battle (ours): same data card as the battle enemy is made
// of (PdmCharacters), on the line of sight of the hero at SEA_NPC_DISTANCE m, bow to him (as Battle_AddEnemy
// in battle.c puts the enemy)
int Sea_NpcSpawn(float x, float z, float ay)
{
	// an attribute name in .(...) has to be a variable, as battle.c notes
	string npcKey = SEA_NPC_KEY;
	aref card;
	makearef(card, PdmCharacters.(npcKey));
	string shipKey = card.ship_key;
	string typeKey = PdmShips.(shipKey).type_key;
	seaNpc = Sea_AddShip(card, typeKey, x + sin(ay) * SEA_NPC_DISTANCE, z + cos(ay) * SEA_NPC_DISTANCE, ay + BATTLE_PI);
	SeaShips[seaNpc].Ship.Name = PdmShips.(shipKey).name;
	SeaShips[seaNpc].Ship.SP = 100;
	SeaShipTypes[seaNpc].SP = 100;
	Trace("PDM: sea, NPC ship " + card.id + " on " + PdmShips.(shipKey).name + " (" + typeKey + ")");
	return seaNpc;
}

// moored hulls of an island's port (ours, the pattern of the original locations_loader.c:
// LocLoadShips putting a hull for every character of the location at its locators.ships_other;
// the converted data of our remake has no such locators, so the hulls stand by the port anchor
// port_x/port_z of PdmIslands, facing port_ay). A character of the island is one of PdmCharacters
// with address.island of it and a ship_key set; the forts (PdmShips class "fort") are places of
// the sea, not hulls, and are handled as a target by their fort_x/fort_z instead
void Sea_PortShips()
{
	if (seaIsland == "" || seaBattle) { return; }
	aref root;
	makearef(root, PdmCharacters);
	int total = GetAttributesNum(root);
	int made = 0;
	float px = stf(PdmIslands.(seaIsland).port_x);
	float pz = stf(PdmIslands.(seaIsland).port_z);
	float pay = stf(PdmIslands.(seaIsland).port_ay);
	Trace("PDM: sea, port ships of " + seaIsland);
	for (int i = 0; i < total; i++)
	{
		aref child = GetAttributeN(root, i);
		string key = GetAttributeName(child);
		if (key == "") { continue; }
		if (made >= SEA_PORT_SHIPS_MAX) { break; }
		if (PdmCharacters.(key).address.island != seaIsland) { continue; }
		string sk = PdmCharacters.(key).ship_key;
		if (sk == "") { continue; }
		if (PdmShips.(sk).class == "fort") { continue; }
		// an attribute name in .(...) has to be a variable, as battle.c notes
		aref card;
		makearef(card, PdmCharacters.(key));
		string typeKey = PdmShips.(sk).type_key;
		// moored off the port anchor, in a fan to one side of the port head
		float ang = pay + 0.5 + 0.5 * made;
		Sea_AddShip(card, typeKey, px + sin(ang) * SEA_PORT_SHIP_DIST, pz + cos(ang) * SEA_PORT_SHIP_DIST, pay + BATTLE_PI);
		made++;
		Trace("PDM: sea, port ship " + card.id + " on " + sk + " moored at the port of " + seaIsland);
	}
	Trace("PDM: sea, port ships moored: " + made);
}

// the target "Плыть к" picks: the nearest of the NPC hulls on the sea, the fort of the island
// at PdmIslands.(island).fort_x/fort_z and its harbour harbour_x/harbour_z where the transition
// to another location happens — all places of the game data, within SEA_SAIL_TO_RADIUS of the
// hero; true when something was picked (its place and name in seaSail*)
bool Sea_SailToTarget()
{
	// the icon pressed in the hub of "Плыть к": hud.c's Hud_LaunchCommand got (chrIndex, locator
	// name) from the engine's BI_LaunchCommand (battle_command.cpp ExecuteConfirm) and put them
	// into the hudSail* globals; the hub closes the pick, so this hull or place is the target
	if (hudSailTargetChr >= 0 || hudSailTargetName != "")
	{
		int targ = hudSailTargetChr;
		string targName = hudSailTargetName;
		hudSailTargetChr = -1;
		hudSailTargetName = "";
		if (targName == "harbour" && seaIsland != "")
		{
			seaSailIndex = -1;
			seaSailTX = stf(PdmIslands.(seaIsland).harbour_x);
			seaSailTZ = stf(PdmIslands.(seaIsland).harbour_z);
			seaSailKind = "harbour";
			seaSailName = seaIsland + " harbour";
			Trace("PDM: sea, sail to the pressed harbour");
			return true;
		}
		// the fort's and harbour names are ours from Hud_IslandLocators, the hull's icon answers
		// with the character index (our hulls carry no lowercase "name", so the engine puts the
		// index into nTargIndex — battle_command.cpp ExecuteConfirm, the name only if it exists)
		if (targName == "fort" && CheckAttribute(&PdmIslands, seaIsland + ".fort_x"))
		{
			seaSailIndex = -1;
			seaSailTX = stf(PdmIslands.(seaIsland).fort_x);
			seaSailTZ = stf(PdmIslands.(seaIsland).fort_z);
			seaSailKind = "fort";
			seaSailName = seaIsland + " fort";
			Trace("PDM: sea, sail to the pressed fort");
			return true;
		}
		if (targ >= 0 && targ < seaShipCount && targ != seaHero)
		{
			seaSailIndex = targ;
			seaSailTX = stf(SeaShips[targ].ship.pos.x);
			seaSailTZ = stf(SeaShips[targ].ship.pos.z);
			seaSailKind = "ship";
			seaSailName = SeaShips[targ].id;
			Trace("PDM: sea, sail to the pressed hull, index " + targ);
			return true;
		}
		// the icon is gone or stale: fall to the nearest pick below
		Trace("PDM: sea, sail to: pressed icon " + targName + " not resolved, picking the nearest");
	}
	seaSailIndex = -1;
	seaSailKind = "";
	seaSailName = "";
	float hx = stf(SeaShips[seaHero].ship.pos.x);
	float hz = stf(SeaShips[seaHero].ship.pos.z);
	float dx = 0.0;
float dz = 0.0;
float d2 = 0.0;
	// reused by the hull, the fort and the harbour below, pdmscript keeps names at function level
	 float best = SEA_SAIL_TO_RADIUS * SEA_SAIL_TO_RADIUS;
	// the nearest hull that is not the hero's
	for (int i = 0; i < seaShipCount; i++)
	{
		if (i == seaHero) { continue; }
		dx = stf(SeaShips[i].ship.pos.x) - hx;
	 dz = stf(SeaShips[i].ship.pos.z) - hz;
	 d2 = dx * dx + dz * dz;
	 if (d2 <= best)
		{
		 best = d2;
		 seaSailIndex = i;
		 seaSailTX = stf(SeaShips[i].ship.pos.x);
		 seaSailTZ = stf(SeaShips[i].ship.pos.z);
		 seaSailKind = "ship";
		 seaSailName = SeaShips[i].id;
		}
	}
	if (seaIsland != "")
	{
		// the fort of the island
		if (CheckAttribute(&PdmIslands, seaIsland + ".fort_x"))
		{
		 float fx = stf(PdmIslands.(seaIsland).fort_x);
		 float fz = stf(PdmIslands.(seaIsland).fort_z);
		 dx = fx - hx;
		 dz = fz - hz;
		 d2 = dx * dx + dz * dz;
		 if (d2 <= best)
			{
			 best = d2;
			 seaSailIndex = -1;
			 seaSailTX = fx;
			 seaSailTZ = fz;
			 seaSailKind = "fort";
			 seaSailName = PdmIslands.(seaIsland).fort;
			}
		}
		// the harbour: the landing point where the transition to another location happens
		if (CheckAttribute(&PdmIslands, seaIsland + ".harbour_x"))
		{
		 float hx2 = stf(PdmIslands.(seaIsland).harbour_x);
		 float hz2 = stf(PdmIslands.(seaIsland).harbour_z);
		 dx = hx2 - hx;
		 dz = hz2 - hz;
		 d2 = dx * dx + dz * dz;
		 if (d2 <= best)
			{
			 seaSailIndex = -1;
			 seaSailTX = hx2;
			 seaSailTZ = hz2;
			 seaSailKind = "harbour";
			 seaSailName = seaIsland + " harbour";
			}
		}
	}
	return seaSailKind != "";
}

// the button is lit only when a target of the data stands in reach of the press
bool Sea_CanSailTo()
{
	if (seaBattle) { return false; }
	// the pressed pick belongs to the launch (Sea_SailTo), not to this enable check:
	// the hub asks CanSailTo every frame and would otherwise consume the pressed icon
	int parkChr = hudSailTargetChr;
	string parkName = hudSailTargetName;
	hudSailTargetChr = -1;
	hudSailTargetName = "";
	bool ready = Sea_SailToTarget();
	hudSailTargetChr = parkChr;
	hudSailTargetName = parkName;
	return ready;
}

// put the hero's hull at a point of the game data at once (ship.cpp MSG_SHIP_TELEPORT
// "lfff": the same call the sail-to of this file makes; the autotest moves the hero with it
void Sea_TeleportHero(float x, float z)
{
	SendMessage(&SeaShips[seaHero], "lfff", MSG_SHIP_TELEPORT, x, z, stf(SeaShips[seaHero].ship.ang.y));
	Trace("PDM sea: teleport sent, hero right after the send " + stf(SeaShips[seaHero].ship.pos.x) + ", " + stf(SeaShips[seaHero].ship.pos.z));
}

// the same teleport put on an NPC hull of this scene (the autotest moves the hull with it
void Sea_TeleportNpc(float x, float z)
{
	SendMessage(&SeaShips[seaNpc], "lfff", MSG_SHIP_TELEPORT, x, z, stf(SeaShips[seaNpc].ship.ang.y));
}

// "Плыть к" outside of battle (ours, the math of battle.c:Battle_SailTo): the hero is put near
// the picked target — abeam of an NPC hull at SEA_SAIL_TO m as in battle.c, or SEA_SAIL_TO_PLACE
// m off a place of the data (the fort, the harbour) on the line from it to where he is now
void Sea_SailTo()
{
	// Sea_CanSailTo may not have run since the last open of the menu, pick again
	if (!Sea_SailToTarget()) { Trace("PDM: sea, sail to: nothing to sail to in reach"); return; }
	// an NPC hull: the same abeam landing as battle.c:Battle_SailTo
	if (seaSailIndex >= 0)
	{
		float ex = stf(SeaShips[seaSailIndex].ship.pos.x);
		 float ez = stf(SeaShips[seaSailIndex].ship.pos.z);
	 float ay = stf(SeaShips[seaSailIndex].ship.ang.y);
		// the starboard of the NPC is (cos ay, -sin ay); the hero stays on his side of it
		// the same ship teleport as battle.c:Battle_SailTo sends to the hero's entity
		// the NPC keeps its head in the teleport, the hero gets the same one
		// so that the ships do not overlap and the button can be pressed again
		// the hero sails on afterwards as the player steers him
		// the NPC does not answer: the hero may press the button again from any side

		float rx = cos(ay);
		float rz = -sin(ay);
		 float side = SEA_SAIL_TO;
		if ((stf(SeaShips[seaHero].ship.pos.x) - ex) * rx + (stf(SeaShips[seaHero].ship.pos.z) - ez) * rz < 0.0) { side = -side; }
		 SendMessage(&SeaShips[seaHero], "lfff", MSG_SHIP_TELEPORT, ex + rx * side, ez + rz * side, ay);
		 Hud_Log(PdmHud.note.sail_to + " " + SeaShips[seaSailIndex].Ship.Name);
		Trace("PDM: sea, sail to " + SeaShips[seaSailIndex].id + ", " + side + " m abeam");
		 return;
		}
		// a place of the data: the hero stops SEA_SAIL_TO_PLACE m off it, on the line from the
		// place to where he is now, the head as it was; atan2 gives the heading without sqrt
		// and casts, the crash-prone chain of battle.c avoided
	 float hx = stf(SeaShips[seaHero].ship.pos.x);
	 float hz = stf(SeaShips[seaHero].ship.pos.z);
	 float a = atan2(hx - seaSailTX, hz - seaSailTZ);
	 // the hull branch above already declared ay at function level, this branch names it hay
	 float hay = stf(SeaShips[seaHero].ship.ang.y);
	 SendMessage(&SeaShips[seaHero], "lfff", MSG_SHIP_TELEPORT, seaSailTX + sin(a) * SEA_SAIL_TO_PLACE, seaSailTZ + cos(a) * SEA_SAIL_TO_PLACE, hay);
	 Hud_Log(PdmHud.note.sail_to + " " + seaSailName);
	 Trace("PDM: sea, sail to " + seaSailName + " at " + stf(seaSailTX) + ", " + stf(seaSailTZ));
	}

// TOWN_AUTO=15: the frame after the jump the hero and the target write their places again
// (battle.c:Battle_SailToCheck's pattern)
void Sea_SailToCheck()
{
		 if (seaSailKind == "" || seaHero < 0) { return; }
		 Trace("PDM: sea, sail to done, hero " + stf(SeaShips[seaHero].ship.pos.x) + " " + stf(SeaShips[seaHero].ship.pos.z) + ", target " + stf(seaSailTX) + " " + stf(seaSailTZ));
		// the button works and the ships moved: the run ends by going back to the world map
		 // the map is the end of the autotest, not of the button press (autotest\sea_sail.c:SeaSailAuto_End)
	}

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
	// the port of the island gets its moored hulls on a normal sea; TOWN_AUTO=15 keeps its scripted
	// lone NPC of SEA_NPC_KEY so the button autotest proves one deterministic target (14 is the options page)
	if (TownAuto != 15) { Sea_PortShips(); }
	if (TownAuto == 15) { Sea_NpcSpawn(x, z, ay); }
	SetEventHandler("Sea_Tick", "Sea_Tick", 0);
	SetEventHandler("Sea_ToPort", "Sea_ToPort", 0);
	SetEventHandler("Sea_ToMap", "Sea_ToMap", 0);
	// "Плыть к" at sea (ours, as battle.c registers Battle_SailTo at 166): the Tab's press posts Sea_SailTo
	// (hud.c:Hud_LaunchCommand), the autotest posts it too, never simulated keys
	SetEventHandler("Sea_SailTo", "Sea_SailTo", 0);
	SetEventHandler("Sea_SailToCheck", "Sea_SailToCheck", 0);
	SetEventHandler("SeaSailAuto_End", "SeaSailAuto_End", 0);
	SetEventHandler("SeaSailAuto_Step3", "SeaSailAuto_Step3", 0);
	SetEventHandler("SeaSailAuto_Step4", "SeaSailAuto_Step4", 0);
	SetEventHandler("SeaSailAuto_Step5", "SeaSailAuto_Step5", 0);
	PostEvent("Sea_Tick", SEA_TICK_MS);
	seaActive = true;
	seaFromMap = false;
	// TOWN_AUTO=4: the autotest sails out and comes back by itself; 6: out to the world map once
	if (TownAuto == 4) { PostEvent("Sea_ToPort", SEA_AUTO_PORT_MS); }
	if (TownAuto == 6 && !seaAutoMapDone) { seaAutoMapDone = true; PostEvent("Sea_ToMap", SEA_AUTO_MAP_MS); }
	// TOWN_AUTO=15: the button "Плыть к" pressed once, as the battle's TOWN_AUTO=9 presses Battle_SailTo
	// (the event stands for the Tab's press, never simulated keys, as the interface autotests do)
	// the autotest of the button lives in autotest\sea_sail.c: this is its first press
	if (TownAuto == 15 && !seaAutoSailDone) { seaAutoSailDone = true; SeaSailAuto_Press(); }
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
void Sea_Arrive(string islandKey, float atMapX, float atMapY, float ay)
{
	seaFromMap = true;
	// to the sea: the transform of the original (worldmap_reload.c: WdmAddPlayerGroup, and worldmap.c: wdmCreateMap for the
	// reverse way): the flag of an island and its harbour are the same anchor, the ship appears at sea
	// from the point of the map in the same meters away from the harbour as it was from the flag in px times 50,
	// with its course from the map
	seaLoadPos = true;
	seaLoadX = stf(PdmIslands.(islandKey).harbour_x) + (atMapX - Map_IslandX(islandKey)) * SEA_MAP_TO_SEA_SCALE;
	seaLoadZ = stf(PdmIslands.(islandKey).harbour_z) + (atMapY - Map_IslandY(islandKey)) * SEA_MAP_TO_SEA_SCALE;
	seaLoadAy = ay;
	Sea_Start(islandKey);
}

void Sea_ToMap()
{
	if (!seaActive) { return; }
	string island = seaIsland;
	// the place and the course of the hero's ship at sea, taken before the release (the entity writes ship.pos and ship.ang each frame)
	float mx = 0.0;
	float my = 0.0;
	float ay = 0.0;
	if (island != "" && CheckAttribute(&PdmIslands, island + ".map_cell"))
	{
		mx = Map_IslandX(island);
		my = Map_IslandY(island);
		if (seaHero >= 0 && CheckAttribute(&SeaShips[seaHero], "ship.pos.x") && CheckAttribute(&PdmIslands, island + ".harbour_x"))
		{
			// back to the map: map = flag + (sea - harbour) / 50 (worldmap.c: wdmCreateMap, the same transform the other way)
			mx = mx + (stf(SeaShips[seaHero].ship.pos.x) - stf(PdmIslands.(island).harbour_x)) / SEA_MAP_TO_SEA_SCALE;
			my = my + (stf(SeaShips[seaHero].ship.pos.z) - stf(PdmIslands.(island).harbour_z)) / SEA_MAP_TO_SEA_SCALE;
			ay = stf(SeaShips[seaHero].ship.ang.y);
		}
	}
	Sea_Release();
	Trace("PDM: sea, to the world map from " + island);
	Map_Start(island, mx, my, ay);
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
	seaNpc = -1;
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
		// the NPC hulls of a normal sea go to the BI ship list too (BI_IN_CREATE_SHIP is
		// SHIP_DESCRIBE_LIST::Add of ships_list.cpp, the same message battle.c sends and hud.c
		// sends for the hero once): their icons fill the bar of "Плыть к".
		CreateEntity(&SeaShips[i], "ship");
		SendMessage(&SeaShips[i], "laa", MSG_SHIP_CREATE, &SeaShips[i], &SeaShipTypes[i]);
		if (i != seaHero) { SendMessage(&BattleInterface, "llaall", BI_IN_CREATE_SHIP, i, &SeaShips[i], &SeaShipTypes[i], 0, BI_RELATION_NEUTRAL); }
		// registration only after MSG_SHIP_CREATE: ships_list.cpp Add (SHIP_DESCRIBE_LIST::Add)
		// scans the "ship" entities and derefs their character pointer, so the hull entity must
		// already be fully created when it lands on the list

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

