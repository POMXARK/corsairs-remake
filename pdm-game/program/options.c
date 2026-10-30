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

// the volumes and the voices of the characters to save/settings.ini (run.sh / run.ps1 read it next launch,
// after the variables of the shell, before settings.ini)
void Options_SaveSettings()
{
	int voice = 0;
	if (optionsVoice) { voice = 1; }
	WriteTextFile("save/settings.ini", "volume_fx = " + optionsVolFx + "\nvolume_music = " + optionsVolMusic + "\nvolume_voice = " + optionsVolVoice + "\nnpc_voice = " + voice + "\n");
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
	Options_SaveSettings();
	return true;
}

// a click on the page; true if it was one of its own
bool Options_Click(string node)
{
	if (node == "LB_RESOLUTION") { optionsSize = Options_Next(optionsSize); Screen_Text(node, optionsSize); return true; }
	if (node == "LB_WINDOWED") { optionsFull = !optionsFull; Options_Check(node, optionsFull); return true; }
	if (node == "LB_SOUNDON") { optionsFx = !optionsFx; Options_Check(node, optionsFx); Sound_Volume(); return true; }
	if (node == "LB_MUSICON") { optionsMusic = !optionsMusic; Options_Check(node, optionsMusic); Sound_Volume(); return true; }
	if (node == "LB_VOICEON") { optionsVoice = !optionsVoice; Options_Check(node, optionsVoice); Options_SaveSettings(); return true; }
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

// ---------- TOWN_AUTO=14 with SCENE=sea: the resolution of the page over the game ----------
// The same click "Применить" makes, without a mouse: it asks the render for the new window (Render.SetScreen
// of DX9RENDER::RunStart, which resizes the window and the back buffer and keeps it in engine.ini) and then
// asks the interface what its window is. The render answers with the new size (Render.screen_x of
// DX9RENDER::ResizeBackBuffer), the interface with the one it had at the launch: XINTERFACE::LoadIni reads
// the window and builds the matrices matp, matv and the attributes ScreenWidth, ScreenLeft, ScreenTop once,
// in XINTERFACE::SetDevice from XINTERFACE::Init, and nothing runs it again after the resize. So the traces
// of every resize show the window changed and the interface not, which is why the menus and the panels of
// the interface keep to the old size of the window (docs findings in docs/dynamic-resolution.md).

// the window of the interface in the units of its screens, as the engine set it once
int optionsAutoStep = 0;
int optionsAutoInterface = 0;
#define OPTIONS_AUTO_STEP_MS 900

int Opt_AutoWidth()
{
	int w = 0;
	if (CheckAttribute(&GameInterface, "ScreenWidth")) { w = sti(GameInterface.ScreenWidth); }
	return w;
}

// DX9RENDER::SetScreen sets it when the device could not take the window: engine.ini holds the size for the next launch
int Opt_AutoRestart()
{
	if (CheckAttribute(&Render, "restart")) { return sti(Render.restart); }
	return 0;
}

void Opt_AutoStart()
{
	// the handler has to exist before the first PostEvent of the step (as save.c does for its steps)
	SetEventHandler("Opt_AutoStep", "Opt_AutoStep", 0);
	Trace("PDM options: autotest, the window " + Options_Current() + ", the interface of " + Opt_AutoWidth() + ", restart " + Opt_AutoRestart());
	optionsAutoInterface = Opt_AutoWidth();
	PostEvent("Opt_AutoStep", OPTIONS_AUTO_STEP_MS);
}

// the click of the page as the mouse sends it (the same message screens.c gets on a click)
void Opt_AutoClick(string node)
{
	Trace("PDM options: autotest, " + screenName + " " + node);
	PostEvent("ievnt_command", 0, "ss", "click", node);
}

// the next size of OPTIONS_SIZES, always another than the window now
void Opt_AutoApply()
{
	optionsKeep = false;
	optionsSize = Options_Next(Options_Current());
	Opt_AutoClick("LB_APPLY");
}

// steps 3 and 5 look at the window the render has and the window the interface was laid out for
void Opt_AutoStep()
{
	int step = optionsAutoStep;
	optionsAutoStep++;
	if (step == 3 || step == 5)
	{
		Trace("PDM options: autotest, the window " + Options_Current() + ", the interface of " + Opt_AutoWidth() + ", restart " + Opt_AutoRestart());
	}
	if (step < 5) { PostEvent("Opt_AutoStep", OPTIONS_AUTO_STEP_MS); }
	if (step == 0) { Screen_GameMenu(); return; }
	if (step == 1) { Opt_AutoClick("LB_OPTIONS"); return; }
	// the volumes of the page are saved on every click (save/settings.ini, read by the next launch)
	if (step == 2) { Opt_AutoClick("LB_FXDOWN"); Opt_AutoClick("LB_VOICEDOWN"); Trace("PDM options: autotest, volumes " + optionsVolFx + " " + optionsVolMusic + " " + optionsVolVoice); }
	if (step == 2 || step == 4) { Opt_AutoApply(); return; }
	Trace("PDM options: autotest done, the interface of " + optionsAutoInterface + " units stayed while the window moved to " + Options_Current());
	ExitProgram();
}

// ---------- TOWN_AUTO=15 with SCENE=sea: the page is CLOSED after the resolution change ----------
// What the player does in a live game: the world renders under the page, the resolution changes, "Выход"
// closes the page (Screen_Click of screens.c makes Screen_Go and Screen_Close, which thaws EXECUTE) and the
// world must keep drawing in the new window. The frames after the close are the evidence of what the scene
// still shows once the device has changed its back buffer (docs/dynamic-resolution.md).

int closeAutoStep = 0;
#define CLOSE_AUTO_STEP_MS 900

void Opt_CloseStart()
{
	// the handler has to exist before the first PostEvent of the step (as save.c does for its steps)
	SetEventHandler("Opt_CloseStep", "Opt_CloseStep", 0);
	Trace("PDM close: autotest, the window " + Options_Current());
	PostEvent("Opt_CloseStep", CLOSE_AUTO_STEP_MS);
}

// the click of the page as the mouse sends it (the same message screens.c gets on a click)
void Opt_CloseClick(string node)
{
	Trace("PDM close: autotest, " + screenName + " " + node);
	PostEvent("ievnt_command", 0, "ss", "click", node);
}

// steps 5..8 render the world with the page closed, so the frames of the run are the frames of the scene
void Opt_CloseStep()
{
	int step = closeAutoStep;
	closeAutoStep++;
	if (step == 5 || step == 8 || step == 12)
	{
		Trace("PDM close: autotest, the window " + Options_Current() + ", the page of " + screenName);
	}
	if (step < 12) { PostEvent("Opt_CloseStep", CLOSE_AUTO_STEP_MS); } // steps 9..12 keep the world rendering alone
	if (step == 0) { Screen_GameMenu(); return; }
	if (step == 1) { Opt_CloseClick("LB_OPTIONS"); return; }
	if (step == 2) { Opt_AutoApply(); return; }
	if (step == 3) { Opt_CloseClick("LB_EXIT"); return; } // Screen_Go closes the page over the live scene
	// steps 4..11 do nothing but keep the frames of the world rendering with the page closed
	if (step >= 12)
	{
		Trace("PDM close: autotest done, the world renders in the window of " + Options_Current() + " with the page closed");
		ExitProgram();
	}
}
