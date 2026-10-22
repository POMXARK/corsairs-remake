// Saving and loading the game, as the original: F3 saves quickly, F7 loads the quick save, the game saves itself
// when the ship leaves a town (save\auto). The engine writes every global of the scripts into the file
// (SaveEngineState, with OnSave before it) and, loading one, erases every entity and handler, reads the
// globals back and calls OnLoad: that makes the scene again where the game was saved, the town at the hero
// or the sea at the ship. The files are in save\ of the game folder (run.sh makes it).
// Not saved, as in the original where it went wrong: a battle, a boarding, a dialog, a screen, the world map.
// The ship comes back whole: its damage lives on the ship entity (ours, a later stage).

// what the save was made in: "town" or "sea", and where: the location, or the island at sea
string saveFrom = "";
string savePlace = "";
// the hero in the town, the ship at sea; false where the ship had not written its place yet
bool saveHasPos = false;
float saveX = 0.0;
float saveY = 0.0;
float saveZ = 0.0;
float saveAy = 0.0;
// the header of the file, read by the engine
string savefile_info = "";
// TOWN_AUTO=12: the step of the autotest, saved with the game as everything else
int saveAutoStep = 0;

#define SAVEFILE_KEY 114
#define SAVEFILE_LOAD_KEY 118
#define SAVEFILE_AUTO_STEP_MS 4000

void Save_Init()
{
	MapKey("Save_Quick", SAVEFILE_KEY);
	MapKey("Save_Load", SAVEFILE_LOAD_KEY);
	SetEventHandler("Save_Auto", "Save_Auto", 0);
}

// "town", "sea" or "" where the game is not saved
string Save_Where()
{
	if (screenName != "" || boardActive || mapActive) { return ""; }
	if (townLoaded && townTalkNpc < 0) { return "town"; }
	if (seaActive && !seaBattle && !fortActive) { return "sea"; }
	return "";
}

bool Save_Write(string file)
{
	if (Save_Where() == "") { return false; }
	SaveEngineState(file);
	Trace("PDM save: " + file + ", " + savefile_info);
	return true;
}

void Save_Quick()
{
	if (Save_Write(SAVEFILE_QUICK)) { Hud_Log("Игра сохранена"); }
	else { Trace("PDM save: not here"); }
}

void Save_Auto()
{
	Save_Write(SAVEFILE_AUTOSAVE);
}

// the engine loads the file at the start of the next frame and calls OnLoad; a file that is not there is
// not loaded, the game goes on
void Save_Load(string file)
{
	Trace("PDM save: loading " + file);
	LoadEngineState(file);
}

// called by the engine before it writes the globals
void OnSave()
{
	saveFrom = Save_Where();
	saveHasPos = false;
	if (saveFrom == "town")
	{
		savePlace = townHere;
		SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &saveX, &saveY, &saveZ);
		SendMessage(&TownHero, "le", MSG_CHARACTER_GETAY, &saveAy);
		saveHasPos = true;
	}
	if (saveFrom == "sea")
	{
		savePlace = seaAt;
		if (CheckAttribute(&SeaShips[seaHero], "ship.pos.x"))
		{
			saveX = stf(SeaShips[seaHero].ship.pos.x);
			saveZ = stf(SeaShips[seaHero].ship.pos.z);
			saveAy = stf(SeaShips[seaHero].ship.ang.y);
			saveHasPos = true;
		}
	}
	savefile_info = saveFrom + " " + savePlace + ", " + PlayerCard.money + " money";
}

// called by the engine after it has read the globals back: the entities and the handlers are gone, the flags
// of the scenes still say what was there
void OnLoad()
{
	Trace("PDM save: loaded " + savefile_info + ", at " + saveX + ", " + saveZ);
	Save_ClearScenes();
	Pdm_Base();
	// the town keeps its handlers from its first start; landing after a load needs them as well
	Town_Handlers();
	if (saveFrom == "sea")
	{
		seaLoadPos = saveHasPos;
		seaLoadX = saveX;
		seaLoadZ = saveZ;
		seaLoadAy = saveAy;
		Sea_Start(savePlace);
	}
	else { Save_LoadTown(); }
	if (TownAuto == SAVEFILE_AUTO) { Save_AutoLoaded(); }
}

void Save_ClearScenes()
{
	seaActive = false;
	seaShipCount = 0;
	seaHero = -1;
	seaFromMap = false;
	hudSea = false;
	hudLand = false;
	hudAction = "";
	townLoaded = false;
	townNpcCount = 0;
	townTalkNpc = -1;
	townGen++;
	screenName = "";
	screenNext = "";
	screenPending = "";
	screenOverGame = false;
	screenGameMenu = false;
	screenGoing = false;
	menuStarting = false;
	mapActive = false;
	boardActive = false;
	fortActive = false;
	battleEnemy = -1;
	// the music starts again (the original lost it after a load)
	soundMusic = "";
	soundMusicId = 0;
	// the controls outlive the load: a dialog or a screen may have locked or frozen them
	Town_LockHero(false);
	LayerFreeze(EXECUTE, false);
	SetTimeScale(1.0);
}

// the location of the save with the hero where he stood; townStreet and townIsland are read back with the
// game, the hero comes out of the street of an interior as before
void Save_LoadTown()
{
	if (townIsland != "") { Sound_TownMusic(sti(PdmIslands.(townIsland).nation)); }
	Town_Load(savePlace, "sea");
	if (saveHasPos)
	{
		SendMessage(&TownHero, "lffff", MSG_CHARACTER_TELEPORT_AY, saveX, saveY, saveZ, saveAy);
		aref data;
		makearef(data, PdmLocations.(savePlace));
		townArriveExit = Town_ExitAt(data, &TownHero);
	}
	PostEvent("Town_Tick", TOWN_TICK_MS);
}

// ---------- TOWN_AUTO=12 with SCENE=sea: save at sea, land, load, back at sea; land, save in the town, load ----------

void Save_AutoStart()
{
	saveAutoStep = 0;
	SetEventHandler("Save_AutoStep", "Save_AutoStep", 0);
	PostEvent("Save_AutoStep", SAVEFILE_AUTO_STEP_MS);
}

// the handlers are gone with the load, the step after the save goes on
void Save_AutoLoaded()
{
	saveAutoStep++;
	SetEventHandler("Save_AutoStep", "Save_AutoStep", 0);
	PostEvent("Save_AutoStep", SAVEFILE_AUTO_STEP_MS);
}

void Save_AutoStep()
{
	float x, y, z;
	if (saveAutoStep == 0 || saveAutoStep == 3)
	{
		saveAutoStep++;
		Save_Quick();
		if (saveFrom == "sea") { PostEvent("Sea_ToPort", 0); }
		if (saveFrom == "town")
		{
			// away from where it was saved, the load has to bring him back
			SendMessage(&TownHero, "lffff", MSG_CHARACTER_TELEPORT_AY, saveX + 2.0, saveY, saveZ + 2.0, saveAy);
		}
		PostEvent("Save_AutoStep", SAVEFILE_AUTO_STEP_MS);
		return;
	}
	if (saveAutoStep == 1 || saveAutoStep == 4)
	{
		Save_Load(SAVEFILE_QUICK);
		return;
	}
	if (saveAutoStep == 2)
	{
		x = stf(SeaShips[seaHero].ship.pos.x);
		z = stf(SeaShips[seaHero].ship.pos.z);
		Trace("PDM save: autotest, the ship at " + x + ", " + z + ", saved at " + saveX + ", " + saveZ);
		saveAutoStep++;
		PostEvent("Sea_ToPort", 0);
		PostEvent("Save_AutoStep", SAVEFILE_AUTO_STEP_MS);
		return;
	}
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	Trace("PDM save: autotest, the hero in " + townHere + " at " + x + ", " + z + ", saved at " + saveX + ", " + saveZ);
	Trace("PDM: autotest done, save");
	ExitProgram();
}
