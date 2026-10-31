// The original Sea Dogs (PDM 1.061) on Storm Engine. The original has no scripts: its logic is C++
// in the DLLs of MODULES. These scripts play the role of those DLLs on the data of the original,
// which run.sh converts: data\pdm_data.c (written by tools/pdm_data2c.py) holds its tables and cards,
// data\pdm_logic.c (tools/pdm_logic2c.py) its actions, story lines and dialogs, run by story.c,
// data\pdm_sound.c (tools/pdm_sound.py) its music and the sounds of the locations, played by sound.c,
// data\pdm_boarding.c (tools/pdm_boarding.py) the cabin of the boarding, fought in boarding.c.
// Stages of the port: docs/port-plan.md.

#define EXECUTE 0
#define REALIZE 1
// save.c, here for the files included before it: the files of the quick save and of the save made leaving a town,
// the delay of that one, the autotest of saving and loading. SAVEFILE_, not SAVE_: the compiler does not tell
// the case of names, SAVE_QUICK would be the function Save_Quick
// the saves of a test run (TOWN_AUTO) go to save-test, not to the saves of the player: RUN_SAVEDIR, RUN_SAVEPFX of start.c (run.sh);
// the quick save is RUN_SAVEPFX + "quick", the auto one RUN_SAVEPFX + "auto" (a define cannot hold the +)
#define SAVEFILE_AUTO_MS 1000
#define SAVEFILE_AUTO 12
#define SAVEFILE_SCREENS_AUTO 13
// the resolution of the page «Настройки» over the game (options.c). OPTIONSAUTO_, not OPTIONS_AUTO:
// the compiler does not tell the case of names, OPTIONS_AUTO would be taken inside Options_Auto...
#define OPTIONSAUTO_ID 14
// the same page in a live scene, but it also CLOSES after the resolution change, so the world keeps
// rendering in the new window for a while (docs/dynamic-resolution.md, the picture after the close)
#define OPTCLOSE_ID 15
// the arrows of the main menu step over the unselectable items (menu.c, Menu_ArrowsStart)
#define MENUARROWS_ID 16
// SCENE=town: the dialog with the shipyard owner opens the screen of the shipyard, its values are checked (screens.c, Screen_ShipyardCheck)
#define SHIPYARD_ID 19
// the same with the store owner and the screen of the trade (trade.c, Trade_Check)
#define STORE_ID 21
// F1 in the town and the pages of the status: ship, goods, chest, log book (screens.c, Screen_StatusAuto)
#define STATUS_ID 22
// the same for the pages of RANSACK.dll, which a boarding opens in the original: ship exchange, transfer, message box
#define RANSACKSCR_ID 23

object Render;
object Scene;

// the hero of the original, WORLDS\CHARACTERS\Nicolas Sharp.mtx
aref PlayerCard;
// the ship of the hero (SHIPS\*.shp) and its type (a record of WORLDS\Ships.idf)
aref PlayerShipCard;
aref PlayerShipType;

#include "data\pdm_data.c"
#include "data\pdm_trade.c"
#include "data\pdm_encounters.c"
#include "keys.c"
#include "data\start.c"
#include "data\pdm_logic.c"
#include "data\pdm_world.c"
#include "data\pdm_voices.c"
#include "data\pdm_voice_lines.c"
#include "data\pdm_screens.c"
#include "data\pdm_sound.c"
#include "data\pdm_hud.c"
#include "data\pdm_boarding.c"
#include "data\pdm_cutscenes.c"
#include "data\pdm_weather.c"
#include "sound.c"
#include "story.c"
// before sea.c and town.c: they use its defines
#include "hud.c"
#include "sea.c"
#include "autotest\sea_sail.c"
#include "autotest\town_face.c"
#include "battle.c"
#include "fort.c"
#include "town.c"
#include "boarding.c"
#include "review.c"
#include "cutscene.c"
#include "menu.c"
#include "map.c"
#include "encounter.c"
#include "trade.c"
#include "screens.c"
#include "save.c"
#include "options.c"

void MapKey(string controlName, int keyCode)
{
	int control = CreateControl(controlName);
	MapControl(control, keyCode);
}

void Main()
{
	Keys_Init();
	PdmData_Init();
	PdmTrade_Init();
	PdmEncounters_Init();
	Trace("PDM main: pdm_data.c done");
	PdmLogic_Init();
	Trace("PDM main: pdm_logic.c done");
	PdmWorld_Init();
	Trace("PDM main: pdm_world.c done");
	PdmVoices_Init();
	Trace("PDM main: pdm_voices.c done");
	PdmVoiceLines_Init();
	Trace("PDM main: pdm_voice_lines.c done");
	PdmScreens_Init();
	Trace("PDM main: pdm_screens.c done");
	PdmSound_Init();
	Trace("PDM main: pdm_sound.c done");
	PdmHud_Init();
	Trace("PDM main: pdm_hud.c done");
	PdmBoarding_Init();
	PdmCut_Init();
	PdmWeather_Init();
	Trace("PDM main: pdm_boarding.c done");
	makearef(PlayerCard, PdmCharacters.Nicolas_Sharp);
	// the gold of a new game: "Деньги 1000" on the screens of the original
	if (!CheckAttribute(PlayerCard, "money")) { PlayerCard.money = 1000; }
	// an attribute name in .(...) has to be a variable
	string shipKey = PlayerCard.ship_key;
	makearef(PlayerShipCard, PdmShips.(shipKey));
	string typeKey = PlayerShipCard.type_key;
	makearef(PlayerShipType, PdmShipTypes.(typeKey));
	string report = "PDM: hero " + PlayerCard.id + ", ship " + PlayerShipCard.name;
	report = report + " (" + PlayerShipType.type + "), at " + PlayerCard.address.island;
	Trace(report);

	Pdm_Base();
	// run.sh writes the scene to start with (SCENE=…) into data\start.c
	if (StartScene == "story")
	{
		Story_SelfTest();
		ExitProgram();
		return;
	}
	if (StartScene == "menu" || StartScene == "menu-newgame" || StartScene == "screens")
	{
		if (TownAuto == OPTIONSAUTO_ID) { Opt_AutoStart(); } // the options page of the main menu changes the screen
		if (TownAuto == OPTCLOSE_ID) { Opt_CloseStart(); } // the same, over a live scene and closed at the end
		if (TownAuto == 45) { Opt_ControlsStart(); } // the page of the controls is filled and scrolls
		if (TownAuto == 46) { Opt_KeysStart(); } // the keys of the page of the controls are rebound and reset
	Menu_Start();
		return;
	}
	if (StartScene == "cutscene") { Cut_Start("intro", "exit"); return; }
	// SCENE=cutscene-<movie> plays one movie of DESC (bunt, death, scene8...) and quits
	if (findSubStr(StartScene, "cutscene-", 0) == 0) { Cut_Start(strcut(StartScene, 9, strlen(StartScene) - 1), "exit"); return; }
	Pdm_NewGame();
	if (StartScene == "review") { Review_Start(); }
	else if (StartScene == "town") { Town_Start(StartTown, "sea"); }
	else if (StartScene == "battle") { Battle_Start(); }
	else { Sea_Start(PlayerCard.address.island); }
	if (TownAuto == SAVEFILE_AUTO) { Save_AutoStart(); }
	if (TownAuto == SAVEFILE_SCREENS_AUTO) { Save_ScreensStart(); }
	if (TownAuto == OPTIONSAUTO_ID) { Opt_AutoStart(); }
}

// what every scene stands on: the keys and the handlers of the game, the scene and the sound; a loaded game
// (save.c OnLoad) makes them again, the engine has erased them
void Pdm_Base()
{
	MapKey("Pdm_Quit", 27);
	Save_Init();
	Screen_Init();
	Options_Init();
	SetEventHandler("Control Activation", "Pdm_Control", 0);

	Render.BackColor = argb(255, 0, 0, 0);
	CreateEntity(&Scene, "Scene");
	LayerAddObject(EXECUTE, &Scene, 0);
	Sound_Init();
}

void Pdm_Control()
{
	string control = GetEventData();
	if (Keys_Control(control)) { return; }
	// Escape on a screen goes back, the keys of the scene wait under it
	if (control == "Pdm_Quit" && Screen_Escape()) { return; }
	// F7 loads anywhere, even from the menu; F3 saves only in the game (save.c)
	if (control == "Save_Load") { Save_Load(RUN_SAVEPFX + "quick"); return; }
	if (screenOverGame) { return; }
	if (control == "Save_Quick") { Save_Quick(); return; }
	if (control == "Screen_Status") { Screen_Status(); return; }
	Sea_Control(control);
	// Escape in a dialog only leaves it, in the commands of the toolbar only closes them (the script hears the
	// key before the battle interface does, the menu is still open)
	// Escape in the game opens the main menu over it: "Продолжить" goes back, "Выход" asks and quits (ours)
	if (control == "Pdm_Quit" && townTalkNpc < 0 && !Hud_MenuOpen())
	{
		// the main menu before a game: "Выход" asks, as its button does
		if (screenName == "mainmenu") { Screen_Message(PdmScreens.mainmenu.t.exit, "exit"); return; }
		Screen_GameMenu();
	}
}
