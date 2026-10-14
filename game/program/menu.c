// Main menu: maps the interface controls, creates XINTERFACE and loads mainmenu.ini.
// Buttons report to compile.log, "Выход" (or Escape) quits.

#define MSG_INTERFACE_INIT 45010
#define INTERFACE_EXECUTE 4
#define INTERFACE_REALIZE 5
#define INVERSE_CONTROL 4

object GameInterface;

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

	CreateEntity(&GameInterface, "xinterface");
	LayerAddObject(INTERFACE_EXECUTE, &GameInterface, -100);
	LayerAddObject(INTERFACE_REALIZE, &GameInterface, -100);

	SetEventHandler("ievnt_command", "Menu_Command", 0);
	SetEventHandler("exitCancel", "Menu_Quit", 0);
	SendMessage(&GameInterface, "ls", MSG_INTERFACE_INIT, "resource\ini\interfaces\mainmenu.ini");
	Trace("MENU: loaded");
}

void Menu_Command()
{
	string command = GetEventData();
	string node = GetEventData();
	if (command == "click" || command == "activate")
	{
		Trace("MENU: " + node);
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

void Menu_Quit()
{
	Trace("MENU: quit");
	ExitProgram();
}
