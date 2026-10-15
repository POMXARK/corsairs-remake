// Entry point: the main menu and the scenes, the port (port.c) with its market (trade.c), the world
// map (map.c), the sea battle (sea.c) and the boarding (deck.c), in the
// world they share (world.c). The menu lives in the interface layers, the scenes in their own; the
// hidden one is frozen, so returning to either keeps its state. Escape in a scene opens the menu,
// "Продолжить" returns, "Новая игра" starts in the port, "Выход" (or Escape in the menu) quits.
// Going from one scene to the other deletes the first and makes the second in the next frame.
// F5 in the port saves the game, «Загрузить» loads it: SaveEngineState writes every script variable,
// LoadEngineState deletes all entities, restores the variables and calls OnLoad, which makes the
// menu, the world and the port again.

#include "world.c"
#include "sea.c"
#include "port.c"
#include "deck.c"
#include "map.c"
#include "trade.c"

#define MSG_INTERFACE_INIT 45010
#define MSG_INTERFACE_SET_NODE_USING 45016
#define MSG_INTERFACE_NEW_CURRENT_NODE 45021
#define INTERFACE_EXECUTE 4
#define INTERFACE_REALIZE 5
#define INVERSE_CONTROL 4

// the file is looked up through the resource paths: the folder must exist when the engine starts
#define SAVE_FILE "save\game.sav"

object GameInterface;
// lists the files of a folder into its attributes when created
object SaveFinder;
// written into the header of the save file
string savefile_info = "";

int inScene = 0;
// "port", "map", "sea", "deck", or "" while the game goes from one to the other
string currentScene = "";

void MapKey(string controlName, int keyCode, int flags)
{
	int control = CreateControl(controlName);
	MapControl(control, keyCode);
	if (flags != 0)
	{
		SetControlFlags(control, flags);
	}
}

void Main()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	MapKey("ILClick", 1, 0);
	MapKey("IRClick", 2, 0);
	MapKey("ITurnH", 256, 0);
	MapKey("ITurnV", 257, INVERSE_CONTROL);
	MapKey("IUp", 38, 0);
	MapKey("IDown", 40, 0);
	MapKey("IAction", 13, 0);
	MapKey("ICancel", 27, 0);
	MapKey("Scene_Menu", 27, 0);
	MapKey("Game_Save", 116, 0);
	Port_MapControls();
	Sea_MapControls();
	Deck_MapControls();
	Map_MapControls();
	Menu_Create();
	Trace("MENU: loaded");
}

// the controls stay after a load, the entities and the event handlers are made again
void Menu_Create()
{
	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);

	SetEventHandler("ievnt_command", "Menu_Command", 0);
	SetEventHandler("exitCancel", "Menu_Quit", 0);
	SetEventHandler("Control Activation", "Game_Control", 0);
	SetEventHandler("Control Deactivation", "Game_ControlUp", 0);
	SetEventHandler("Game_Enter", "Game_Enter", 0);
	Deck_SetHandlers();
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\mainmenu.ini");
	// nothing to continue yet
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "B_CONTINUE", 0);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "B_LOAD", SaveExists());
}

void Menu_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command == "click" || command == "activate")
	{
		Trace("MENU: " + node);
		if (node == "B_NEWGAME")
		{
			Game_New();
		}
		if (node == "B_LOAD")
		{
			Game_Load();
		}
		if (node == "B_CONTINUE")
		{
			Game_ShowScene();
		}
		if (node == "B_QUIT")
		{
			Menu_Quit();
		}
	}
	if (command == "deactivate")
	{
		Menu_Quit();
	}
}

// a new game starts in the port, with the world made at the first one
void Game_New()
{
	World_Create();
	Game_ResetState();
	Trade_Reset();
	Map_Reset();
	Game_ShowScene();
	Game_GoTo("port");
}

void Game_GoTo(string scene)
{
	if (currentScene == "port") { Port_Leave(); }
	if (currentScene == "sea") { Sea_Leave(); }
	if (currentScene == "deck") { Deck_Leave(); }
	if (currentScene == "map") { Map_Leave(); }
	currentScene = "";
	PostEvent("Game_Enter", 1, "s", scene);
}

void Game_Enter()
{
	string scene = GetEventData();
	currentScene = scene;
	if (scene == "port") { Port_Enter(); }
	if (scene == "sea") { Sea_Enter(); }
	if (scene == "deck") { Deck_Enter(); }
	if (scene == "map") { Map_Enter(); }
}

void Game_ShowScene()
{
	LayerFreeze(INTERFACE_EXECUTE, 1);
	LayerFreeze(INTERFACE_REALIZE, 1);
	World_Freeze(0);
	inScene = 1;
}

void Game_ShowMenu()
{
	World_Freeze(1);
	LayerFreeze(INTERFACE_EXECUTE, 0);
	LayerFreeze(INTERFACE_REALIZE, 0);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "B_CONTINUE", 1);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_NEW_CURRENT_NODE, "B_CONTINUE");
	inScene = 0;
	Trace("MENU: shown");
}

void Game_Control()
{
	string control = GetEventData();
	if (inScene == 0 || currentScene == "")
	{
		return;
	}
	if (control == "Game_Save")
	{
		Game_Save();
		return;
	}
	// Escape in the dialog only leaves the conversation
	if (control == "Scene_Menu" && !dialogOpen)
	{
		Game_ShowMenu();
		return;
	}
	if (currentScene == "port") { Port_Control(control); }
	if (currentScene == "sea") { Sea_Control(control); }
	if (currentScene == "deck") { Deck_Control(control); }
}

// a held control let go: only the sea aims while the button is down
void Game_ControlUp()
{
	string control = GetEventData();
	if (currentScene == "sea") { Sea_ControlUp(control); }
}

void Menu_Quit()
{
	Trace("MENU: quit");
	ExitProgram();
}

// ---------------------------------------------------------------- save and load

// FINDFILESINTODIRECTORY fills filelist with the files of dir matching mask when it is created
int SaveExists()
{
	DeleteAttribute(&SaveFinder, "");
	SaveFinder.dir = "save";
	SaveFinder.mask = "game.sav";
	CreateEntity(&SaveFinder, "FINDFILESINTODIRECTORY");
	DeleteClass(&SaveFinder);
	aref files;
	makearef(files, SaveFinder.filelist);
	if (GetAttributesNum(files) > 0) { return 1; }
	return 0;
}

// The battle lives in entities the save does not keep (SEA_AI, the balls in flight): the game is
// saved in the port only.
void Game_Save()
{
	if (currentScene != "port" || dialogOpen)
	{
		Log("Сохраниться можно только в порту");
		return;
	}
	SaveEngineState(SAVE_FILE);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "B_LOAD", 1);
	Log("Игра сохранена: " + gold + " песо, побед: " + wins);
	Trace("SAVE: saved, gold " + gold + " wins " + wins);
}

// called by SaveEngineState before the variables are written
void OnSave()
{
	Port_RememberHero();
	savefile_info = Market_PortName(Trade_Here()) + ", " + gold + " песо, побед: " + wins;
}

// the load itself happens at the start of the next frame, then OnLoad continues
void Game_Load()
{
	if (!SaveExists()) { return; }
	Trace("SAVE: loading");
	LoadEngineState(SAVE_FILE);
}

// The variables are back as they were saved, the entities and the event handlers are gone.
void OnLoad()
{
	worldCreated = 0;
	wavesSound = 0;
	inPort = 0;
	inDeck = 0;
	inMap = 0;
	dialogOpen = 0;
	castOff = 0;
	currentScene = "";
	Menu_Create();
	World_Create();
	portSpawn = "save";
	Game_ShowScene();
	PostEvent("Game_Enter", 1, "s", "port");
	Trace("SAVE: loaded, gold " + gold + " wins " + wins);
}
