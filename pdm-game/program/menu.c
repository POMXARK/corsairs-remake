// The main menu of the original (MENU.dll): the screen is [MainMenu] of INI/menu.ini converted by
// tools/pdm_ui.py into resource\ini\interfaces\mainmenu.ini. "Новая Игра" starts the game in the town of the hero,
// "Выход" quits; "Настройки", "Загрузить" and "Авторы" open their pages (screens.c), what they do comes
// with the later stages (P9).
// SCENE=menu-newgame presses "Новая Игра" by itself after a while (the test without key presses).

#define MSG_INTERFACE_INIT 45010
#define MSG_INTERFACE_RELEASE 45011
#define MSG_INTERFACE_SET_SELECTABLE 45024
#define MSG_INTERFACE_MSG_TO_NODE 45045
#define MSG_INTERFACE_MENU_ACTION 45062
#define MSG_INTERFACE_GET_CURRENT_NODE 45028
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
	if (StartScene == "menu" && TownAuto == MENUARROWS_ID) { Menu_ArrowsStart(); }
}

// The test of the arrows (autotests.md, "menu-arrows"): "Сохранить" and "Продолжить" are not selectable
// without a game, and the arrows have to step over them, as in the original. Every step presses one
// command like the key does (MSG_INTERFACE_MENU_ACTION) and reads the current node back.
// the node expected after the step N (step 0 selects the first one); steps 1-4 press "down", 5-8 "up"
string Menu_ArrowsNode(int step)
{
	if (step == 0 || step == 8) { return "LB_NEWGAME"; }
	if (step == 1 || step == 7) { return "LB_LOADGAME"; }
	if (step == 2 || step == 6) { return "LB_OPTIONS"; }
	if (step == 3 || step == 5) { return "LB_CREDITS"; }
	return "LB_EXIT";
}
int menuArrowsStep = 0;
bool menuArrowsFail = false;

void Menu_ArrowsStart()
{
	SetEventHandler("Menu_ArrowsStep", "Menu_ArrowsStep", 0);
	PostEvent("Menu_ArrowsStep", 1000);
}

void Menu_ArrowsStep()
{
	string current = "";
	// step 0 only reads where the menu starts ("activate" would press the button)
	if (menuArrowsStep > 0)
	{
		string command = "downstep";
		if (menuArrowsStep > 4) { command = "upstep"; }
		SendMessage(&GameInterface, "lss", MSG_INTERFACE_MENU_ACTION, command, "");
	}
	SendMessage(&GameInterface, "le", MSG_INTERFACE_GET_CURRENT_NODE, &current);
	string expected = Menu_ArrowsNode(menuArrowsStep);
	Trace("PDM menu: arrows step " + menuArrowsStep + ", at " + current + ", expected " + expected);
	if (current != expected) { menuArrowsFail = true; }
	menuArrowsStep++;
	if (menuArrowsStep < 9) { PostEvent("Menu_ArrowsStep", 500); return; }
	if (menuArrowsFail) { Trace("PDM menu: arrows FAIL"); } else { Trace("PDM menu: arrows ok"); }
	Trace("PDM menu: autotest done, arrows");
	ExitProgram();
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
