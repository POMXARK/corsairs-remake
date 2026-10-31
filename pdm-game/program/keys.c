// the rebinding of the keys on the page "Управление" (ours: the original shows its own keys and does not rebind them
// in the data we have). The overrides are in PdmKeys.<control> = <Windows key code>, run.sh / run.ps1 put them in
// data/start.c (Keys_Init) from the lines key_<control> = <code> of save/settings.ini; a new key works from the next
// launch of the game, as the scenes map their keys once.
object PdmKeys;

#define KEYS_COUNT 23
string keysName[KEYS_COUNT] = {"Ship_TurnLeft", "Ship_TurnRight", "Ship_SailUp", "Ship_SailDown", "Battle_Fire",
	"Battle_Charge0", "Battle_Charge1", "Battle_Charge2", "Battle_Charge3", "Screen_Status", "Save_Quick", "Save_Load",
	"ChrForward", "ChrBackward", "ChrRun", "Town_Talk", "ChrTurnHL", "ChrTurnHR", "Hud_Menu", "Hud_Confirm",
	"Hud_Left", "Hud_Right", "Hud_Corner"};
int keysDefault[KEYS_COUNT] = {65, 68, 87, 83, 70, 49, 50, 51, 52, 112, 114, 118, 87, 83, 16, 69, 65, 68, 9, 13, 37, 39, 187};
// the number "key" of the line in [KeyControls] of INI/menu.ini that the row stands for
int keysRow[KEYS_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 20, 22, 23, 24, 25, 26, 27, 38, 39, 12, 13, 42, 43, 19};

int keysCapture = -1;
bool keysCapReady = false;

int Keys_Code(string name, int def)
{
	if (CheckAttribute(&PdmKeys, name)) { return sti(PdmKeys.(name)); }
	return def;
}

// the code of a control of the table: the key of the player, else the default
int Keys_Of(string name)
{
	for (int i = 0; i < KEYS_COUNT; i++)
	{
		if (keysName[i] == name) { return Keys_Code(name, keysDefault[i]); }
	}
	return 0;
}

int Keys_Find(int row)
{
	for (int i = 0; i < KEYS_COUNT; i++)
	{
		if (keysRow[i] == row) { return i; }
	}
	return -1;
}

string Keys_VkName(int vk)
{
	if (vk >= 48 && vk <= 57) { return "" + (vk - 48); }
	if (vk >= 65 && vk <= 90) { return strcut("ABCDEFGHIJKLMNOPQRSTUVWXYZ", vk - 65, vk - 65); }
	if (vk >= 112 && vk <= 123) { return "F" + (vk - 111); }
	if (vk == 8) { return "Backspace"; }
	if (vk == 9) { return "Tab"; }
	if (vk == 13) { return "Enter"; }
	if (vk == 16) { return "Shift"; }
	if (vk == 17) { return "Ctrl"; }
	if (vk == 18) { return "Alt"; }
	if (vk == 32) { return "Space"; }
	if (vk == 33) { return "PgUp"; }
	if (vk == 34) { return "PgDn"; }
	if (vk == 35) { return "End"; }
	if (vk == 36) { return "Home"; }
	if (vk == 37) { return "Left"; }
	if (vk == 38) { return "Up"; }
	if (vk == 39) { return "Right"; }
	if (vk == 40) { return "Down"; }
	if (vk == 45) { return "Insert"; }
	if (vk == 46) { return "Delete"; }
	return "#" + vk;
}

// the lines of the overrides for save/settings.ini
string Keys_Lines()
{
	string out = "";
	for (int i = 0; i < KEYS_COUNT; i++)
	{
		string nm = keysName[i];
		if (CheckAttribute(&PdmKeys, nm)) { out = out + "key_" + nm + " = " + sti(PdmKeys.(nm)) + "\n"; }
	}
	return out;
}

// the controls of every key that wait for the press of the new one; the mouse is not offered
void Keys_CaptureMake()
{
	if (keysCapReady) { return; }
	keysCapReady = true;
	for (int vk = 8; vk < 223; vk++)
	{
		// Escape cancels; the locks (Caps 20, Num 144, Scroll 145) report their state, not a press
		if (vk == 27 || vk == 20 || vk == 144 || vk == 145) { continue; }
		MapKey("Pdm_Cap" + vk, vk);
	}
}

void Keys_Begin(int i)
{
	Keys_CaptureMake();
	keysCapture = i;
	Trace("PDM keys: waiting for the key of " + keysName[i]);
}

// the press that the page waits for; true if it was taken (Escape cancels)
bool Keys_Control(string control)
{
	if (keysCapture < 0) { return false; }
	int i = keysCapture;
	if (control == "Pdm_Quit")
	{
		keysCapture = -1;
		Trace("PDM keys: cancelled");
		Screen_Controls();
		return true;
	}
	if (findSubStr(control, "Pdm_Cap", 0) != 0) { return false; }
	int vk = sti(strcut(control, 7, strlen(control) - 1));
	keysCapture = -1;
	string nm = keysName[i];
	PdmKeys.(nm) = vk;
	Options_SaveSettings();
	Trace("PDM keys: " + keysName[i] + " is " + Keys_VkName(vk) + " (" + vk + ")");
	Screen_Controls();
	return true;
}

// the button "Сбросить": every control gets its own key again
void Keys_Reset()
{
	keysCapture = -1;
	for (int i = 0; i < KEYS_COUNT; i++)
	{
		string nm = keysName[i];
		DeleteAttribute(&PdmKeys, nm);
	}
	Options_SaveSettings();
	Trace("PDM keys: reset");
	Screen_Controls();
}
