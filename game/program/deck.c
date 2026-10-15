// The boarding: the deck of «Ворон» (make_deck.py), the captain and his sailors at the stern, the
// pirates at the bow. Built from the engine melee demo: the location runs the fight, the characters
// hold sabers (BLADE), the pirates and our sailors are NPCs with the "Fight" task, the captain is the
// player. Life, energy and damage live in the characters' attributes here, the engine asks for them.
// The pirates on the deck are the crew of «Ворон» that the guns have left, a fighter for every
// CREW_PER_PIRATE of them; the captain takes a sailor along for every CREW_PER_SAILOR of his.
// E draws or sheathes the saber, the left mouse button attacks fast, the right one with force,
// Space holds a block, Q parries; W/S/A/D and the mouse move as in the port. Enter after the fight
// returns to the port.

#define MSG_CHARACTER_SETBLADE 30360
#define MSG_CHARACTER_SETFTGLEVEL 30362
#define MSG_CHARACTER_EX_MSG 30373
#define MSG_NPCHARACTER_SETTASK 30400

// make_deck.py: the deck is this high over the sea
#define DECK_HEIGHT 3.0
#define MAX_PIRATES 5
#define MAX_SAILORS 3
#define CREW_PER_PIRATE 24
#define CREW_PER_SAILOR 32
// life and energy; an action costs energy, it comes back by ENERGY_REGEN a second
#define HERO_HP 100.0
#define SAILOR_HP 60.0
#define PIRATE_HP 50.0
// every level of «Ворон» (world.c, Raven_Level) makes his pirates this much tougher and quicker
#define PIRATE_LEVEL_HP 8.0
#define PIRATE_LEVEL_SKILL 0.08
#define MAX_ENERGY 100.0
#define ENERGY_REGEN 12.0
#define DECK_TICK_MS 100
// a sailor who falls on the deck is this many of the crew; the pirates who are left go over the side
#define SAILOR_LOSS 12
// the hold of a taken «Ворон»: the governor pays for the prize, the charges go into our hold
#define PRIZE_GOLD 300
#define PRIZE_LEVEL_GOLD 100
#define PRIZE_BALLS 30

object DeckLocation;
object DeckGroups;
object DeckCamera;
object DeckBrig;
object Boarder;
object DeckPirates[MAX_PIRATES];
object DeckSailors[MAX_SAILORS];

int inDeck = 0;
int deckVisit = 0;
int deckOver = 0;
int pirateCount = 0;
int sailorCount = 0;
int piratesLeft = 0;
int sailorsLost = 0;

void Deck_MapControls()
{
	// the fight controls the player character reads (player.cpp); outside the deck the script does
	// not let him fight (Deck_IsFight)
	MapKey("ChrFightMode", 69, 0);
	MapKey("ChrAttackFast", 1, 0);
	MapKey("ChrAttackForce", 2, 0);
	MapKey("ChrBlock", 32, 0);
	MapKey("ChrParry", 81, 0);
}

// the rules the engine asks about any character of a location: in the port too, so they are set with
// the menu (and again after a load)
void Deck_SetHandlers()
{
	SetEventHandler("Location_CharacterIsFight", "Deck_IsFight", 0);
	SetEventHandler("ChrAttackAction", "Deck_CheckAction", 0);
	SetEventHandler("ChrCheckEnergy", "Deck_CheckAction", 0);
	SetEventHandler("ChrFgtActApply", "Deck_ActionApply", 0);
	SetEventHandler("Location_CharacterAttack", "Deck_Attack", 0);
	SetEventHandler("NpcEvtHP", "Deck_RelHP", 0);
	SetEventHandler("NpcEvtEny", "Deck_RelEnergy", 0);
	SetEventHandler("NpcEvtEgy", "Deck_RelEnergy", 0);
	SetEventHandler("NPC_Event_GetActionEnergy", "Deck_ActionEnergy", 0);
	SetEventHandler("NPC_Event_GetAttackActive", "DeckAi_AttackActive", 0);
	SetEventHandler("NPC_Event_GetAttackWeightFast", "DeckAi_WeightFast", 0);
	SetEventHandler("NPC_Event_GetAttackWeightForce", "DeckAi_WeightForce", 0);
	SetEventHandler("NPC_Event_GetAttackWeightRound", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_GetAttackWeightBreak", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_GetAttackWeightFeint", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_GetDefenceActive", "DeckAi_DefenceActive", 0);
	SetEventHandler("NPC_Event_GetDefenceWeightBlock", "DeckAi_WeightBlock", 0);
	SetEventHandler("NPC_Event_GetDefenceWeightParry", "DeckAi_WeightParry", 0);
	SetEventHandler("NPC_Event_EnableRecoil", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_GetFireActive", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_EnableFire", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_StunChance", "DeckAi_Zero", 0);
	SetEventHandler("NPC_Event_AdaptiveTargetSelect", "DeckAi_ZeroInt", 0);
	SetEventHandler("NPC_IsDodgeEnabled", "DeckAi_ZeroInt", 0);
	SetEventHandler("Deck_Tick", "Deck_Tick", 0);
}

int Deck_Clamp(int value, int low, int high)
{
	if (value < low) { return low; }
	if (value > high) { return high; }
	return value;
}

// The location runs the characters in it: it is made before them.
void Deck_Enter()
{
	World_Waves(0.4, 0.2, 0.6);
	inDeck = 1;
	deckOver = 0;
	sailorsLost = 0;
	pirateCount = Deck_Clamp((boardEnemyCrew + CREW_PER_PIRATE - 1) / CREW_PER_PIRATE, 1, MAX_PIRATES);
	sailorCount = Deck_Clamp(shipCrew / CREW_PER_SAILOR, 0, MAX_SAILORS);
	piratesLeft = pirateCount;

	DeckLocation.id = "deck";
	CreateEntity(&DeckLocation, "location");
	SendMessage(&DeckLocation, "ls", MSG_LOCATION_MODELSPATH, "deck");
	SendMessage(&DeckLocation, "ls", MSG_LOCATION_TEXTURESPATH, "deck");
	if (!SendMessage(&DeckLocation, "lssl", MSG_LOCATION_ADD_MODEL, "deck", "DLightModel", 10))
	{
		Trace("DECK: model not loaded");
	}
	if (!SendMessage(&DeckLocation, "ls", MSG_LOCATION_SET_CHRS_PATCH, "deck_patch"))
	{
		Trace("DECK: character patch not loaded");
	}
	CreateEntity(&DeckGroups, "CharactersGroups");
	SendMessage(&DeckGroups, "ssss", "SetRelation", "Crew", "Pirates", "enemy");
	SetEventHandler("EWhr_GetShadowDensity", "Port_ShadowDensity", 0);
	SetEventHandler("EWhr_GetFogDensity", "Port_FogDensity", 0);

	// the captain at the stern with the saber drawn, his sailors around him
	Boarder.id = "captain";
	Boarder.name = "Капитан";
	CreateEntity(&Boarder, "player");
	Deck_SetupFencer(&Boarder, "boarder", HERO_HP, "crew");
	Deck_Place(&Boarder, 0.0, -9.5, 0.0);
	int i;
	for (i = 0; i < sailorCount; i++)
	{
		DeckSailors[i].id = "sailor" + i;
		DeckSailors[i].slot = i;
		DeckSailors[i].name = "Матрос";
		CreateEntity(&DeckSailors[i], "npcharacter");
		Deck_SetupFencer(&DeckSailors[i], "boarder", SAILOR_HP, "crew");
		SendMessage(&DeckSailors[i], "lf", MSG_CHARACTER_SETFTGLEVEL, 0.4);
	}
	if (sailorCount > 0) { Deck_Place(&DeckSailors[0], -2.0, -8.5, 0.0); }
	if (sailorCount > 1) { Deck_Place(&DeckSailors[1], 2.0, -8.5, 0.0); }
	if (sailorCount > 2) { Deck_Place(&DeckSailors[2], -1.0, -11.5, 0.0); }
	// the pirates at the bow, facing the stern
	int level = Raven_Level();
	for (i = 0; i < pirateCount; i++)
	{
		DeckPirates[i].id = "pirate" + i;
		DeckPirates[i].slot = i;
		DeckPirates[i].name = "Пират";
		CreateEntity(&DeckPirates[i], "npcharacter");
		Deck_SetupFencer(&DeckPirates[i], "pirate", PIRATE_HP + PIRATE_LEVEL_HP * level, "pirate");
		SendMessage(&DeckPirates[i], "lf", MSG_CHARACTER_SETFTGLEVEL, 0.35 + PIRATE_LEVEL_SKILL * level);
	}
	if (pirateCount > 0) { Deck_Place(&DeckPirates[0], 0.0, 9.5, PI); }
	if (pirateCount > 1) { Deck_Place(&DeckPirates[1], 2.0, 9.5, PI); }
	if (pirateCount > 2) { Deck_Place(&DeckPirates[2], -1.0, 8.5, PI); }
	if (pirateCount > 3) { Deck_Place(&DeckPirates[3], 2.0, 11.5, PI); }
	if (pirateCount > 4) { Deck_Place(&DeckPirates[4], 0.0, 12.5, PI); }

	SendMessage(&Boarder, "lsl", MSG_CHARACTER_EX_MSG, "SetFightMode", 1);
	for (i = 0; i < sailorCount; i++) { Deck_Retarget(&DeckSailors[i]); }
	for (i = 0; i < pirateCount; i++) { Deck_Retarget(&DeckPirates[i]); }

	CreateEntity(&DeckCamera, "locationcamera");
	SendMessage(&DeckCamera, "li", MSG_CAMERA_SETTARGET, &Boarder);
	SendMessage(&DeckCamera, "l", MSG_CAMERA_FOLLOW);
	SendMessage(&Scene, "si", "SetActiveCamera", &DeckCamera);
	// «Ласточка» grappled alongside
	LoadModel(&DeckBrig, "ships\Brig\Brig");
	PlaceModel(&DeckBrig, -11.0, 0.0, -2.0, 0.0);
	LayerAddObject(SEA_REFLECTION2, &DeckBrig, 10);

	deckVisit++;
	PostEvent("Deck_Tick", DECK_TICK_MS, "l", deckVisit);
	Log("На абордаж! Пиратов: " + pirateCount + ", с вами матросов: " + sailorCount);
	Log("ЛКМ — удар, ПКМ — выпад, Пробел — блок, Q — парировать, E — убрать саблю");
	Trace("DECK: scene loaded, pirates " + pirateCount + " sailors " + sailorCount);
}

void Deck_Leave()
{
	inDeck = 0;
	int i;
	for (i = 0; i < pirateCount; i++) { DeleteClass(&DeckPirates[i]); }
	for (i = 0; i < sailorCount; i++) { DeleteClass(&DeckSailors[i]); }
	DeleteClass(&DeckBrig);
	DeleteClass(&DeckCamera);
	DeleteClass(&Boarder);
	DeleteClass(&DeckGroups);
	DeleteClass(&DeckLocation);
	Trace("DECK: left");
}

void Deck_Place(ref chr, float x, float z, float ay)
{
	SendMessage(chr, "lffff", MSG_CHARACTER_TELEPORT_AY, x, DECK_HEIGHT, z, ay);
}

void Deck_SetupFencer(ref chr, string model, float hp, string side)
{
	chr.hp = hp;
	chr.maxhp = hp;
	chr.energy = MAX_ENERGY;
	chr.side = side;
	chr.target = "";
	// resource\models\characters\<model>.gm with resource\animation\fencer.ani
	if (!SendMessage(chr, "lss", MSG_CHARACTER_SETMODEL, model, "fencer"))
	{
		Trace("DECK: " + model + " not loaded");
	}
	// the fencer has one action of a kind where the engine expects lists of up to four: every list
	// names it once. Changing "actions" rereads them.
	chr.actions.idle.i1 = "idle_1";
	chr.actions.dead.d1 = "death_1";
	chr.actions.fightidle.i1 = "fight stand";
	chr.actions.fightwalk = "fight walk";
	chr.actions.fightbackwalk = "fight back walk";
	chr.actions.fightrun = "fight run";
	chr.actions.fightbackrun = "fight back run";
	chr.actions.attack_fast.a1 = "attack_fast_1";
	chr.actions.attack_force.a1 = "attack_force_1";
	chr.actions.attack_round.a1 = "attack_force_1";
	chr.actions.attack_break.a1 = "attack_force_1";
	chr.actions.attack_feint.a1 = "attack_fast_1";
	chr.actions.attack_feintc.a1 = "attack_fast_1";
	chr.actions.hit_attack.h1 = "hit_attack_1";
	chr.actions.parry.p1 = "parry_1";
	chr.actions.hit_feint = "hit_attack_1";
	chr.actions.hit_parry = "hit_parry";
	chr.actions.hit_round = "hit_attack_1";
	chr.actions.hit_shot = "hit_attack_1";
	chr.actions.HitNoFight = "hit_attack_1";
	chr.actions.block = "block";
	chr.actions.block_axe = "block";
	chr.actions.blockhit = "block_hit";
	chr.actions.blockaxehit = "block_hit";
	chr.actions.blockbreak = "hit_attack_1";
	chr.actions.recoil = "block_hit";
	chr.actions.strafeleft = "fight walk";
	chr.actions.straferight = "fight walk";
	chr.actions.fightdead.d1 = "death_1";
	chr.actions = "";
	// models\Ammo\saber.gm; the trail between its "start" and "end" labels fades in 0.25 s
	SendMessage(chr, "lsfll", MSG_CHARACTER_SETBLADE, "saber", 0.25, argb(64, 255, 255, 255), argb(0, 255, 255, 255));
	// the engine attacks only enemies: the groups hold who is whose
	if (side == "pirate") { SendMessage(&DeckGroups, "sis", "MoveChr", chr, "Pirates"); }
	else { SendMessage(&DeckGroups, "sis", "MoveChr", chr, "Crew"); }
}

int Deck_Alive(ref chr)
{
	return stf(chr.hp) > 0.0;
}

// An NPC fights the enemy his index points at among the ones standing: the pirates share out the
// captain and his sailors, the sailors the pirates. A fallen enemy sends everyone who fought him on.
void Deck_Retarget(ref chr)
{
	if (deckOver || !Deck_Alive(chr)) { return; }
	int slot = sti(chr.slot);
	int i, n, nth;
	if (chr.side == "pirate")
	{
		// the captain and the sailors standing, in turn
		n = 1;
		for (i = 0; i < sailorCount; i++) { if (Deck_Alive(&DeckSailors[i])) { n++; } }
		// the script has no %
		nth = slot - (slot / n) * n;
		if (nth == 0) { Deck_FightTask(chr, &Boarder); return; }
		for (i = 0; i < sailorCount; i++)
		{
			if (Deck_Alive(&DeckSailors[i]))
			{
				nth--;
				if (nth == 0) { Deck_FightTask(chr, &DeckSailors[i]); return; }
			}
		}
		return;
	}
	for (n = 0; n < pirateCount; n++)
	{
		i = slot + n;
		i = i - (i / pirateCount) * pirateCount;
		if (Deck_Alive(&DeckPirates[i])) { Deck_FightTask(chr, &DeckPirates[i]); return; }
	}
}

void Deck_FightTask(ref chr, ref enemy)
{
	chr.target = enemy.id;
	SendMessage(chr, "lsi", MSG_NPCHARACTER_SETTASK, "Fight", enemy);
}

// ---------------------------------------------------------------- the rules the engine asks

int Deck_IsFight()
{
	aref chr = GetEventData();
	if (!inDeck || deckOver) { return 0; }
	return 1;
}

float Deck_ActionCost(string action)
{
	if (action == "fast") { return 10.0; }
	if (action == "force") { return 22.0; }
	if (action == "parry") { return 14.0; }
	if (action == "hit_parry") { return 8.0; }
	if (action == "recoil") { return 12.0; }
	return 6.0;
}

// an attack or another action starts only with the energy for it
int Deck_CheckAction()
{
	aref chr = GetEventData();
	string action = GetEventData();
	if (!CheckAttribute(chr, "energy")) { return 0; }
	if (stf(chr.energy) < Deck_ActionCost(action)) { return 0; }
	return 1;
}

void Deck_ActionApply()
{
	aref chr = GetEventData();
	string action = GetEventData();
	if (!CheckAttribute(chr, "energy")) { return; }
	float energy = stf(chr.energy) - Deck_ActionCost(action);
	if (energy < 0.0) { energy = 0.0; }
	chr.energy = energy;
}

// a saber reached an enemy: a block takes most of the blow, a force attack breaks through more
void Deck_Attack()
{
	aref attacker = GetEventData();
	aref enemy = GetEventData();
	string action = GetEventData();
	int isBlocked = GetEventData();
	if (deckOver || !inDeck || stf(enemy.hp) <= 0.0) { return; }
	float damage = 12.0;
	if (action == "force") { damage = 22.0; }
	// the captain's saber is the best on board
	if (attacker.id == "captain") { damage = damage * 1.25; }
	if (isBlocked)
	{
		damage = damage * 0.15;
		if (action == "force") { damage = damage * 2.0; }
	}
	float hp = stf(enemy.hp) - damage;
	if (hp < 0.0) { hp = 0.0; }
	enemy.hp = hp;
	if (enemy.id == "captain" && !isBlocked) { Log("Вас ранили! Жизни " + makeint(hp)); }
	if (hp > 0.0) { return; }
	// "Dead" stops the character and plays his fightdead action
	SendMessage(enemy, "ls", MSG_NPCHARACTER_SETTASK, "Dead");
	Trace("DECK: " + enemy.id + " killed by " + attacker.id);
	if (enemy.id == "captain") { Deck_End(0); return; }
	int i;
	if (enemy.side == "pirate")
	{
		piratesLeft--;
		if (piratesLeft <= 0) { Deck_End(1); return; }
		Log("Пират пал! Осталось " + piratesLeft);
		for (i = 0; i < sailorCount; i++) { if (DeckSailors[i].target == enemy.id) { Deck_Retarget(&DeckSailors[i]); } }
		return;
	}
	sailorsLost++;
	Log("Наш матрос пал!");
	for (i = 0; i < pirateCount; i++) { if (DeckPirates[i].target == enemy.id) { Deck_Retarget(&DeckPirates[i]); } }
}

// The fight is over: the crew and the prize go to the state of the game, Tom pays in the port.
void Deck_End(int won)
{
	deckOver = 1;
	shipCrew = shipCrew - sailorsLost * SAILOR_LOSS;
	if (won)
	{
		int prize = PRIZE_GOLD + PRIZE_LEVEL_GOLD * Raven_Level();
		lastBattle = "win";
		lastBoarding = "won";
		unpaidGold = unpaidGold + Raven_Bounty() + prize;
		unpaidWins++;
		unpaidPrizes++;
		Charge_Add(CHARGE_BALLS, PRIZE_BALLS);
		Log("«Ворон» наш! В его трюме " + PRIZE_BALLS + " ядер, приз — " + prize + " песо. Enter — на карту");
		Trace("DECK: won, sailors lost " + sailorsLost + ", crew " + shipCrew);
		return;
	}
	// the captain falls wounded, the sailors carry him back and cut the grapnels
	lastBattle = "loss";
	lastBoarding = "lost";
	shipCrew = shipCrew - (sailorCount - sailorsLost) * SAILOR_LOSS;
	if (shipCrew < LOSS_CREW) { shipCrew = LOSS_CREW; }
	Log("Вы ранены, матросы уносят вас на «Ласточку» и рубят абордажные концы. Enter — в порт");
	Trace("DECK: lost, crew " + shipCrew);
}

float Deck_RelHP()
{
	aref chr = GetEventData();
	if (!CheckAttribute(chr, "maxhp")) { return 1.0; }
	return stf(chr.hp) / stf(chr.maxhp);
}

float Deck_RelEnergy()
{
	aref chr = GetEventData();
	if (!CheckAttribute(chr, "energy")) { return 1.0; }
	return stf(chr.energy) / MAX_ENERGY;
}

float Deck_ActionEnergy()
{
	aref chr = GetEventData();
	string action = GetEventData();
	return Deck_ActionCost(action) / MAX_ENERGY;
}

// how often an NPC attacks or defends and with what
float DeckAi_AttackActive() { aref chr = GetEventData(); return 0.6; }
float DeckAi_WeightFast() { aref chr = GetEventData(); return 0.7; }
float DeckAi_WeightForce() { aref chr = GetEventData(); return 0.3; }
float DeckAi_DefenceActive() { aref chr = GetEventData(); return 0.5; }
float DeckAi_WeightBlock() { aref chr = GetEventData(); return 0.7; }
float DeckAi_WeightParry() { aref chr = GetEventData(); return 0.3; }
float DeckAi_Zero() { aref chr = GetEventData(); return 0.0; }
int DeckAi_ZeroInt() { return 0; }

// the energy comes back
void Deck_Tick()
{
	int visit = GetEventData();
	if (!inDeck || visit != deckVisit) { return; }
	Deck_Regen(&Boarder);
	int i;
	for (i = 0; i < sailorCount; i++) { Deck_Regen(&DeckSailors[i]); }
	for (i = 0; i < pirateCount; i++) { Deck_Regen(&DeckPirates[i]); }
	PostEvent("Deck_Tick", DECK_TICK_MS, "l", visit);
}

void Deck_Regen(ref chr)
{
	float energy = stf(chr.energy) + ENERGY_REGEN * DECK_TICK_MS / 1000.0;
	if (energy > MAX_ENERGY) { energy = MAX_ENERGY; }
	chr.energy = energy;
}

// called by menu.c for the controls pressed while the deck is shown
void Deck_Control(string control)
{
	if (control == "Sea_ToPort" && deckOver) { Sea_AfterBattle(); }
}
