// The boarding (П5): in the battle the command "Абордаж" of the toolbar (Tab, or Space) boards the enemy within
// BOARD_DISTANCE. The original plays the movie of the crews fighting on the deck (ACTIONS\brd_*.a: PLAY
// Engine_movie "Fight_Eng", not ported: ours counts the fight of the crews and reports it), then the captains fight
// in the cabin MODELS\kayuta.cff: tools/pdm_boarding.py converts it into data\pdm_boarding.c (PdmBoarding) with
// the fighters of anim_types.idf holding the blade drawn (models\characters\<model>_brd.gm).
// The fight is the one of the engine demo melee: the engine plays the attacks, blocks and parries and asks these
// scripts what they cost and what they do. The blades are parts of the models of the original, so the
// fighters fight without the BLADE entity (SetFightWOWeapon). The damage is the power of the hit of the
// original (hit_1..4 of the .idf: 10 and 15) by the combat of the attacker and the defence of the one hit.
// The energy is the one of Boarding.dll: an action spends power * 0.013 a frame (WORLDS\CHARACTERS\brd_anim.idf:
// the hits 20 frames of power 10 and 15, the blocks 15 frames of 2 and 3, the turns 4), a blocked blow the block
// of the one who blocks it, and an action starts only with the energy for it; the energy comes back by
// 0.035 + (s*9+1)*0.0032 + (s - s of the enemy)*0.03 a second (s the combat 0..1), the dead lose it.
// Ours: the cost is a tenth of the original (it spends 2.6 of the full 1 on a hit and gives back 0.04..0.1
// a second), the tired fighter strikes slower (SetAnimSpeed, BOARD_SLOW_MIN at no energy).
// The plates of Boarding.dll (TEXTURES\boarding\brd_left.tf, brd_right.tf) at the bottom corners show
// "Команда" (the health) and "Сила" (the energy) of the hero and of the enemy (IBoardingStatus).
// W/S, A/D, the mouse move the hero, F attacks fast, G with force, Space blocks, Q parries.
// Won: the enemy ship is taken, back to the sea; lost: the hero falls, the main menu.
// SCENE=battle TOWN_AUTO=8: SEA_AI sails the hero to the enemy to board, he fights by himself and the autotest quits.

#define MSG_CHARACTER_SETFTGLEVEL 30362
#define MSG_CHARACTER_EX_MSG 30373
#define LOG_INIT_CHARCTER_HP 45025
#define LOG_SET_BOARDING_BAR 45031
#define BOARD_HP 100.0
#define BOARD_ENERGY 100.0
#define BOARD_TICK_MS 100
// the energy of Boarding.dll: spent power * BOARD_POWER_COST a frame of the action; back by BOARD_REGEN +
// (s*9+1)*BOARD_REGEN_SKILL + (s - s of the enemy)*BOARD_REGEN_BETTER a second, at least BOARD_REGEN_MIN;
// the dead lose BOARD_DEAD_DRAIN a second (all of the full energy 1)
#define BOARD_POWER_COST 0.013
#define BOARD_REGEN 0.035
#define BOARD_REGEN_SKILL 0.0032
#define BOARD_REGEN_BETTER 0.03
#define BOARD_REGEN_MIN 0.01
#define BOARD_DEAD_DRAIN 0.1
// ours: the cost is this part of the original
#define BOARD_COST_SCALE 0.1
// ours: the speed of the actions of a fighter without energy, percent of the normal one
#define BOARD_SLOW_MIN 60
// the plates of Boarding.dll: 10 pixels from the left, the right and the bottom edges
#define BOARD_PLATE_MARGIN 10.0
// a blocked blow takes this part of the damage, a skill point this much more (combat) or less (defence)
#define BOARD_BLOCKED 0.15
#define BOARD_COMBAT_STEP 0.12
#define BOARD_DEFENCE_STEP 0.06
// back to the sea, or to the menu, this long after the fight
#define BOARD_END_MS 5000

object BoardLocation;
object BoardWeather;
object BoardGroups;
object BoardHero;
object BoardEnemy;
object BoardCamera;
object BoardStatus;
bool boardActive = false;
bool boardOver = false;
string boardIsland = "";
string boardEnemyKey = "";
int boardShadow[2];

// the hero is in the battle, not done, near the enemy
bool Board_Can()
{
	if (!seaBattle || battleOver || battleEnemy < 0 || seaHero < 0) { return false; }
	if (!CheckAttribute(&SeaShips[seaHero], "ship.pos.x") || !CheckAttribute(&SeaShips[battleEnemy], "ship.pos.x")) { return false; }
	float dx = stf(SeaShips[battleEnemy].ship.pos.x) - stf(SeaShips[seaHero].ship.pos.x);
	float dz = stf(SeaShips[battleEnemy].ship.pos.z) - stf(SeaShips[seaHero].ship.pos.z);
	return sqrt(dx * dx + dz * dz) < BOARD_DISTANCE;
}

// a tick of the battle: the autotest boards as soon as it can
void Board_SeaTick()
{
	if (TownAuto == 8 && Board_Can()) { PostEvent("Board_Start", 0); }
}

// the scene is changed outside the frame (a posted event): the sea goes, the cabin comes
void Board_Start()
{
	if (!Board_Can()) { return; }
	boardEnemyKey = BATTLE_ENEMY;
	boardIsland = PlayerCard.address.island;
	if (seaIsland != "") { boardIsland = seaIsland; }
	Sea_Release();
	Board_Crews();
	Board_Load();
}

// The crews fight on the deck (ours: the movie of the original is not ported): each side loses men by the
// strength of the other, the crew by the soldier skill of the ship
void Board_Crews()
{
	string enemyKey = boardEnemyKey;
	string shipKey = PdmCharacters.(enemyKey).ship_key;
	int ours = sti(PlayerShipCard.crew);
	int theirs = sti(PdmShips.(shipKey).crew);
	float ourStrength = ours * (1.0 + 0.25 * sti(PlayerShipCard.skills.soldier));
	float theirStrength = theirs * (1.0 + 0.25 * sti(PdmShips.(shipKey).skills.soldier));
	int ourLoss = makeint(theirs * theirStrength / (ourStrength + theirStrength));
	int theirLoss = makeint(ours * ourStrength / (ourStrength + theirStrength));
	if (ourLoss > ours) { ourLoss = ours; }
	if (theirLoss > theirs) { theirLoss = theirs; }
	string report = "PDM: boarding, crews " + ours + " against " + theirs + ", lost " + ourLoss + " and " + theirLoss;
	Trace(report);
	BoardHero.crew_lost = ourLoss;
	BoardEnemy.crew_lost = theirLoss;
}

void Board_Load()
{
	string enemyKey = boardEnemyKey;
	aref card;
	makearef(card, PdmCharacters.(enemyKey));
	boardActive = true;
	boardOver = false;
	Town_MapKeys();
	MapKey("ChrAttackFast", 70);
	MapKey("ChrAttackForce", 71);
	MapKey("ChrBlock", 32);
	MapKey("ChrParry", 81);

	// the cabin is lit inside, as the interiors of the towns
	CreateEntity(&BoardWeather, "weather");
	BoardWeather.Fog.Enable = 0;
	BoardWeather.Fog.Density = 0.0;
	BoardWeather.Fog.Color = argb(0, 0, 0, 0);
	BoardWeather.Sun.Color = argb(0, 255, 240, 215);
	BoardWeather.Sun.Ambient = argb(0, 150, 140, 125);
	BoardWeather.Sun.HeightAngle = 0.9;
	BoardWeather.Sun.AzimuthAngle = 2.5;
	BoardWeather.isDone = "";
	Render.BackColor = argb(255, 0, 0, 0);
	boardShadow[0] = argb(255, 96, 96, 96);
	boardShadow[1] = argb(255, 96, 96, 64);

	BoardLocation.id = "boarding";
	CreateEntity(&BoardLocation, "location");
	SendMessage(&BoardLocation, "ls", MSG_LOCATION_MODELSPATH, "locations");
	SendMessage(&BoardLocation, "ls", MSG_LOCATION_TEXTURESPATH, "locations");
	if (!SendMessage(&BoardLocation, "lssl", MSG_LOCATION_ADD_MODEL, PdmBoarding.model, "DLightModel", 10))
	{
		Trace("PDM boarding: model " + PdmBoarding.model + " not loaded");
	}
	if (!SendMessage(&BoardLocation, "ls", MSG_LOCATION_SET_CHRS_PATCH, PdmBoarding.patch))
	{
		Trace("PDM boarding: patch " + PdmBoarding.patch + " not loaded");
	}
	CreateEntity(&BoardGroups, "CharactersGroups");

	// the event handlers go first: the characters ask them as soon as they are set up
	SetEventHandler("EWhr_GetShadowDensity", "Board_ShadowDensity", 0);
	SetEventHandler("EWhr_GetFogDensity", "Board_FogDensity", 0);
	SetEventHandler("Location_CharacterIsFight", "Board_IsFight", 0);
	SetEventHandler("ChrAttackAction", "Board_AttackAction", 0);
	SetEventHandler("ChrCheckEnergy", "Board_AttackAction", 0);
	SetEventHandler("ChrFgtActApply", "Board_ActionApply", 0);
	SetEventHandler("Location_CharacterAttack", "Board_Attack", 0);
	SetEventHandler("NpcEvtHP", "Board_RelHP", 0);
	SetEventHandler("NpcEvtEny", "Board_RelEnergy", 0);
	SetEventHandler("NpcEvtEgy", "Board_RelEnergy", 0);
	SetEventHandler("NPC_Event_GetActionEnergy", "Board_ActionEnergy", 0);
	SetEventHandler("NPC_Event_GetAttackActive", "Board_AiAttack", 0);
	SetEventHandler("NPC_Event_GetAttackWeightFast", "Board_AiFast", 0);
	SetEventHandler("NPC_Event_GetAttackWeightForce", "Board_AiForce", 0);
	SetEventHandler("NPC_Event_GetAttackWeightRound", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_GetAttackWeightBreak", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_GetAttackWeightFeint", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_GetDefenceActive", "Board_AiDefence", 0);
	SetEventHandler("NPC_Event_GetDefenceWeightBlock", "Board_AiBlock", 0);
	SetEventHandler("NPC_Event_GetDefenceWeightParry", "Board_AiParry", 0);
	SetEventHandler("NPC_Event_EnableRecoil", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_GetFireActive", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_EnableFire", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_StunChance", "Board_AiZero", 0);
	SetEventHandler("NPC_Event_AdaptiveTargetSelect", "Board_AiZeroInt", 0);
	SetEventHandler("NPC_IsDodgeEnabled", "Board_AiZeroInt", 0);
	SetEventHandler("Board_Tick", "Board_Tick", 0);
	SetEventHandler("Board_End", "Board_End", 0);

	BoardHero.id = PlayerCard.id;
	BoardHero.name = PlayerCard.name;
	BoardHero.skills.combat = PlayerCard.skills.combat;
	BoardHero.skills.defence = PlayerCard.skills.defence;
	// the autotest fights by the AI of the engine
	if (TownAuto) { CreateEntity(&BoardHero, "NPCharacter"); }
	else { CreateEntity(&BoardHero, "player"); }
	Board_SetFighter(&BoardHero, Board_ModelOf(PlayerCard, 0), "attacker");

	BoardEnemy.id = card.id;
	BoardEnemy.name = card.name;
	BoardEnemy.skills.combat = card.skills.combat;
	BoardEnemy.skills.defence = card.skills.defence;
	CreateEntity(&BoardEnemy, "NPCharacter");
	Board_SetFighter(&BoardEnemy, Board_ModelOf(card, sti(card.nation)), "defender");

	SendMessage(&BoardGroups, "sis", "MoveChr", &BoardHero, "Hero");
	SendMessage(&BoardGroups, "sis", "MoveChr", &BoardEnemy, "Enemy");
	SendMessage(&BoardGroups, "ssss", "SetRelation", "Hero", "Enemy", "enemy");

	CreateEntity(&BoardCamera, "locationcamera");
	SendMessage(&BoardCamera, "li", MSG_CAMERA_SETTARGET, &BoardHero);
	SendMessage(&BoardCamera, "l", MSG_CAMERA_FOLLOW);
	SendMessage(&Scene, "si", "SetActiveCamera", &BoardCamera);

	// the skill of the AI: how fast it answers an attack with a block or a parry
	SendMessage(&BoardEnemy, "lf", MSG_CHARACTER_SETFTGLEVEL, Board_FightLevel(&BoardEnemy));
	SendMessage(&BoardEnemy, "lsi", MSG_NPCHARACTER_SETTASK, "Fight", &BoardHero);
	if (TownAuto)
	{
		SendMessage(&BoardHero, "lf", MSG_CHARACTER_SETFTGLEVEL, Board_FightLevel(&BoardHero));
		SendMessage(&BoardHero, "lsi", MSG_NPCHARACTER_SETTASK, "Fight", &BoardEnemy);
	}

	Hud_CreateLog();
	Board_CreateStatus();
	Sound_Music(Battle_Music(sti(card.nation)));
	SendMessage(&Sound, "lslllll", MSG_SOUND_PLAY, "svara", PCM_STEREO, VOLUME_FX, false, false, false, 0);
	Hud_Log("Абордаж! Команды потеряли " + BoardHero.crew_lost + " и " + BoardEnemy.crew_lost + " человек");
	Hud_Log(card.name + " ждёт в каюте");
	PostEvent("Board_Tick", BOARD_TICK_MS);
	Trace("PDM: boarding, " + BoardHero.id + " against " + card.id + " in " + PdmBoarding.model);
}

// the boarding model of the card (CHARACTERS\Pirat2.cff -> pirat2_brd), or the fighter of the nation (brd_mans.idf)
string Board_ModelOf(aref card, int nation)
{
	string model = Town_Lower(strcut(card.model, 11, strlen(card.model) - 5));
	if (CheckAttribute(&PdmBoarding, "fighters." + model)) { return model; }
	string crew = "n" + nation;
	if (CheckAttribute(&PdmBoarding, "crew." + crew)) { model = PdmBoarding.crew.(crew); }
	if (model != "" && CheckAttribute(&PdmBoarding, "fighters." + model)) { return model; }
	return "hero";
}

// the blade drawn from the start: the model with it in the hand, the fight actions of pdm_character.py, the
// fight mode without the BLADE entity; on its place of the cabin
void Board_SetFighter(ref chr, string model, string side)
{
	chr.hp = BOARD_HP;
	chr.energy = BOARD_ENERGY;
	if (!SendMessage(chr, "lss", MSG_CHARACTER_SETMODEL, model + "_brd", model))
	{
		Trace("PDM boarding: model " + model + "_brd not loaded");
	}
	chr.actions.idle.i1 = "fight stand";
	chr.actions.dead.d1 = "death_1";
	chr.actions.fightidle.i1 = "fight stand";
	chr.actions.fightwalk = "fight walk";
	chr.actions.fightbackwalk = "fight back walk";
	chr.actions.fightrun = "fight run";
	chr.actions.fightbackrun = "fight back run";
	chr.actions.attack_fast.a1 = "attack_fast_1";
	chr.actions.attack_fast.a2 = "attack_fast_2";
	chr.actions.attack_force.a1 = "attack_force_1";
	chr.actions.attack_force.a2 = "attack_force_2";
	chr.actions.attack_round.a1 = "attack_force_1";
	chr.actions.attack_break.a1 = "attack_force_2";
	chr.actions.attack_feint.a1 = "attack_fast_1";
	chr.actions.attack_feintc.a1 = "attack_fast_2";
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
	chr.actions.fightdead.d2 = "death_2";
	chr.actions = "";
	SendMessage(chr, "lsl", MSG_CHARACTER_EX_MSG, "SetFightWOWeapon", 1);
	SendMessage(chr, "lsl", MSG_CHARACTER_EX_MSG, "SetFightMode", 1);
	SendMessage(chr, "lffff", MSG_CHARACTER_TELEPORT_AY, stf(PdmBoarding.(side).x), stf(PdmBoarding.(side).y),
		stf(PdmBoarding.(side).z), stf(PdmBoarding.(side).ay));
	Trace("PDM boarding: " + chr.id + " (" + model + "_brd) the " + side);
}

// combat 0..10 of the card: 0.3 .. 0.9
float Board_FightLevel(ref chr)
{
	return 0.3 + 0.06 * sti(chr.skills.combat);
}

// the plates of the hero and of the enemy, their bars in the windows: the health and the energy
void Board_CreateStatus()
{
	DeleteAttribute(&BoardStatus, "");
	float top = hudH - Hud_Px(BOARD_PLATE_MARGIN + stf(PdmBoarding.hud.hero.height));
	Board_StatusPlate("hero", Hud_Px(BOARD_PLATE_MARGIN), top, false);
	Board_StatusPlate("enemy", hudW - Hud_Px(BOARD_PLATE_MARGIN + stf(PdmBoarding.hud.enemy.width)), top, true);
	CreateEntity(&BoardStatus, "IBoardingStatus");
	LayerAddObject(REALIZE, &BoardStatus, 65534);
	SendMessage(&BoardStatus, "l", LOG_INIT_CHARCTER_HP);
	Board_ShowStatus();
}

// bars hero_health, hero_energy, enemy_health, enemy_energy in this order (LOG_SET_BOARDING_BAR 0..3); the bars of
// the enemy shrink to the right, to the middle of the screen as those of the hero
void Board_StatusPlate(string side, float left, float top, bool fromRight)
{
	aref hud;
	makearef(hud, PdmBoarding.hud.(side));
	BoardStatus.frames.(side).texture = hud.texture;
	BoardStatus.frames.(side).left = left;
	BoardStatus.frames.(side).top = top;
	BoardStatus.frames.(side).width = Hud_Px(stf(hud.width));
	BoardStatus.frames.(side).height = Hud_Px(stf(hud.height));
	Board_StatusBar(side + "_health", hud, "health", left, top, fromRight, argb(255, 168, 24, 16));
	Board_StatusBar(side + "_energy", hud, "energy", left, top, fromRight, argb(255, 216, 176, 48));
}

void Board_StatusBar(string name, aref hud, string bar, float left, float top, bool fromRight, int color)
{
	BoardStatus.bars.(name).left = left + Hud_Px(stf(hud.(bar).left));
	BoardStatus.bars.(name).top = top + Hud_Px(stf(hud.(bar).top));
	BoardStatus.bars.(name).width = Hud_Px(stf(hud.(bar).width));
	BoardStatus.bars.(name).height = Hud_Px(stf(hud.(bar).height));
	BoardStatus.bars.(name).color = color;
	BoardStatus.bars.(name).backColor = argb(255, 24, 16, 12);
	BoardStatus.bars.(name).fromRight = fromRight;
}

void Board_ShowStatus()
{
	SendMessage(&BoardStatus, "llf", LOG_SET_BOARDING_BAR, 0, stf(BoardHero.hp) / BOARD_HP);
	SendMessage(&BoardStatus, "llf", LOG_SET_BOARDING_BAR, 1, stf(BoardHero.energy) / BOARD_ENERGY);
	SendMessage(&BoardStatus, "llf", LOG_SET_BOARDING_BAR, 2, stf(BoardEnemy.hp) / BOARD_HP);
	SendMessage(&BoardStatus, "llf", LOG_SET_BOARDING_BAR, 3, stf(BoardEnemy.energy) / BOARD_ENERGY);
}

void Board_Release()
{
	if (!boardActive) { return; }
	boardActive = false;
	DelEventHandler("EWhr_GetShadowDensity", "Board_ShadowDensity");
	DelEventHandler("EWhr_GetFogDensity", "Board_FogDensity");
	DelEventHandler("Location_CharacterIsFight", "Board_IsFight");
	DelEventHandler("ChrAttackAction", "Board_AttackAction");
	DelEventHandler("ChrCheckEnergy", "Board_AttackAction");
	DelEventHandler("ChrFgtActApply", "Board_ActionApply");
	DelEventHandler("Location_CharacterAttack", "Board_Attack");
	DelEventHandler("NpcEvtHP", "Board_RelHP");
	DelEventHandler("NpcEvtEny", "Board_RelEnergy");
	DelEventHandler("NpcEvtEgy", "Board_RelEnergy");
	DelEventHandler("NPC_Event_GetActionEnergy", "Board_ActionEnergy");
	DelEventHandler("NPC_Event_GetAttackActive", "Board_AiAttack");
	DelEventHandler("NPC_Event_GetAttackWeightFast", "Board_AiFast");
	DelEventHandler("NPC_Event_GetAttackWeightForce", "Board_AiForce");
	DelEventHandler("NPC_Event_GetAttackWeightRound", "Board_AiZero");
	DelEventHandler("NPC_Event_GetAttackWeightBreak", "Board_AiZero");
	DelEventHandler("NPC_Event_GetAttackWeightFeint", "Board_AiZero");
	DelEventHandler("NPC_Event_GetDefenceActive", "Board_AiDefence");
	DelEventHandler("NPC_Event_GetDefenceWeightBlock", "Board_AiBlock");
	DelEventHandler("NPC_Event_GetDefenceWeightParry", "Board_AiParry");
	DelEventHandler("NPC_Event_EnableRecoil", "Board_AiZero");
	DelEventHandler("NPC_Event_GetFireActive", "Board_AiZero");
	DelEventHandler("NPC_Event_EnableFire", "Board_AiZero");
	DelEventHandler("NPC_Event_StunChance", "Board_AiZero");
	DelEventHandler("NPC_Event_AdaptiveTargetSelect", "Board_AiZeroInt");
	DelEventHandler("NPC_IsDodgeEnabled", "Board_AiZeroInt");
	DelEventHandler("Board_Tick", "Board_Tick");
	DelEventHandler("Board_End", "Board_End");
	DeleteClass(&BoardStatus);
	Hud_ReleaseLog();
	DeleteClass(&BoardCamera);
	DeleteClass(&BoardHero);
	DeleteClass(&BoardEnemy);
	DeleteClass(&BoardGroups);
	DeleteClass(&BoardLocation);
	DeleteClass(&BoardWeather);
}

// ---------- the rules the engine asks ----------

int Board_IsFight()
{
	aref chr = GetEventData();
	return !boardOver;
}

// the energy an action of the engine takes: the action of brd_anim.idf it plays, its frames by its power by
// BOARD_POWER_COST (ours: by BOARD_COST_SCALE, of the BOARD_ENERGY full)
float Board_Cost(string action)
{
	// hit_1/3: 20 frames of 10, hit_2/4: 20 of 15
	float frames = 20.0;
	float power = 10.0;
	if (action == "force") { power = 15.0; }
	// the parry, as the block of a strong blow: block_2/4, 15 frames of 3; its blow back as a fast hit
	if (action == "parry") { frames = 15.0; power = 3.0; }
	// the recoil, the strafes: a step of the fight, as the turn turn_*_atack, 15 frames of 4
	if (action == "recoil" || action == "strafe_l" || action == "strafe_r") { frames = 15.0; power = 4.0; }
	return Board_FramesCost(frames, power);
}

float Board_FramesCost(float frames, float power)
{
	return frames * power * BOARD_POWER_COST * BOARD_COST_SCALE * BOARD_ENERGY;
}

// a blocked blow costs the one who blocks it the block of brd_anim.idf: block_1/3 (15 frames of 2) a fast
// blow, block_2/4 (15 of 3) a strong one
float Board_BlockCost(string action)
{
	if (action == "force") { return Board_FramesCost(15.0, 3.0); }
	return Board_FramesCost(15.0, 2.0);
}

// an action starts only with the energy for it
int Board_AttackAction()
{
	aref chr = GetEventData();
	string action = GetEventData();
	if (stf(chr.energy) < Board_Cost(action)) { return 0; }
	return 1;
}

void Board_ActionApply()
{
	aref chr = GetEventData();
	string action = GetEventData();
	float energy = stf(chr.energy) - Board_Cost(action);
	if (energy < 0.0) { energy = 0.0; }
	chr.energy = energy;
}

// a blade reached the enemy: the power of the hit of the original (10 fast, 15 with force), more by the combat
// of the attacker, less by the defence of the one hit; a block takes most of it
void Board_Attack()
{
	aref attacker = GetEventData();
	aref enemy = GetEventData();
	string action = GetEventData();
	int isBlocked = GetEventData();
	if (boardOver || stf(enemy.hp) <= 0.0) { return; }
	float damage = 10.0;
	if (action == "force") { damage = 15.0; }
	damage = damage * (1.0 + BOARD_COMBAT_STEP * sti(attacker.skills.combat));
	damage = damage * (1.0 - BOARD_DEFENCE_STEP * sti(enemy.skills.defence));
	string alias = "finch";
	// a block holds with the energy for it, otherwise the blow breaks through it
	if (isBlocked && stf(enemy.energy) < Board_BlockCost(action)) { isBlocked = false; }
	if (isBlocked)
	{
		damage = damage * BOARD_BLOCKED;
		alias = "block";
		enemy.energy = stf(enemy.energy) - Board_BlockCost(action);
	}
	SendMessage(&Sound, "lslllll", MSG_SOUND_PLAY, alias, PCM_STEREO, VOLUME_FX, false, false, false, 0);
	float hp = stf(enemy.hp) - damage;
	if (hp < 0.0) { hp = 0.0; }
	enemy.hp = hp;
	Board_ShowStatus();
	Trace("PDM: boarding, " + attacker.id + " hits " + enemy.id + " (" + action + ", blocked " + isBlocked + "), " + makeint(hp) + " hp");
	if (hp > 0.0) { return; }
	boardOver = true;
	// "Dead" stops the character and plays his fightdead action
	SendMessage(enemy, "ls", MSG_NPCHARACTER_SETTASK, "Dead");
	SendMessage(&Sound, "lslllll", MSG_SOUND_PLAY, "death", PCM_STEREO, VOLUME_FX, false, false, false, 0);
	if (enemy.id == BoardEnemy.id)
	{
		Sound_Music("win");
		Hud_Log(BoardEnemy.name + " повержен. Корабль захвачен!");
		Trace("PDM: boarding, the enemy falls, the ship is taken");
	}
	else
	{
		Sound_Music("die");
		Hud_Log("Вы погибли");
		Trace("PDM: boarding, the hero falls");
	}
	PostEvent("Board_End", BOARD_END_MS);
}

float Board_RelHP()
{
	aref chr = GetEventData();
	return stf(chr.hp) / BOARD_HP;
}

float Board_RelEnergy()
{
	aref chr = GetEventData();
	return stf(chr.energy) / BOARD_ENERGY;
}

float Board_ActionEnergy()
{
	aref chr = GetEventData();
	string action = GetEventData();
	return Board_Cost(action) / BOARD_ENERGY;
}

// the choices of the AI, as in the melee demo
float Board_AiAttack() { aref chr = GetEventData(); return 0.6; }
float Board_AiFast() { aref chr = GetEventData(); return 0.7; }
float Board_AiForce() { aref chr = GetEventData(); return 0.3; }
float Board_AiDefence() { aref chr = GetEventData(); return 0.5; }
float Board_AiBlock() { aref chr = GetEventData(); return 0.7; }
float Board_AiParry() { aref chr = GetEventData(); return 0.3; }
float Board_AiZero() { aref chr = GetEventData(); return 0.0; }
int Board_AiZeroInt() { return 0; }

// ---------- around the fight ----------

void Board_Tick()
{
	if (!boardActive) { return; }
	Board_Recover(&BoardHero, &BoardEnemy);
	Board_Recover(&BoardEnemy, &BoardHero);
	Board_ShowStatus();
	PostEvent("Board_Tick", BOARD_TICK_MS);
}

// the energy of Boarding.dll comes back by the combat of the fighter and how much better he is than the enemy;
// the speed of his actions falls with it (ours)
void Board_Recover(ref chr, ref enemy)
{
	float s = 0.1 * sti(chr.skills.combat);
	float rate = BOARD_REGEN + (s * 9.0 + 1.0) * BOARD_REGEN_SKILL + (s - 0.1 * sti(enemy.skills.combat)) * BOARD_REGEN_BETTER;
	if (rate < BOARD_REGEN_MIN) { rate = BOARD_REGEN_MIN; }
	if (stf(chr.hp) <= 0.0) { rate = -BOARD_DEAD_DRAIN; }
	float energy = stf(chr.energy) + rate * BOARD_ENERGY * BOARD_TICK_MS / 1000.0;
	if (energy > BOARD_ENERGY) { energy = BOARD_ENERGY; }
	if (energy < 0.0) { energy = 0.0; }
	chr.energy = energy;
	int speed = BOARD_SLOW_MIN + makeint((100 - BOARD_SLOW_MIN) * energy / BOARD_ENERGY);
	SendMessage(chr, "lsl", MSG_CHARACTER_EX_MSG, "SetAnimSpeed", speed);
}

// won: back to the sea at the island without the enemy; lost: the main menu. The autotest quits here.
void Board_End()
{
	int won = stf(BoardHero.hp) > 0.0;
	Board_Release();
	if (TownAuto == 8)
	{
		Trace("PDM: autotest done, boarding, won " + won);
		ExitProgram();
		return;
	}
	if (won) { Sea_Start(boardIsland); }
	else { Menu_Start(); }
}

ref Board_ShadowDensity()
{
	return &boardShadow;
}

float Board_FogDensity()
{
	return 0.0;
}
