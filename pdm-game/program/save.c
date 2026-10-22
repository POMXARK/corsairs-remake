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
// TOWN_AUTO=13: the file the autotest saved from the screen and the size of the window it started in
string saveAutoFile = "";
string saveAutoSize = "";

#define SAVEFILE_KEY 114
#define SAVEFILE_LOAD_KEY 118
#define SAVEFILE_AUTO_STEP_MS 4000
#define MSG_INTERFACE_SAVE_FILE_FIND 45035
#define MSG_INTERFACE_DELETE_SAVE_FILE 45037
#define MSG_INTERFACE_DO_SAVE_DATA 45047
#define MSG_INTERFACE_GET_SAVE_DATA 45048
// the rows of the lists of "Загрузить игру" and "Сохранить игру"
#define SAVEFILE_LIST_MAX 60

// the files of the list of the screen, newest first: SaveFiles.f<row> = the name in save\
object SaveFiles;
int saveFileCount = 0;
// "Сохранить игру" has "Новая запись" in its first row
int saveFileFirst = 0;
// the rows put into the list
int saveFileRows = 0;
// the file the message box asks about: to delete or to write over
string saveFileAsked = "";

void Save_Init()
{
	MapKey("Save_Quick", SAVEFILE_KEY);
	MapKey("Save_Load", SAVEFILE_LOAD_KEY);
	SetEventHandler("Save_Auto", "Save_Auto", 0);
	SetEventHandler("FTChange", "Save_ScreenChange", 0);
	SetEventHandler("FormatedTextActivate", "Save_ScreenChange", 0);
}

// "town", "sea" or "" where the game is not saved
string Save_Where()
{
	// the menu over the game (Escape) saves the game under it, the other screens wait
	if (screenName != "" && !screenGameMenu) { return ""; }
	if (boardActive || mapActive) { return ""; }
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
	if (!optionsAutosave) { return; }
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
	savefile_info = Save_Info();
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
	if (TownAuto == SAVEFILE_SCREENS_AUTO) { Save_ScreensLoaded(); }
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

// the header of the file the lists show: the island, the town or the sea, the money
string Save_Info()
{
	string island = savePlace;
	if (saveFrom == "town") { island = townIsland; }
	string place = island;
	if (CheckAttribute(&PdmIslands, island + ".label")) { place = PdmIslands.(island).label; }
	if (saveFrom == "town") { place = place + ", город"; } else { place = place + ", в море"; }
	return place + ", " + PlayerCard.money + " золотых";
}

// ---------- the screens "Загрузить игру" and "Сохранить игру" (screens.c opens them) ----------

// the name of a file in the list: the quick save, the save leaving a town, a save of the screen (gameN)
string Save_Title(string name)
{
	if (name == "quick") { return "Быстрое сохранение"; }
	if (name == "auto") { return "Автосохранение"; }
	if (findSubStr(name, "game", 0) == 0) { return "Запись " + strcut(name, 4, strlen(name) - 1); }
	return name;
}

// the files of save\ into EDITFILES, a group a row the cursor of the list goes over (backColor of
// tools/pdm_ui.py); its header under the list
// a row of the list: the first one replaces the text of the page (an empty text would leave a row of garbage in
// a list with wrapoff, GetOneLine of the engine does not end its line), the others are added to it
void Save_ScreenRow(string line)
{
	if (saveFileRows == 0) { Screen_Text("EDITFILES", line); }
	else { SendMessage(&GameInterface, "lsle", MSG_INTERFACE_MSG_TO_NODE, "EDITFILES", 0, &line); }
	saveFileRows++;
}

void Save_ScreenFill()
{
	GameInterface.SavePath = "save";
	saveFileCount = 0;
	saveFileFirst = 0;
	saveFileRows = 0;
	if (screenName == "savegame")
	{
		saveFileFirst = 1;
		Save_ScreenRow("Новая запись");
		bool can = Save_Where() != "";
		SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_SAVE", can);
	}
	string name = "";
	int size = 0;
	string at;
	while (saveFileCount < SAVEFILE_LIST_MAX)
	{
		if (SendMessage(&GameInterface, "llee", MSG_INTERFACE_SAVE_FILE_FIND, saveFileCount, &name, &size) == 0) { break; }
		at = "f" + saveFileCount;
		SaveFiles.(at) = name;
		Save_ScreenRow(Save_Title(name));
		saveFileCount++;
	}
	// the rest of a list cut at SAVEFILE_LIST_MAX
	if (saveFileCount == SAVEFILE_LIST_MAX) { SendMessage(&GameInterface, "llee", MSG_INTERFACE_SAVE_FILE_FIND, 1000, &name, &size); }
	if (saveFileRows == 0) { Screen_Text("EDITFILES", " "); }
	bool any = saveFileCount > 0;
	if (screenName == "loadgame") { SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_LOAD", any); }
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_DELETE", any);
	SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "EDITFILES", 1, 0);
	Save_ScreenDesc();
}

// the file of the row under the cursor, "" for "Новая запись" or none
string Save_ScreenFile()
{
	// apart: the compiler drops "- saveFileFirst" after the call
	int row = SendMessage(&GameInterface, "lsl", MSG_INTERFACE_MSG_TO_NODE, "EDITFILES", 11);
	row = row - saveFileFirst;
	if (row < 0 || row >= saveFileCount) { return ""; }
	string at = "f" + row;
	return SaveFiles.(at);
}

void Save_ScreenDesc()
{
	string file = Save_ScreenFile();
	string text = "";
	if (file != "") { SendMessage(&GameInterface, "lse", MSG_INTERFACE_GET_SAVE_DATA, "save\" + file, &text); }
	if (file == "" && screenName == "savegame") { text = "Новая запись: game" + Save_FreeNumber(); }
	Screen_Text("EDITDESC", text);
}

// the first gameN not in the list
int Save_FreeNumber()
{
	int n = 1;
	bool taken = true;
	while (taken)
	{
		taken = false;
		for (int i = 0; i < saveFileCount; i++)
		{
			string at = "f" + i;
			if (SaveFiles.(at) == "game" + n) { taken = true; }
		}
		if (taken) { n++; }
	}
	return n;
}

// the cursor of the list moved (FTChange, FormatedTextActivate of the FORMATEDTEXT): the header of its file
void Save_ScreenChange()
{
	string node = GetEventData();
	if (node != "EDITFILES") { return; }
	if (screenName == "loadgame" || screenName == "savegame") { Save_ScreenDesc(); }
}

// a button of the two screens; true if it was one of theirs
bool Save_ScreenClick(string node)
{
	string file = Save_ScreenFile();
	if (node == "LB_LOAD")
	{
		if (file != "") { Save_Load("save\" + file); }
		return true;
	}
	if (node == "LB_DELETE")
	{
		if (file == "") { return true; }
		saveFileAsked = file;
		Screen_Message("'" + Save_Title(file) + "'\nВы уверены, что хотите стереть выбранную игру?", "delete");
		return true;
	}
	if (node == "LB_SAVE")
	{
		if (file == "") { Save_FromScreen("game" + Save_FreeNumber()); return true; }
		saveFileAsked = file;
		Screen_Message(Screen_Put(PdmScreens.savegame.t.overwrite, Save_Title(file)), "overwrite");
		return true;
	}
	return false;
}

// "Да" of the message box of the two screens
void Save_ScreenYes()
{
	if (screenMessageYes == "delete")
	{
		Trace("PDM save: delete " + saveFileAsked);
		SendMessage(&GameInterface, "ls", MSG_INTERFACE_DELETE_SAVE_FILE, saveFileAsked);
	}
	if (screenMessageYes == "overwrite") { Save_FromScreen(saveFileAsked); }
}

// the menu over the game saves it and goes back to the game, as the original
// written with the menu open, as the original: the engine keeps no entity in a save, the load makes the scene
// again. The header (the place, the money and the picture of the game) goes after the globals of the file
void Save_FromScreen(string file)
{
	if (!Save_Write("save\" + file)) { Trace("PDM save: not here"); return; }
	SendMessage(&GameInterface, "lss", MSG_INTERFACE_DO_SAVE_DATA, "save\" + file, savefile_info);
	Hud_Log("Игра сохранена");
	screenNext = "";
	screenGoing = true;
	PostEvent("Screen_Go", 0);
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

// ---------- TOWN_AUTO=13 with SCENE=sea: the screens of the menu over the game ----------
// "Сохранить игру" writes a new file, "Загрузить игру" shows its header and loads it, then deletes it with
// "Да" of the message box; "Настройки" give the window another size and the first one back

void Save_ScreensStart()
{
	saveAutoStep = 0;
	SetEventHandler("Save_ScreensStep", "Save_ScreensStep", 0);
	SetEventHandler("Save_ScreensSaved", "Save_ScreensSaved", 0);
	PostEvent("Save_ScreensStep", SAVEFILE_AUTO_STEP_MS);
}

void Save_ScreensSaved()
{
	saveAutoStep = 2;
}

// the step after the load is the one saved with the game
void Save_ScreensLoaded()
{
	SetEventHandler("Save_ScreensStep", "Save_ScreensStep", 0);
	PostEvent("Save_ScreensStep", SAVEFILE_AUTO_STEP_MS);
}

void Save_ScreensClick(string node)
{
	Trace("PDM save: autotest, " + screenName + " " + node);
	PostEvent("ievnt_command", 0, "ss", "click", node);
}

// the cursor of the list on the file saved by the autotest
void Save_ScreensSelect()
{
	for (int i = 0; i < saveFileCount; i++)
	{
		string at = "f" + i;
		if (SaveFiles.(at) == saveAutoFile)
		{
			SendMessage(&GameInterface, "lsll", MSG_INTERFACE_MSG_TO_NODE, "EDITFILES", 1, i + saveFileFirst);
			Save_ScreenDesc();
		}
	}
	string text = "";
	SendMessage(&GameInterface, "lse", MSG_INTERFACE_GET_SAVE_DATA, "save\" + Save_ScreenFile(), &text);
	Trace("PDM save: autotest, " + saveFileCount + " files, the cursor on " + Save_ScreenFile() + ": " + text);
}

void Save_ScreensStep()
{
	int step = saveAutoStep;
	saveAutoStep++;
	PostEvent("Save_ScreensStep", SAVEFILE_AUTO_STEP_MS);
	if (step == 0 || step == 2 || step == 4) { Screen_GameMenu(); }
	if (step == 0) { Save_ScreensClick("LB_SAVEGAME"); }
	if (step == 1)
	{
		saveAutoFile = "game" + Save_FreeNumber();
		Trace("PDM save: autotest, " + saveFileCount + " files, saving " + saveAutoFile);
		// the file keeps the step after the load, the game goes on with the next one when it is written
		saveAutoStep = 4;
		Trace("PDM save: autotest, the row " + SendMessage(&GameInterface, "lsl", MSG_INTERFACE_MSG_TO_NODE, "EDITFILES", 11) + ", the file '" + Save_ScreenFile() + "'");
		Save_ScreensClick("LB_SAVE");
		PostEvent("Save_ScreensSaved", 500);
	}
	if (step == 2 || step == 4) { Save_ScreensClick("LB_LOADGAME"); }
	if (step == 3) { Save_ScreensSelect(); Save_ScreensClick("LB_LOAD"); }
	if (step == 5) { Trace("PDM save: autotest, loaded " + savefile_info); Save_ScreensSelect(); Save_ScreensClick("LB_DELETE"); }
	if (step == 6) { Save_ScreensClick("LB_YES"); }
	if (step == 7) { Save_ScreensSelect(); Save_ScreensClick("LB_EXIT"); }
	if (step == 8) { Save_ScreensClick("LB_OPTIONS"); }
	if (step == 9)
	{
		saveAutoSize = Options_Current();
		optionsSize = "1600x900";
		if (saveAutoSize == optionsSize) { optionsSize = "1280x720"; }
		Save_ScreensClick("LB_APPLY");
	}
	if (step == 10)
	{
		Trace("PDM save: autotest, the window " + Options_Current() + " on " + screenName);
		optionsSize = saveAutoSize;
		Save_ScreensClick("LB_APPLY");
	}
	if (step == 11)
	{
		Trace("PDM save: autotest, the window " + Options_Current() + " on " + screenName);
		Trace("PDM: autotest done, screens");
		ExitProgram();
	}
}
