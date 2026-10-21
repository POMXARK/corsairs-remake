// The main menu of the original (MENU.dll): the screen is [MainMenu] of INI/menu.ini converted by
// tools/pdm_ui.py into resource\ini\interfaces\mainmenu.ini. "Новая Игра" starts the game at sea,
// "Выход" quits; the other screens come with the later stages (P9). Without a game "Сохранить" and
// "Продолжить" cannot be chosen, as in the original.
// SCENE=menu-newgame presses "Новая Игра" by itself after a while (the test without key presses).

#define MSG_INTERFACE_INIT 45010
#define MSG_INTERFACE_RELEASE 45011
#define MSG_INTERFACE_SET_SELECTABLE 45024
#define INTERFACE_EXECUTE 4
#define INTERFACE_REALIZE 5
#define INVERSE_CONTROL 4

object GameInterface;

void Menu_MapKey(string controlName, int keyCode, int flags)
{
	int control = CreateControl(controlName);
	MapControl(control, keyCode);
	if (flags != 0) { SetControlFlags(control, flags); }
}

void Menu_Start()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	Menu_MapKey("ILClick", 1, 0);
	Menu_MapKey("IRClick", 2, 0);
	Menu_MapKey("ITurnH", 256, 0);
	Menu_MapKey("ITurnV", 257, INVERSE_CONTROL);
	Menu_MapKey("IUp", 38, 0);
	Menu_MapKey("IDown", 40, 0);
	Menu_MapKey("IAction", 13, 0);

	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);
	SetEventHandler("ievnt_command", "Menu_Command", 0);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\mainmenu.ini");
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_SAVEGAME", 0);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_RESUMEGAME", 0);
	Sound_Music("Main");
	Trace("PDM menu: main menu");
	if (StartScene == "menu-newgame")
	{
		PostEvent("ievnt_command", 6000, "ss", "click", "LB_NEWGAME");
	}
}

void Menu_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command != "click" && command != "activate") { return; }
	Trace("PDM menu: " + node);
	if (node == "LB_NEWGAME") { Menu_NewGame(); return; }
	if (node == "LB_EXIT") { ExitProgram(); }
}

void Menu_NewGame()
{
	DelEventHandler("ievnt_command", "Menu_Command");
	SendMessage(&GameInterface, "l", MSG_INTERFACE_RELEASE);
	DeleteClass(&GameInterface);
	Pdm_NewGame();
	Sea_Start();
}
