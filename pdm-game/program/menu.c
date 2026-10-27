// The main menu of the original (MENU.dll): the screen is [MainMenu] of INI/menu.ini converted by
// tools/pdm_ui.py into resource\ini\interfaces\mainmenu.ini. "Новая Игра" starts the game in the town of the hero,
// "Выход" quits; "Настройки", "Загрузить" and "Авторы" open their pages (screens.c), what they do comes
// with the later stages (P9).
// SCENE=menu-newgame presses "Новая Игра" by itself after a while (the test without key presses).

#define MSG_INTERFACE_INIT 45010
#define MSG_INTERFACE_RELEASE 45011
#define MSG_INTERFACE_SET_SELECTABLE 45024
#define MSG_INTERFACE_MSG_TO_NODE 45045
#define INTERFACE_EXECUTE 4
#define INTERFACE_REALIZE 5
#define INVERSE_CONTROL 4

object GameInterface;
// the picture of the game for the header of a save (screens.c)
object ScrShoter;
// "click" and "activate" of one press, or Enter held, must start one game
bool menuStarting = false;

void Menu_MapKey(string controlName, int keyCode, int flags)
{
	int control = CreateControl(controlName);
	MapControl(control, keyCode);
	if (flags != 0) { SetControlFlags(control, flags); }
}

// the controls XINTERFACE reads, for the menu and the world map (map.c)
void Menu_InterfaceKeys()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	Menu_MapKey("ILClick", 1, 0);
	Menu_MapKey("IRClick", 2, 0);
	Menu_MapKey("ITurnH", 256, 0);
	Menu_MapKey("ITurnV", 257, INVERSE_CONTROL);
	Menu_MapKey("IUp", 38, 0);
	Menu_MapKey("IDown", 40, 0);
	Menu_MapKey("IAction", 13, 0);
}

void Menu_Start()
{
	Menu_InterfaceKeys();
	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);
	SetEventHandler("ievnt_command", "Menu_Command", 0);
	SetEventHandler("Menu_NewGame", "Menu_NewGame", 0);
	Screen_Show("mainmenu");
	Sound_Music("Main");
	Trace("PDM menu: main menu");
	if (StartScene == "menu-newgame")
	{
		PostEvent("ievnt_command", 6000, "ss", "click", "LB_NEWGAME");
	}
	if (StartScene == "screens") { PostEvent("Screen_Tour", SCREEN_AUTO_MS); }
}

void Menu_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command != "click" && command != "activate") { return; }
	Trace("PDM menu: " + node);
	if (Screen_Page(node)) { return; }
	if (screenName != "mainmenu" || node != "LB_EXIT") { if (Screen_Click(node)) { return; } }
	if (screenName == "messagebox" && node == "LB_YES" && screenMessageYes == "exit") { ExitProgram(); }
	if (screenName != "mainmenu") { return; }
	// the button is still being pressed: the interface goes away after the event, not inside it,
	// or the engine touches the deleted button (a crash on Enter)
	if (node == "LB_NEWGAME" && !menuStarting) { menuStarting = true; PostEvent("Menu_NewGame", 0); return; }
	// "Выход" asks first, as in the original: t_Exit in the message box, "Да" quits
	if (node == "LB_EXIT") { Screen_Message(PdmScreens.mainmenu.t.exit, "exit"); }
}

void Menu_NewGame()
{
	DelEventHandler("ievnt_command", "Menu_Command");
	DelEventHandler("Menu_NewGame", "Menu_NewGame");
	SendMessage(&GameInterface, "l", MSG_INTERFACE_RELEASE);
	DeleteClass(&GameInterface);
	screenName = "";
	// the movie of the new game, then the hero starts in the town of his address (cutscene.c Cut_End)
	Cut_Start("intro", "town");
}
