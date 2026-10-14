// Entry point: the main menu and switching between it and the scene (scene.c).
// The menu lives in the interface layers, the scene in its own; the hidden one is frozen,
// so returning to either keeps its state. Escape in the scene opens the menu,
// "Продолжить" returns, "Новая игра" restarts the scene, "Выход" (or Escape in the menu) quits.

#include "scene.c"

#define MSG_INTERFACE_INIT 45010
#define MSG_INTERFACE_SET_NODE_USING 45016
#define MSG_INTERFACE_NEW_CURRENT_NODE 45021
#define INTERFACE_EXECUTE 4
#define INTERFACE_REALIZE 5
#define INVERSE_CONTROL 4

object GameInterface;

int inScene = 0;

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
	Scene_MapControls();

	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);

	SetEventHandler("ievnt_command", "Menu_Command", 0);
	SetEventHandler("exitCancel", "Menu_Quit", 0);
	SetEventHandler("Control Activation", "Game_Control", 0);
	SetEventHandler("frame", "Game_Frame", 0);
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
			Scene_Start();
			Game_ShowScene();
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

void Game_ShowScene()
{
	LayerFreeze(INTERFACE_EXECUTE, 1);
	LayerFreeze(INTERFACE_REALIZE, 1);
	Scene_Freeze(0);
	inScene = 1;
}

void Game_ShowMenu()
{
	Scene_Freeze(1);
	LayerFreeze(INTERFACE_EXECUTE, 0);
	LayerFreeze(INTERFACE_REALIZE, 0);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, "B_CONTINUE", 1);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_NEW_CURRENT_NODE, "B_CONTINUE");
	inScene = 0;
	Trace("MENU: shown");
}

void Game_Frame()
{
	if (inScene != 0)
	{
		Scene_Update(GetDeltaTime() * 0.001);
	}
}

void Game_Control()
{
	string control = GetEventData();
	if (inScene != 0 && control == "Scene_Menu")
	{
		Game_ShowMenu();
	}
}

void Menu_Quit()
{
	Trace("MENU: quit");
	ExitProgram();
}
