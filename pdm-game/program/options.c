// The page "Настройки" ([Options] of MENU.dll, screens.c opens it): the resolution and the full screen, the sound
// and the music. A click on the resolution goes to the next one, "Применить" gives the window the chosen one at
// once (Render.SetScreen of the engine, which keeps it in engine.ini for the next launch) and opens the page again
// in the new window. The checks of the original show their state: the tick of check-nor.tga on, the cross of
// check-hi.tga off (<NODE>_OFF of tools/pdm_ui.py over the button). What the game has not got yet (the mouse
// inverted, the antialiasing, the simple textures, the gamma, the difficulty) is shown off and cannot be chosen.

#define MSG_INTERFACE_SET_NODE_USING 45016
// the sizes the resolution goes through; the current one is put among them if it is not one of them (ours)
#define OPTIONS_SIZES "1280x720,1366x768,1600x900,1920x1080,2560x1440"
#define OPTIONS_REOPEN_MS 200

// the choice of the page until "Применить"
string optionsSize = "";
bool optionsFull = false;
// the page opened again after "Применить" keeps the choice, opened from the menu it shows the window
bool optionsKeep = false;
// the sound and the music of the session, their volume in percent and the neural voices of the characters
// (docs/voice-over.md): the volumes begin as the game played them before the page had sliders
bool optionsFx = true;
bool optionsMusic = true;
bool optionsVoice = true;
int optionsVolFx = 80;
int optionsVolMusic = 70;
int optionsVolVoice = 100;
#define OPTIONS_VOLUME_STEP 10
// the save when the ship leaves a town (save.c)
bool optionsAutosave = true;

void Options_Init()
{
	// the volume the launch asks for (VOLUME_FX ... or settings.ini, run.sh)
	optionsVolFx = StartVolFx;
	optionsVolMusic = StartVolMusic;
	optionsVolVoice = StartVolVoice;
	optionsVoice = StartNpcVoice != 0;
	SetEventHandler("Options_Reopen", "Options_Reopen", 0);
}

string Options_Current()
{
	return Render.screen_x + "x" + Render.screen_y;
}

// the size after <size> in OPTIONS_SIZES, the first one after the last
string Options_Next(string size)
{
	string list = OPTIONS_SIZES + ",";
	int at = findSubStr(list, size + ",", 0);
	if (at < 0) { at = -1; } else { at = at + strlen(size); }
	if (at + 1 >= strlen(list)) { at = -1; }
	int end = findSubStr(list, ",", at + 1);
	return strcut(list, at + 1, end - 1);
}

int Options_Width(string size)
{
	return sti(strcut(size, 0, findSubStr(size, "x", 0) - 1));
}

int Options_Height(string size)
{
	return sti(strcut(size, findSubStr(size, "x", 0) + 1, strlen(size) - 1));
}

void Options_Check(string node, bool on)
{
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_NODE_USING, node + "_OFF", !on);
}

void Options_Off(string node)
{
	Options_Check(node, false);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, node, false);
}

void Options_Fill()
{
	if (!optionsKeep)
	{
		optionsSize = Options_Current();
		optionsFull = sti(Render.full_screen) != 0;
	}
	optionsKeep = false;
	Screen_Text("LB_RESOLUTION", optionsSize);
	Screen_Text("LB_DEVICES", "Direct3D 9");
	Screen_Text("LB_LANGUAGES", "Обычная");
	Screen_Text("EDITGAMMA", "1.0");
	Options_Check("LB_WINDOWED", optionsFull);
	Options_Check("LB_SOUNDON", optionsFx);
	Options_Check("LB_MUSICON", optionsMusic);
	Options_Check("LB_VOICEON", optionsVoice);
	Options_Check("LB_AUTOSAVE", optionsAutosave);
	Options_Volumes();
	Options_Off("LB_SWAPMOUSEX");
	Options_Off("LB_SWAPMOUSEY");
	Options_Off("LB_ALIASING");
	Options_Off("LB_TEXTURELOW");
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_SOUNDPOS", false);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_MUSICPOS", false);
	SendMessage(&GameInterface, "lsl", MSG_INTERFACE_SET_SELECTABLE, "LB_GAMMA", false);
}

int Options_Step(int volume, int step)
{
	int v = volume + step;
	if (v < 0) { v = 0; }
	if (v > 100) { v = 100; }
	return v;
}

void Options_Volumes()
{
	for (int i = 0; i < 3; i++)
	{
		string row = "";
		if (i == 0) { row = "FX"; }
		if (i == 1) { row = "MUSIC"; }
		if (i == 2) { row = "VOICE"; }
		Screen_Text("LB_" + row + "DOWN", "(-)");
		Screen_Text("LB_" + row + "UP", "(+)");
	}
	Screen_Text("LB_FXVAL", optionsVolFx + "%");
	Screen_Text("LB_MUSICVAL", optionsVolMusic + "%");
	Screen_Text("LB_VOICEVAL", optionsVolVoice + "%");
}

// - and + of a row of the volume (pdm_ui.py options_volume); true if the click was one of them
bool Options_Slider(string node)
{
	int step = 0;
	if (findSubStr(node, "DOWN", 0) > 0) { step = 0 - OPTIONS_VOLUME_STEP; }
	if (findSubStr(node, "UP", 0) > 0) { step = OPTIONS_VOLUME_STEP; }
	if (step == 0) { return false; }
	bool known = true;
	if (node == "LB_FXDOWN" || node == "LB_FXUP") { optionsVolFx = Options_Step(optionsVolFx, step); }
	else
	{
		if (node == "LB_MUSICDOWN" || node == "LB_MUSICUP") { optionsVolMusic = Options_Step(optionsVolMusic, step); }
		else
		{
			if (node == "LB_VOICEDOWN" || node == "LB_VOICEUP") { optionsVolVoice = Options_Step(optionsVolVoice, step); }
			else { known = false; }
		}
	}
	if (!known) { return false; }
	Options_Volumes();
	Sound_Volume();
	return true;
}

// a click on the page; true if it was one of its own
bool Options_Click(string node)
{
	if (node == "LB_RESOLUTION") { optionsSize = Options_Next(optionsSize); Screen_Text(node, optionsSize); return true; }
	if (node == "LB_WINDOWED") { optionsFull = !optionsFull; Options_Check(node, optionsFull); return true; }
	if (node == "LB_SOUNDON") { optionsFx = !optionsFx; Options_Check(node, optionsFx); Sound_Volume(); return true; }
	if (node == "LB_MUSICON") { optionsMusic = !optionsMusic; Options_Check(node, optionsMusic); Sound_Volume(); return true; }
	if (node == "LB_VOICEON") { optionsVoice = !optionsVoice; Options_Check(node, optionsVoice); return true; }
	if (Options_Slider(node)) { return true; }
	if (node == "LB_AUTOSAVE") { optionsAutosave = !optionsAutosave; Options_Check(node, optionsAutosave); return true; }
	if (node == "LB_APPLY") { Options_Apply(); return true; }
	return false;
}

void Options_Apply()
{
	bool now = sti(Render.full_screen) != 0;
	if (optionsSize == Options_Current() && optionsFull == now) { return; }
	Trace("PDM options: the screen " + optionsSize + ", full screen " + optionsFull);
	Render.SetScreen.x = Options_Width(optionsSize);
	Render.SetScreen.y = Options_Height(optionsSize);
	int full = 0;
	if (optionsFull) { full = 1; }
	Render.SetScreen.full_screen = full;
	Render.restart = 0;
	// the render takes it at the start of the next frame; the page is laid out again for the new window
	PostEvent("Options_Reopen", OPTIONS_REOPEN_MS);
}

void Options_Reopen()
{
	Trace("PDM options: the window is " + Options_Current() + ", full screen " + Render.full_screen);
	if (screenName != "options") { return; }
	optionsKeep = true;
	Screen_Show("options");
	// the device could not take the window (native Direct3D 9 keeps resources of the scene): engine.ini has the
	// screen, the next launch opens it
	if (CheckAttribute(&Render, "restart") && sti(Render.restart) != 0) { Screen_Text("LB_RESOLUTION", optionsSize + " (после перезапуска)"); }
}
