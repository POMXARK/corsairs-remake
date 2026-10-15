// Entry point: the main menu and the scenes, the port (port.c) and the sea battle (sea.c), in the
// world they share (world.c). The menu lives in the interface layers, the scenes in their own; the
// hidden one is frozen, so returning to either keeps its state. Escape in a scene opens the menu,
// "Продолжить" returns, "Новая игра" starts in the port, "Выход" (or Escape in the menu) quits.
// Going from one scene to the other deletes the first and makes the second in the next frame.

#include "world.c"
#include "sea.c"
#include "port.c"

#define MSG_INTERFACE_INIT 45010
#define MSG_INTERFACE_SET_NODE_USING 45016
#define MSG_INTERFACE_NEW_CURRENT_NODE 45021
#define INTERFACE_EXECUTE 4
#define INTERFACE_REALIZE 5
#define INVERSE_CONTROL 4

object GameInterface;

int inScene = 0;
// "port", "sea", or "" while the game goes from one to the other
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
	Port_MapControls();
	Sea_MapControls();

	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);

	SetEventHandler("ievnt_command", "Menu_Command", 0);
	SetEventHandler("exitCancel", "Menu_Quit", 0);
	SetEventHandler("Control Activation", "Game_Control", 0);
	SetEventHandler("Game_Enter", "Game_Enter", 0);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\mainmenu.ini");
	// nothing to continue yet
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "B_CONTINUE", 0);
	Trace("MENU: loaded");
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
	Game_ShowScene();
	Game_GoTo("port");
}

void Game_GoTo(string scene)
{
	if (currentScene == "port") { Port_Leave(); }
	if (currentScene == "sea") { Sea_Leave(); }
	currentScene = "";
	PostEvent("Game_Enter", 1, "s", scene);
}

void Game_Enter()
{
	string scene = GetEventData();
	currentScene = scene;
	if (scene == "port") { Port_Enter(); }
	if (scene == "sea") { Sea_Enter(); }
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
	// Escape in the dialog only leaves the conversation
	if (control == "Scene_Menu" && !dialogOpen)
	{
		Game_ShowMenu();
		return;
	}
	if (currentScene == "port") { Port_Control(control); }
	if (currentScene == "sea") { Sea_Control(control); }
}

void Menu_Quit()
{
	Trace("MENU: quit");
	ExitProgram();
}
