// The towns and interiors of the original: what the town modules of the original do with
// WORLDS/locations/*.loc. tools/pdm_world.py converts the locations into data\pdm_world.c
// (PdmLocations.<loc>: model, patch, points) and their models, patches and characters.
//
// The hero walks on the patch of the location (W/S, A/D, the mouse, Shift walks). The points of the
// .loc: 1 an exit (its box is the door, its link where it leads: sea, street or an interior slot of
// the town), 4 where the hero appears coming from the location of its link, the others are the
// places of the characters: a character stands on a point of the class of his model
// (anim_types.idf). Who is in the location: the cards of PdmCharacters whose address is the island
// of the town and the kind of the location (2 street, 3 tavern, 4 store, 5 shipyard, 6 townhall,
// 8 the town guard), or whom the story put there (Pdm_SetLocation, "<island>.<kind>").
//
// E talks to the nearest character who has a dialog (card.dialog_key, see Town_Talk below).

#define MSG_LOCATION_ADD_MODEL 30100
#define MSG_LOCATION_SET_CHRS_PATCH 30120
#define MSG_LOCATION_MODELSPATH 30140
#define MSG_LOCATION_TEXTURESPATH 30141
#define MSG_CHARACTER_SETMODEL 30200
#define MSG_CHARACTER_GETPOS 30202
#define MSG_CHARACTER_TELEPORT_AY 30211
#define MSG_NPCHARACTER_SETTASK 30400
#define MSG_CAMERA_SETTARGET 30500
#define MSG_CAMERA_FOLLOW 30510

#define TOWN_MAX_NPC 32
#define TOWN_TICK_MS 200

object TownLocation;
object TownWeather;
object TownGroups;
object TownHero;
object TownCamera;
object TownTaken;
object TownNpc[TOWN_MAX_NPC];
int townNpcCount = 0;
bool townLoaded = false;
// the town of the island and the location the hero is in
string townIsland = "";
string townStreet = "";
string townHere = "";
// the exit box the hero stands in: he leaves through an exit only after stepping into it
int townInExit = -1;
int townShadow[2];
// TOWN_AUTO=1 (run.sh): the hero walks by himself into the tavern and out again, for the tests;
// TOWN_AUTO=2 also talks to the first character of the tavern who has a dialog, always taking the
// first answer that is on
int townAutoStep = 0;
bool townAutoTalked = false;
int townAutoNpc = -1;

#define TOWN_TALK_DIST 3.0
object TownDialog;
// the NPC talked to (-1: no dialog), his dialog and its node on the screen
int townTalkNpc = -1;
string townTalkKey = "";
string townTalkNode = "";
// the dialog entity takes choosing the same "go" twice in a row for a broken tree: the go of an
// answer is its link with the parity of the step before it
int townTalkStep = 0;

// the island whose town is the location (avilia for City_GrandaAvilia)
string Town_IslandOf(string town)
{
	int n = GetAttributesNum(&PdmIslands);
	aref island;
	for (int i = 0; i < n; i++)
	{
		island = GetAttributeN(&PdmIslands, i);
		if (island.town == town) { return GetAttributeName(island); }
	}
	return "";
}

// the kind of a location in the address codes of the characters
string Town_Kind(string loc)
{
	if (loc == townStreet) { return "street"; }
	aref interiors;
	makearef(interiors, PdmLocations.(townStreet).interiors);
	int n = GetAttributesNum(interiors);
	aref slot;
	for (int i = 0; i < n; i++)
	{
		slot = GetAttributeN(interiors, i);
		if (GetAttributeValue(slot) == loc) { return GetAttributeName(slot); }
	}
	return "";
}

bool Town_AddressIs(aref card, string kind)
{
	string code = "";
	if (CheckAttribute(card, "address.location")) { code = card.address.location; }
	if (kind == "street") { return code == "2" || code == "8"; }
	if (kind == "tavern") { return code == "3"; }
	if (kind == "store") { return code == "4"; }
	if (kind == "shipyard") { return code == "5"; }
	if (kind == "townhall") { return code == "6"; }
	return false;
}

// "<island>.<kind>" of the story: the island by its key or its name, as the story writes them
// ("Gray Sails" for Gray_Sails, "d'Orange" for d_Orange, "tendales")
bool Town_StoryPlaceIs(string place, string kind)
{
	place = Town_Norm(place);
	string island = PdmIslands.(townIsland).class;
	if (place == Town_Norm(island + "." + kind)) { return true; }
	return place == Town_Norm(townIsland + "." + kind);
}

void Town_Start(string loc, string from)
{
	townStreet = loc;
	townIsland = Town_IslandOf(loc);
	Trace("PDM town: " + loc + " of the island " + townIsland);
	// the music of the towns of the nation of the island
	if (townIsland != "") { Sound_TownMusic(sti(PdmIslands.(townIsland).nation)); }
	SetEventHandler("EWhr_GetShadowDensity", "Town_ShadowDensity", 0);
	SetEventHandler("EWhr_GetFogDensity", "Town_FogDensity", 0);
	SetEventHandler("Town_Tick", "Town_Tick", 0);
	SetEventHandler("Town_AutoGo", "Town_AutoGo", 0);
	SetEventHandler("Town_AutoWhere", "Town_AutoWhere", 0);
	SetEventHandler("Town_AutoQuit", "Town_AutoQuit", 0);
	SetEventHandler("Town_AutoTalk", "Town_AutoTalk", 0);
	SetEventHandler("Town_AutoPick", "Town_AutoPick", 0);
	SetEventHandler("Control Activation", "Town_Control", 0);
	SetEventHandler("DialogEvent", "Town_DialogEvent", 0);
	SetEventHandler("DialogCancel", "Town_DialogLeave", 0);
	SetEventHandler("EmergencyDialogExit", "Town_DialogLeave", 0);
	SetEventHandler("Town_DialogClose", "Town_DialogClose", 0);
	Town_Load(loc, from);
	PostEvent("Town_Tick", TOWN_TICK_MS);
}

void Town_MapKeys()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	MapKey("ChrForward", 87);
	MapKey("ChrBackward", 83);
	MapKey("ChrTurnHL", 65);
	MapKey("ChrTurnHR", 68);
	MapKey("ChrRun", 16);
	MapKey("ChrTurnH", 256);
	MapKey("ChrCamTurnV", 257);
	MapKey("Town_Talk", 69);
	// polled by the dialog entity while it is open: arrows pick an answer, Space, Enter or the left
	// button say it, PageUp/PageDown page a long speech, Escape leaves
	MapKey("DlgUp", 38);
	MapKey("DlgDown", 40);
	MapKey("DlgAction", 32);
	MapKey("DlgAction1", 1);
	MapKey("DlgAction2", 13);
	MapKey("DlgScrollUp", 33);
	MapKey("DlgScrollDown", 34);
	MapKey("DlgCancel", 27);
}

void Town_Load(string loc, string from)
{
	aref data;
	makearef(data, PdmLocations.(loc));
	townHere = loc;
	Town_MapKeys();

	CreateEntity(&TownWeather, "weather");
	TownWeather.Fog.Enable = 1;
	TownWeather.Fog.Density = 0.004;
	TownWeather.Fog.Color = argb(0, 150, 180, 210);
	TownWeather.Sun.Color = argb(0, 255, 240, 215);
	TownWeather.Sun.Ambient = argb(0, 120, 120, 130);
	TownWeather.Sun.HeightAngle = 0.9;
	TownWeather.Sun.AzimuthAngle = 2.5;
	TownWeather.isDone = "";
	Render.BackColor = argb(255, 150, 180, 210);
	if (data.sound != "town" && data.sound != "deadtown")
	{
		// the interiors are lit inside and have no sky behind their walls
		TownWeather.Sun.Ambient = argb(0, 150, 140, 125);
		Render.BackColor = argb(255, 0, 0, 0);
	}

	TownLocation.id = loc;
	CreateEntity(&TownLocation, "location");
	SendMessage(&TownLocation, "ls", MSG_LOCATION_MODELSPATH, "locations");
	SendMessage(&TownLocation, "ls", MSG_LOCATION_TEXTURESPATH, "locations");
	if (!SendMessage(&TownLocation, "lssl", MSG_LOCATION_ADD_MODEL, data.model, "DLightModel", 10))
	{
		Trace("PDM town: model " + data.model + " not loaded");
	}
	if (!SendMessage(&TownLocation, "ls", MSG_LOCATION_SET_CHRS_PATCH, data.patch))
	{
		Trace("PDM town: patch " + data.patch + " not loaded");
	}
	CreateEntity(&TownGroups, "CharactersGroups");

	// the hero appears on the arrival point of the location he comes from, or on the first one
	int arrive = Town_FindPoint(data, 4, from);
	if (arrive < 0) { arrive = Town_FindPoint(data, 4, ""); }
	TownHero.id = "hero";
	if (TownAuto) { CreateEntity(&TownHero, "NPCharacter"); }
	else { CreateEntity(&TownHero, "player"); }
	Town_SetModel(&TownHero, "hero");
	Town_Teleport(&TownHero, data, arrive);
	townInExit = Town_ExitAt(data, &TownHero);

	CreateEntity(&TownCamera, "locationcamera");
	SendMessage(&TownCamera, "li", MSG_CAMERA_SETTARGET, &TownHero);
	SendMessage(&TownCamera, "l", MSG_CAMERA_FOLLOW);
	SendMessage(&Scene, "si", "SetActiveCamera", &TownCamera);

	Town_PlaceCharacters(data);
	// the voices of many when the location is full of people
	Sound_Location(data.sound, townNpcCount > 2);
	townLoaded = true;
	if (TownAuto) { PostEvent("Town_AutoGo", 3000); }
	Trace("PDM town: in " + loc + " from " + from + ", " + townNpcCount + " characters");
}

void Town_Release()
{
	Town_DialogClose();
	for (int i = 0; i < townNpcCount; i++) { DeleteClass(&TownNpc[i]); }
	townNpcCount = 0;
	DeleteClass(&TownCamera);
	DeleteClass(&TownHero);
	DeleteClass(&TownGroups);
	DeleteClass(&TownLocation);
	DeleteClass(&TownWeather);
	townLoaded = false;
}

// the first point of the type (with the link, if one is given); "type" is a word of the script
int Town_FindPoint(aref data, int pointType, string link)
{
	int n = sti(data.points);
	string at;
	string pointLink;
	for (int i = 0; i < n; i++)
	{
		at = "p" + i;
		if (sti(data.(at).type) != pointType) { continue; }
		pointLink = data.(at).link;
		if (link == "" || pointLink == link) { return i; }
	}
	return -1;
}

void Town_Teleport(ref chr, aref data, int point)
{
	if (point < 0) { return; }
	string at = "p" + point;
	SendMessage(chr, "lffff", MSG_CHARACTER_TELEPORT_AY, stf(data.(at).x), stf(data.(at).y), stf(data.(at).z), stf(data.(at).ay));
}

// models\characters\<model>.gm with animation\<model>.ani; the idle actions are idle_1..4 of the
// converted .ani, read again when "actions" changes
void Town_SetModel(ref chr, string model)
{
	if (!SendMessage(chr, "lss", MSG_CHARACTER_SETMODEL, model, model))
	{
		Trace("PDM town: model " + model + " not loaded");
	}
	chr.actions.idle.i1 = "idle_1";
	chr.actions.idle.i2 = "idle_2";
	chr.actions.idle.i3 = "idle_3";
	chr.actions.idle.i4 = "idle_4";
	chr.actions = "";
}

void Town_PlaceCharacters(aref data)
{
	string kind = Town_Kind(townHere);
	int n = GetAttributesNum(&PdmCharacters);
	int points = sti(data.points);
	// a point takes one character
	DeleteAttribute(&TownTaken, "");
	aref card;
	string model, at, place;
	int cls, i, p;
	bool here;
	for (i = 0; i < n && townNpcCount < TOWN_MAX_NPC; i++)
	{
		card = GetAttributeN(&PdmCharacters, i);
		if (GetAttributeName(card) == "Nicolas_Sharp") { continue; }
		if (CheckAttribute(card, "location"))
		{
			place = card.location;
			here = Town_StoryPlaceIs(place, kind);
		}
		else
		{
			here = CheckAttribute(card, "address.island") && card.address.island == townIsland && Town_AddressIs(card, kind);
		}
		if (!here) { continue; }
		// CHARACTERS\citizen1.cff -> citizen1
		model = strcut(card.model, 11, strlen(card.model) - 5);
		model = Town_Lower(model);
		if (!CheckAttribute(&PdmCharModels, model) || PdmCharModels.(model).model == "")
		{
			Trace("PDM town: no model " + model + " for " + card.id);
			continue;
		}
		cls = sti(PdmCharModels.(model).class);
		for (p = 0; p < points; p++)
		{
			at = "p" + p;
			if (sti(data.(at).type) == cls && !CheckAttribute(&TownTaken, at)) { break; }
		}
		if (p >= points)
		{
			Trace("PDM town: no free point of type " + cls + " for " + card.id);
			continue;
		}
		TownTaken.(at) = 1;
		TownNpc[townNpcCount].id = GetAttributeName(card);
		CreateEntity(&TownNpc[townNpcCount], "NPCharacter");
		Town_SetModel(&TownNpc[townNpcCount], model);
		Town_Teleport(&TownNpc[townNpcCount], data, p);
		Trace("PDM town: " + card.id + " (" + model + ") on point " + p + " of type " + cls);
		townNpcCount++;
	}
}

// the script has no tolower, and the models are named in either case
string Town_Lower(string s)
{
	string up = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
	string low = "abcdefghijklmnopqrstuvwxyz";
	string out = "";
	string c;
	int k;
	for (int i = 0; i < strlen(s); i++)
	{
		c = GetSymbol(s, i);
		k = findSubStr(up, c, 0);
		if (k >= 0) { c = GetSymbol(low, k); }
		out = out + c;
	}
	return out;
}

// an island as the story writes it: lower case, "_" and "'" as spaces
string Town_Norm(string s)
{
	s = Town_Lower(s);
	string out = "";
	string c;
	for (int i = 0; i < strlen(s); i++)
	{
		c = GetSymbol(s, i);
		if (c == "_" || c == "'") { c = " "; }
		out = out + c;
	}
	return out;
}

// the exit point whose box the character stands in, -1 if none
int Town_ExitAt(aref data, ref chr)
{
	float x, y, z;
	SendMessage(chr, "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	int n = sti(data.points);
	string at;
	for (int i = 0; i < n; i++)
	{
		at = "p" + i;
		if (sti(data.(at).type) != 1) { continue; }
		if (x >= stf(data.(at).bx0) && x <= stf(data.(at).bx1) && z >= stf(data.(at).bz0) && z <= stf(data.(at).bz1))
		{
			return i;
		}
	}
	return -1;
}

void Town_Tick()
{
	if (!townLoaded) { return; }
	PostEvent("Town_Tick", TOWN_TICK_MS);
	aref data;
	makearef(data, PdmLocations.(townHere));
	int exit = Town_ExitAt(data, &TownHero);
	if (exit == townInExit) { return; }
	townInExit = exit;
	if (exit < 0) { return; }
	string at = "p" + exit;
	Town_Go(data.(at).link);
}

// leaves the location through an exit whose link is sea, street or an interior slot
void Town_Go(string link)
{
	string from = Town_Kind(townHere);
	string to = "";
	if (link == "street") { to = townStreet; }
	if (CheckAttribute(&PdmLocations, townStreet + ".interiors." + link)) { to = PdmLocations.(townStreet).interiors.(link); }
	Trace("PDM town: exit " + link + " from " + townHere);
	if (link == "sea")
	{
		Town_Release();
		Sea_Start();
		return;
	}
	if (to == "" || !CheckAttribute(&PdmLocations, to))
	{
		Trace("PDM town: no location for the exit " + link);
		return;
	}
	Town_Release();
	// coming out of an interior, the hero appears at its door: the arrival point named by its kind
	Town_Load(to, from);
	PostEvent("Town_Tick", TOWN_TICK_MS);
}

ref Town_ShadowDensity()
{
	townShadow[0] = argb(255, 96, 96, 96);
	townShadow[1] = argb(255, 96, 96, 64);
	return &townShadow;
}

float Town_FogDensity()
{
	return stf(TownWeather.Fog.Density);
}

// ---------- the dialogs ----------

void Town_Control()
{
	string control = GetEventData();
	if (control == "Town_Talk" && townLoaded && townTalkNpc < 0) { Town_Talk(); }
}

// the key of the dialog of the NPC i, "" if he has none
string Town_DialogOf(int i)
{
	string id = TownNpc[i].id;
	if (!CheckAttribute(&PdmCharacters, id + ".dialog_key")) { return ""; }
	string dialog = PdmCharacters.(id).dialog_key;
	if (dialog == "" || !CheckAttribute(&PdmDialogs, dialog + ".start")) { return ""; }
	return dialog;
}

// the nearest NPC with a dialog closer than TOWN_TALK_DIST, -1 if none
int Town_NearestTalker()
{
	float hx, hy, hz, x, y, z;
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
	int best = -1;
	float bestDist = TOWN_TALK_DIST * TOWN_TALK_DIST;
	for (int i = 0; i < townNpcCount; i++)
	{
		if (Town_DialogOf(i) == "") { continue; }
		SendMessage(&TownNpc[i], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
		float d = (x - hx) * (x - hx) + (z - hz) * (z - hz);
		if (d < bestDist) { bestDist = d; best = i; }
	}
	return best;
}

void Town_Talk()
{
	int i = Town_NearestTalker();
	if (i < 0) { Trace("PDM dialog: nobody to talk to"); return; }
	Town_TalkTo(i);
}

// the dialog entity draws the window: the speech of the node (TownDialog.Text) and the answers
// (TownDialog.Links.*), and raises DialogEvent with the go of the chosen answer in CurrentNode
void Town_TalkTo(int i)
{
	string id = TownNpc[i].id;
	townTalkNpc = i;
	townTalkKey = Town_DialogOf(i);
	// the window shows "name lastname" of the speaker
	TownNpc[i].name = PdmCharacters.(id).name;
	TownNpc[i].lastname = "";
	CreateEntity(&TownDialog, "dialog");
	SendMessage(&TownDialog, "lii", 1, &TownNpc[i], &TownNpc[i]);
	LayerAddObject(REALIZE, &TownDialog, -256);
	// the voice the character greets with, played once
	if (CheckAttribute(&PdmCharacters, id + ".greeting")) { TownDialog.greeting = PdmCharacters.(id).greeting; }
	Trace("PDM dialog: " + id + " talks " + townTalkKey);
	Town_DialogNode(PdmDialogs.(townTalkKey).start);
}

// the speech of a node of the dialog and its links that are on
void Town_DialogNode(string node)
{
	if (!CheckAttribute(&PdmDialogs, townTalkKey + "." + node))
	{
		Trace("PDM dialog: no node " + node + " in " + townTalkKey);
		Town_DialogLeave();
		return;
	}
	townTalkNode = node;
	aref nd;
	makearef(nd, PdmDialogs.(townTalkKey).(node));
	TownDialog.Text = nd.text;
	DeleteAttribute(&TownDialog, "Links");
	int n = GetAttributesNum(nd);
	int shown = 0;
	aref link;
	string go;
	for (int i = 0; i < n; i++)
	{
		link = GetAttributeN(nd, i);
		if (!CheckAttribute(link, "to") || sti(link.on) == 0) { continue; }
		go = GetAttributeName(link);
		// the text has to be set before the go
		TownDialog.Links.(go) = link.text;
		TownDialog.Links.(go).go = "" + townTalkStep + go;
		shown++;
	}
	Trace("PDM dialog: node " + node + ", " + shown + " answers");
	if (shown == 0) { Town_DialogLeave(); }
}

void Town_DialogEvent()
{
	Town_DialogPick(strcut(TownDialog.CurrentNode, 1, strlen(TownDialog.CurrentNode) - 1));
}

// the player says the answer link: its action runs, the dialog goes to its node or ends
void Town_DialogPick(string link)
{
	townTalkStep = 1 - townTalkStep;
	string text = PdmDialogs.(townTalkKey).(townTalkNode).(link).text;
	Trace("PDM dialog: answer " + link + ": " + text);
	string to = Pdm_DialogChoose(townTalkKey, townTalkNode, link);
	if (to == "" || to == "exit") { Town_DialogLeave(); return; }
	Town_DialogNode(to);
}

// the dialog is deleted on the next frame, not inside its own event
void Town_DialogLeave()
{
	PostEvent("Town_DialogClose", 1);
}

void Town_DialogClose()
{
	if (townTalkNpc < 0) { return; }
	DeleteClass(&TownDialog);
	string id = TownNpc[townTalkNpc].id;
	Trace("PDM dialog: closed, " + id + " has the dialog " + PdmCharacters.(id).dialog_key);
	townTalkNpc = -1;
	if (TownAuto == 2 && !townAutoTalked)
	{
		townAutoTalked = true;
		PostEvent("Town_AutoGo", 2000);
	}
}

// ---------- the autotest, TOWN_AUTO=1/2 run.sh ----------

// the hero of TOWN_AUTO goes to the door of the tavern, then back to the street, then the game quits;
// with TOWN_AUTO=2 he talks to the tavern first
void Town_AutoGo()
{
	if (TownAuto == 2 && townHere != townStreet && !townAutoTalked)
	{
		Town_AutoTalkGo();
		return;
	}
	townAutoStep++;
	string link = "tavern";
	if (townHere != townStreet) { link = "street"; }
	if (townAutoStep > 2)
	{
		Trace("PDM town: autotest done in " + townHere);
		PostEvent("Town_AutoQuit", 3000);
		return;
	}
	aref data;
	makearef(data, PdmLocations.(townHere));
	int door = Town_FindPoint(data, 1, link);
	if (door < 0)
	{
		Trace("PDM town: autotest finds no door " + link);
		PostEvent("Town_AutoQuit", 0);
		return;
	}
	// the exit point itself can lie behind the wall: walk to the spot of its box nearest to the
	// arrival point, half a metre inside the box: Goto point stops some 0.2 m short
	string at = "p" + door;
	float x0 = stf(data.(at).bx0) + 0.5;
	float z0 = stf(data.(at).bz0) + 0.5;
	float x1 = stf(data.(at).bx1) - 0.5;
	float z1 = stf(data.(at).bz1) - 0.5;
	float cx = (x0 + x1) * 0.5;
	float cz = (z0 + z1) * 0.5;
	float bestDist = 1000000.0;
	float x = cx;
	float y = stf(data.(at).y);
	float z = cz;
	int n = sti(data.points);
	for (int i = 0; i < n; i++)
	{
		string pt = "p" + i;
		if (sti(data.(pt).type) != 4) { continue; }
		float dx = stf(data.(pt).x) - cx;
		float dz = stf(data.(pt).z) - cz;
		if (dx * dx + dz * dz < bestDist)
		{
			bestDist = dx * dx + dz * dz;
			x = stf(data.(pt).x);
			y = stf(data.(pt).y);
			z = stf(data.(pt).z);
		}
	}
	if (x0 > x1) { x = cx; } else { if (x < x0) { x = x0; } if (x > x1) { x = x1; } }
	if (z0 > z1) { z = cz; } else { if (z < z0) { z = z0; } if (z > z1) { z = z1; } }
	Trace("PDM town: autotest goes to " + link + " (point " + door + ") at " + x + ", " + z);
	SendMessage(&TownHero, "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point", x, y, z);
	PostEvent("Town_AutoWhere", 15000);
}

// where the hero has got to: a door he does not pass is in the log
void Town_AutoWhere()
{
	float x, y, z;
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	Trace("PDM town: autotest hero at " + x + ", " + y + ", " + z + " in " + townHere);
}

// walks up to the first NPC with a dialog and talks to him
void Town_AutoTalkGo()
{
	townAutoNpc = -1;
	for (int i = 0; i < townNpcCount && townAutoNpc < 0; i++)
	{
		if (Town_DialogOf(i) != "") { townAutoNpc = i; }
	}
	if (townAutoNpc < 0)
	{
		Trace("PDM dialog: autotest finds nobody to talk to in " + townHere);
		townAutoTalked = true;
		PostEvent("Town_AutoGo", 0);
		return;
	}
	float x, y, z;
	SendMessage(&TownNpc[townAutoNpc], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	Trace("PDM dialog: autotest goes to " + TownNpc[townAutoNpc].id);
	SendMessage(&TownHero, "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point", x, y, z);
	PostEvent("Town_AutoTalk", 6000);
}

void Town_AutoTalk()
{
	Town_AutoWhere();
	Town_TalkTo(townAutoNpc);
	PostEvent("Town_AutoPick", 4000);
}

// the first answer of the node that is on, as if the player pressed Enter on it
void Town_AutoPick()
{
	if (townTalkNpc < 0) { return; }
	aref nd;
	makearef(nd, PdmDialogs.(townTalkKey).(townTalkNode));
	int n = GetAttributesNum(nd);
	aref link;
	for (int i = 0; i < n; i++)
	{
		link = GetAttributeN(nd, i);
		if (CheckAttribute(link, "to") && sti(link.on) != 0) { break; }
	}
	if (i >= n) { return; }
	Town_DialogPick(GetAttributeName(link));
	PostEvent("Town_AutoPick", 3500);
}

void Town_AutoQuit()
{
	ExitProgram();
}
