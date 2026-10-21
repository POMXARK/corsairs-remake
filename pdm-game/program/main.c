// The original Sea Dogs (PDM 1.061) on Storm Engine. The original has no scripts: its logic is C++
// in the DLLs of MODULES. These scripts play the role of those DLLs on the data of the original,
// which run.sh converts: data\pdm_data.c (written by tools/pdm_data2c.py) holds its tables and cards,
// data\pdm_logic.c (tools/pdm_logic2c.py) its actions, story lines and dialogs, run by story.c,
// data\pdm_sound.c (tools/pdm_sound.py) its music and the sounds of the locations, played by sound.c.
// Stages of the port: docs/port-plan.md.

#define EXECUTE 0
#define REALIZE 1

object Render;
object Scene;

// the hero of the original, WORLDS\CHARACTERS\Nicolas Sharp.mtx
aref PlayerCard;
// the ship of the hero (SHIPS\*.shp) and its type (a record of WORLDS\Ships.idf)
aref PlayerShipCard;
aref PlayerShipType;

#include "data\pdm_data.c"
#include "data\start.c"
#include "data\pdm_logic.c"
#include "data\pdm_world.c"
#include "data\pdm_voices.c"
#include "data\pdm_voice_lines.c"
#include "data\pdm_screens.c"
#include "data\pdm_sound.c"
#include "data\pdm_hud.c"
#include "sound.c"
#include "story.c"
// before sea.c and town.c: they use its defines
#include "hud.c"
#include "sea.c"
#include "town.c"
#include "review.c"
#include "menu.c"
#include "map.c"
#include "screens.c"

void MapKey(string controlName, int keyCode)
{
	int control = CreateControl(controlName);
	MapControl(control, keyCode);
}

void Main()
{
	PdmData_Init();
	PdmLogic_Init();
	PdmWorld_Init();
	PdmVoices_Init();
	PdmVoiceLines_Init();
	PdmScreens_Init();
	PdmSound_Init();
	PdmHud_Init();
	makearef(PlayerCard, PdmCharacters.Nicolas_Sharp);
	// an attribute name in .(...) has to be a variable
	string shipKey = PlayerCard.ship_key;
	makearef(PlayerShipCard, PdmShips.(shipKey));
	string typeKey = PlayerShipCard.type_key;
	makearef(PlayerShipType, PdmShipTypes.(typeKey));
	string report = "PDM: hero " + PlayerCard.id + ", ship " + PlayerShipCard.name;
	report = report + " (" + PlayerShipType.type + "), at " + PlayerCard.address.island;
	Trace(report);

	MapKey("Pdm_Quit", 27);
	Screen_Init();
	SetEventHandler("Control Activation", "Pdm_Control", 0);

	Render.BackColor = argb(255, 0, 0, 0);
	CreateEntity(&Scene, "Scene");
	LayerAddObject(EXECUTE, &Scene, 0);
	Sound_Init();
	// run.sh writes the scene to start with (SCENE=…) into data\start.c
	if (StartScene == "story")
	{
		Story_SelfTest();
		ExitProgram();
		return;
	}
	if (StartScene == "menu" || StartScene == "menu-newgame" || StartScene == "screens")
	{
		Menu_Start();
		return;
	}
	Pdm_NewGame();
	if (StartScene == "review") { Review_Start(); }
	else if (StartScene == "town") { Town_Start(StartTown, "sea"); }
	else { Sea_Start(PlayerCard.address.island); }
}

void Pdm_Control()
{
	string control = GetEventData();
	// Escape on a screen goes back, the keys of the scene wait under it
	if (control == "Pdm_Quit" && Screen_Escape()) { return; }
	if (screenOverGame) { return; }
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
