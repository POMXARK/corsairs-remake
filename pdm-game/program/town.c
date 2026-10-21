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
#define MSG_CHARACTER_TURNBYCHR 30341
#define MSG_NPCHARACTER_SETTASK 30400
#define MSG_CAMERA_SETTARGET 30500
#define MSG_CAMERA_FOLLOW 30510
#define MSG_CAMERA_TOPOS 30512

#define TOWN_MAX_NPC 32
#define TOWN_TICK_MS 200
#define TOWN_TALK_BACK 1.0
#define TOWN_TALK_SIDE 0.5
#define TOWN_TALK_HEIGHT 1.8
// townsfolk walk as zombi.dll of the original: models of class 3, 9, 10 (anim_types.idf) outside a
// tavern and a residence go from point to point of type 3, never the one they stand at, come there
// within 2 units (4.6 m) and stand 3 to 12 actions before they go on (rand % 10 + 3)
#define TOWN_WANDER_MS 1000
#define TOWN_WANDER_POINT 3
#define TOWN_WANDER_NEAR 4.6
#define TOWN_WANDER_ACTIONS 3
#define TOWN_WANDER_MORE 9
// ours: an action of a stand is taken as 2 s (stand_calm, 30-40 frames at 20 a second); the
// original has sensors to walk round others, here a walk not done in a minute ends where it is
#define TOWN_WANDER_ACTION_S 2
#define TOWN_WANDER_WAIT 60

object TownLocation;
object TownWeather;
object TownGroups;
object TownHero;
object TownCamera;
object TownTaken;
object TownNpc[TOWN_MAX_NPC];
int townNpcCount = 0;
bool townLoaded = false;
// a loaded location counts up: a wander event of the location before it is dropped
int townGen = 0;
// the town of the island and the location the hero is in
string townIsland = "";
string townStreet = "";
string townHere = "";
// the exit box the hero stands in: he leaves through an exit only after stepping into it
int townInExit = -1;
int townShadow[2];
// TOWN_AUTO (run.sh): the hero follows a plan by himself, for the tests (Town_AutoPlan): 1 walks into
// the tavern and out again, 2 also talks to the first character of the tavern who has a dialog,
// 3 does the errand of the guard Billy in Highrock
object TownPlan;
int townPlanCount = 0;
int townPlanStep = 0;
int townAutoNpc = -1;
// the action of the answer the autotest talks for, whether it is said, the nodes seen
string townAutoWant = "";
bool townAutoDone = false;
bool townAutoTalking = false;
int townAutoWait = 0;
int townAutoPicks = 0;
object TownVisited;

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
	SetEventHandler("Town_Wander", "Town_Wander", 0);
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
	if (TownAuto) { Town_AutoPlan(); }
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
	townGen++;
	PostEvent("Town_Wander", TOWN_WANDER_MS, "l", townGen);
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
		TownNpc[townNpcCount].wander.on = Town_Wanders(cls, kind);
		TownNpc[townNpcCount].wander.point = p;
		TownNpc[townNpcCount].wander.rest = Town_WanderRest();
		TownNpc[townNpcCount].wander.walk = 0;
		TownNpc[townNpcCount].wander.hold = 0;
		CreateEntity(&TownNpc[townNpcCount], "NPCharacter");
		Town_SetModel(&TownNpc[townNpcCount], model);
		Town_Teleport(&TownNpc[townNpcCount], data, p);
		Trace("PDM town: " + card.id + " (" + model + ") on point " + p + " of type " + cls);
		townNpcCount++;
	}
}

// land_sector.dll: a wandering zombi is made for a model of class 3, 9 or 10, not in a tavern or a
// residence; the guards (class 2) and the drunkards stand
bool Town_Wanders(int cls, string kind)
{
	if (kind == "tavern" || kind == "townhall") { return false; }
	return cls == 3 || cls == 9 || cls == 10;
}

// seconds of a stand at a point: 3 to 12 actions (zombi.dll)
int Town_WanderRest()
{
	return (TOWN_WANDER_ACTIONS + rand(TOWN_WANDER_MORE)) * TOWN_WANDER_ACTION_S;
}

// once a second: a townsman who has stood his actions walks to another point; one who came
// within 2 units of it stands again. A speaker and the one the autotest goes to hold still
// (Town_WanderHold)
void Town_Wander()
{
	int gen = GetEventData();
	if (!townLoaded || gen != townGen) { return; }
	PostEvent("Town_Wander", TOWN_WANDER_MS, "l", townGen);
	aref data;
	makearef(data, PdmLocations.(townHere));
	float x, y, z, d;
	string at;
	for (int i = 0; i < townNpcCount; i++)
	{
		if (!sti(TownNpc[i].wander.on) || sti(TownNpc[i].wander.hold)) { continue; }
		if (sti(TownNpc[i].wander.walk) > 0)
		{
			at = "p" + TownNpc[i].wander.point;
			SendMessage(&TownNpc[i], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
			d = (x - stf(data.(at).x)) * (x - stf(data.(at).x)) + (z - stf(data.(at).z)) * (z - stf(data.(at).z));
			TownNpc[i].wander.walk = sti(TownNpc[i].wander.walk) + 1;
			if (d > TOWN_WANDER_NEAR * TOWN_WANDER_NEAR && sti(TownNpc[i].wander.walk) < TOWN_WANDER_WAIT) { continue; }
			SendMessage(&TownNpc[i], "ls", MSG_NPCHARACTER_SETTASK, "Stay");
			TownNpc[i].wander.walk = 0;
			TownNpc[i].wander.rest = Town_WanderRest();
			continue;
		}
		TownNpc[i].wander.rest = sti(TownNpc[i].wander.rest) - 1;
		if (sti(TownNpc[i].wander.rest) > 0) { continue; }
		Town_WanderGo(i, data);
	}
}

// to a point of type 3 picked at random, not his own (zombi.dll); ours: not one another stands at,
// so two do not meet on one spot. His own point is set free
void Town_WanderGo(int i, aref data)
{
	int points = sti(data.points);
	int free = 0;
	int p;
	string at;
	for (p = 0; p < points; p++)
	{
		at = "p" + p;
		if (sti(data.(at).type) == TOWN_WANDER_POINT && !CheckAttribute(&TownTaken, at)) { free++; }
	}
	TownNpc[i].wander.rest = Town_WanderRest();
	if (free == 0) { return; }
	int pick = rand(free - 1);
	for (p = 0; p < points; p++)
	{
		at = "p" + p;
		if (sti(data.(at).type) != TOWN_WANDER_POINT || CheckAttribute(&TownTaken, at)) { continue; }
		if (pick == 0) { break; }
		pick--;
	}
	DeleteAttribute(&TownTaken, "p" + TownNpc[i].wander.point);
	TownTaken.(at) = 1;
	TownNpc[i].wander.point = p;
	TownNpc[i].wander.walk = 1;
	SendMessage(&TownNpc[i], "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point", stf(data.(at).x), stf(data.(at).y), stf(data.(at).z));
}

// a walking townsman stops where he is (hold) or stands a while before he walks on (release)
void Town_WanderHold(int i, bool hold)
{
	if (i < 0 || i >= townNpcCount) { return; }
	if (hold)
	{
		if (sti(TownNpc[i].wander.walk) > 0) { SendMessage(&TownNpc[i], "ls", MSG_NPCHARACTER_SETTASK, "Stay"); }
		TownNpc[i].wander.walk = 0;
		TownNpc[i].wander.hold = 1;
		return;
	}
	TownNpc[i].wander.hold = 0;
	TownNpc[i].wander.rest = Town_WanderRest();
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
		Sea_Start(townIsland);
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

// the Sea_ToPort event of sea.c: back to the street of the town the hero sailed from, at its
// pier; a game started at sea goes to the town of his address
void Sea_ToPort()
{
	if (!seaActive) { return; }
	// the ship came over the world map to another island: its town
	if (seaIsland != "" && seaIsland != townIsland) { townStreet = PdmIslands.(seaIsland).town; }
	Sea_Release();
	Trace("PDM: sea, to the port of " + townStreet);
	if (townStreet == "")
	{
		string island = PlayerCard.address.island;
		Town_Start(PdmIslands.(island).town, "sea");
		return;
	}
	townIsland = Town_IslandOf(townStreet);
	if (townIsland != "") { Sound_TownMusic(sti(PdmIslands.(townIsland).nation)); }
	Town_Load(townStreet, "sea");
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
	if (control == "Town_Talk" && townLoaded && townTalkNpc < 0 && screenName == "") { Town_Talk(); }
}

// the key of the dialog of the NPC i, "" if he has none
string Town_DialogOf(int i)
{
	string id = TownNpc[i].id;
	if (id == "" || !CheckAttribute(&PdmCharacters, id + ".dialog_key")) { return ""; }
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
	Town_WanderHold(i, true);
	// the window shows "name lastname" of the speaker
	TownNpc[i].name = PdmCharacters.(id).name;
	TownNpc[i].lastname = "";
	// the hero stops, the speaker and the hero face each other
	if (TownAuto) { SendMessage(&TownHero, "ls", MSG_NPCHARACTER_SETTASK, "Stay"); }
	SendMessage(&TownNpc[i], "li", MSG_CHARACTER_TURNBYCHR, &TownHero);
	SendMessage(&TownHero, "li", MSG_CHARACTER_TURNBYCHR, &TownNpc[i]);
	Town_TalkCamera(i);
	CreateEntity(&TownDialog, "dialog");
	SendMessage(&TownDialog, "lii", 1, &TownNpc[i], &TownNpc[i]);
	LayerAddObject(REALIZE, &TownDialog, -256);
	// the voice the character greets with, played once
	if (CheckAttribute(&PdmCharacters, id + ".greeting")) { TownDialog.greeting = PdmCharacters.(id).greeting; }
	Trace("PDM dialog: " + id + " talks " + townTalkKey);
	Town_DialogNode(PdmDialogs.(townTalkKey).start);
}

// the camera looks at the speaker over the shoulder of the hero, close to him: nothing stands between
void Town_TalkCamera(int i)
{
	float hx, hy, hz, x, y, z;
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
	SendMessage(&TownNpc[i], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	float dx = hx - x;
	float dz = hz - z;
	float d = sqrt(dx * dx + dz * dz);
	if (d < 0.01) { return; }
	dx = dx / d;
	dz = dz / d;
	// a metre behind the hero, half a metre to his right, a bit over his head
	float cx = hx + dx * TOWN_TALK_BACK + dz * TOWN_TALK_SIDE;
	float cz = hz + dz * TOWN_TALK_BACK - dx * TOWN_TALK_SIDE;
	SendMessage(&TownCamera, "li", MSG_CAMERA_SETTARGET, &TownNpc[i]);
	SendMessage(&TownCamera, "lfffl", MSG_CAMERA_TOPOS, cx, hy + TOWN_TALK_HEIGHT, cz, 0);
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
	SendMessage(&TownCamera, "li", MSG_CAMERA_SETTARGET, &TownHero);
	SendMessage(&TownCamera, "l", MSG_CAMERA_FOLLOW);
	string id = TownNpc[townTalkNpc].id;
	Trace("PDM dialog: closed, " + id + " has the dialog " + PdmCharacters.(id).dialog_key);
	Town_WanderHold(townTalkNpc, false);
	townTalkNpc = -1;
	Town_Refresh();
	// the store or the shipyard the dialog asked for
	PostEvent("Screen_Pending", 0);
	if (townAutoTalking)
	{
		townAutoTalking = false;
		if (townAutoWant != "" && !townAutoDone) { Trace("PDM dialog: autotest FAILED, no answer " + townAutoWant); }
		PostEvent("Town_AutoGo", 2000);
	}
}

// the story may take a character out of the location (Pdm_SetLocation): he leaves at once
void Town_Refresh()
{
	string kind = Town_Kind(townHere);
	string id, place;
	for (int i = 0; i < townNpcCount; i++)
	{
		id = TownNpc[i].id;
		if (id == "" || !CheckAttribute(&PdmCharacters, id + ".location")) { continue; }
		place = PdmCharacters.(id).location;
		if (Town_StoryPlaceIs(place, kind)) { continue; }
		Trace("PDM town: " + id + " leaves for " + place);
		DeleteClass(&TownNpc[i]);
		TownNpc[i].id = "";
	}
}

// ---------- the autotest, TOWN_AUTO=1/2/3 run.sh ----------

// the plan of the autotest: its steps "go" (through the exit with the link arg), "talk" (to the
// character arg, "" for the first one with a dialog, up to the answer whose action is want)
void Town_PlanAdd(string kind, string arg, string want)
{
	string at = "s" + townPlanCount;
	TownPlan.(at) = kind;
	TownPlan.(at).arg = arg;
	TownPlan.(at).want = want;
	townPlanCount++;
}

void Town_AutoPlan()
{
	townPlanCount = 0;
	townPlanStep = 0;
	if (TownAuto == 3)
	{
		// the first errand of Highrock: the guard Billy asks for wine, the tavern keeper sells
		// a bottle, Billy gets it; the story turns the link of the tavern keeper on and changes
		// Billy's dialog twice
		Town_PlanAdd("talk", "Billy___Town_Guard", "PdmA_Wine_agreed");
		Town_PlanAdd("go", "tavern", "");
		Town_PlanAdd("talk", "Jeremy_Windem", "PdmA_Wine_bought");
		Town_PlanAdd("go", "street", "");
		Town_PlanAdd("talk", "Billy___Town_Guard", "PdmA_Wine_good_end");
		return;
	}
	// 4: out to sea and back to the pier (Sea_ToPort), then into the tavern; 5: the same, the ship
	// sails into the port by the harbour (sea.c Sea_AtHarbour)
	// 6: out to sea, over the world map to the next island and into its port (map.c)
	if (TownAuto == 4 || TownAuto == 5 || TownAuto == 6) { Town_PlanAdd("go", "sea", ""); }
	Town_PlanAdd("go", "tavern", "");
	if (TownAuto == 2) { Town_PlanAdd("talk", "", ""); }
	Town_PlanAdd("go", "street", "");
}

// the next step of the plan; after the last one the game quits
void Town_AutoGo()
{
	if (townPlanStep >= townPlanCount)
	{
		Trace("PDM town: autotest done in " + townHere + ", money " + Pdm_Count(PlayerCard, "money") + ", reputation "
			+ Pdm_Count(PlayerCard, "reputation") + ", experience " + Pdm_Count(PlayerCard, "experience"));
		PostEvent("Town_AutoQuit", 3000);
		return;
	}
	string at = "s" + townPlanStep;
	townPlanStep++;
	if (TownPlan.(at) == "talk")
	{
		Town_AutoTalkGo(TownPlan.(at).arg, TownPlan.(at).want);
		return;
	}
	Town_AutoDoor(TownPlan.(at).arg);
}

// walks into the exit box with the link
void Town_AutoDoor(string link)
{
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

// walks up to the character (the first one with a dialog for "") and talks to him
void Town_AutoTalkGo(string who, string want)
{
	townAutoNpc = -1;
	for (int i = 0; i < townNpcCount && townAutoNpc < 0; i++)
	{
		if (Town_DialogOf(i) == "") { continue; }
		if (who == "" || TownNpc[i].id == who) { townAutoNpc = i; }
	}
	if (townAutoNpc < 0)
	{
		Trace("PDM dialog: autotest FAILED, nobody to talk to (" + who + ") in " + townHere);
		PostEvent("Town_AutoGo", 0);
		return;
	}
	townAutoWant = want;
	townAutoDone = false;
	townAutoWait = 0;
	// the hero goes to where he stands: he does not walk away meanwhile
	Town_WanderHold(townAutoNpc, true);
	float x, y, z;
	SendMessage(&TownNpc[townAutoNpc], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	Trace("PDM dialog: autotest goes to " + TownNpc[townAutoNpc].id);
	SendMessage(&TownHero, "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point", x, y, z);
	PostEvent("Town_AutoTalk", 1000);
}

// talks as soon as the hero is near enough, at most 90 s later: an NPC walks a town slowly
void Town_AutoTalk()
{
	float hx, hy, hz, x, y, z;
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
	SendMessage(&TownNpc[townAutoNpc], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	float d = (x - hx) * (x - hx) + (z - hz) * (z - hz);
	if (d > TOWN_TALK_DIST * TOWN_TALK_DIST && townAutoWait < 180)
	{
		townAutoWait++;
		// every 10 s where the hero is: a stop on the way shows in the log
		if (townAutoWait % 20 == 0) { Town_AutoWhere(); }
		PostEvent("Town_AutoTalk", 500);
		return;
	}
	Town_AutoWhere();
	// a test that goes on would talk to the empty air: it stops here, the log shows where
	if (d > TOWN_TALK_DIST * TOWN_TALK_DIST)
	{
		Trace("PDM dialog: autotest FAILED, the hero does not reach " + TownNpc[townAutoNpc].id);
		// who stands in the way
		for (int i = 0; i < townNpcCount; i++)
		{
			SendMessage(&TownNpc[i], "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
			Trace("PDM dialog: " + TownNpc[i].id + " at " + x + ", " + z);
		}
		SendMessage(&TownHero, "ls", MSG_NPCHARACTER_SETTASK, "Stay");
		return;
	}
	DeleteAttribute(&TownVisited, "");
	townAutoPicks = 0;
	townAutoTalking = true;
	Town_TalkTo(townAutoNpc);
	PostEvent("Town_AutoPick", 4000);
}

// the answer the player would choose, as if he pressed Enter on it: the one whose action is wanted;
// on the way to it the first answer to a node not seen yet; once it is said, the way out; without
// a want, the first answer that is on
void Town_AutoPick()
{
	if (townTalkNpc < 0) { return; }
	TownVisited.(townTalkNode) = 1;
	aref nd;
	makearef(nd, PdmDialogs.(townTalkKey).(townTalkNode));
	int n = GetAttributesNum(nd);
	aref link;
	string first = "";
	string fresh = "";
	string out = "";
	string pick = "";
	string name, to;
	for (int i = 0; i < n; i++)
	{
		link = GetAttributeN(nd, i);
		if (!CheckAttribute(link, "to") || sti(link.on) == 0) { continue; }
		name = GetAttributeName(link);
		to = link.to;
		if (first == "") { first = name; }
		if (!townAutoDone && townAutoWant != "" && link.action == townAutoWant) { pick = name; }
		if (to == "exit") { if (out == "") { out = name; } }
		else { if (fresh == "" && !CheckAttribute(&TownVisited, to)) { fresh = name; } }
	}
	if (first == "") { return; }
	if (pick != "") { townAutoDone = true; }
	else
	{
		pick = first;
		if (townAutoDone && out != "") { pick = out; }
		if (!townAutoDone && townAutoWant != "" && fresh != "") { pick = fresh; }
	}
	townAutoPicks++;
	if (townAutoPicks > 30) { Town_DialogLeave(); return; }
	Town_DialogPick(pick);
	PostEvent("Town_AutoPick", 3500);
}

void Town_AutoQuit()
{
	ExitProgram();
}
