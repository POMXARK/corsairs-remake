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
// E talks to the nearest character who has a dialog (card.dialog_key, see Town_Talk below). In an exit box
// the icon of the exit shows top right (hud.c), Space goes through it.

#define MSG_LOCATION_ADD_MODEL 30100
#define MSG_LOCATION_SET_CHRS_PATCH 30120
#define MSG_LOCATION_MODELSPATH 30140
#define MSG_LOCATION_TEXTURESPATH 30141
#define MSG_CHARACTER_SETMODEL 30200
#define MSG_CHARACTER_GETPOS 30202
#define MSG_CHARACTER_GETAY 30203
#define MSG_CHARACTER_TELEPORT_AY 30211
#define MSG_CHARACTER_TURNBYCHR 30341
#define MSG_CHARACTER_TURNBYPOINT 30342
#define MSG_CHARACTER_HEADLOOK_DEFAULT 30380
#define MSG_CHARACTER_HEADLOOK_CHARACTER 30382
#define MSG_NPCHARACTER_SETTASK 30400
#define MSG_CAMERA_SETTARGET 30500
#define MSG_CAMERA_FOLLOW 30510
#define MSG_CAMERA_TOPOS 30512
// the pitch of the follow camera (location_camera.cpp:397 reads one float into lAx and locks it,
// where the default ax of 0.4 looks steeply down) and the distance of the orbit
#define MSG_CAMERA_MOVE 30513
#define MSG_CAMERA_SET_RADIUS 30521

#define TOWN_MAX_NPC 32
#define TOWN_TICK_MS 200
#define TOWN_TALK_BACK 1.0
#define TOWN_TALK_SIDE 0.5
#define TOWN_TALK_HEIGHT 1.8
// metres around an exit box that still take the exit: the patch is cut at the walls by the reach of
// the body and the floor of City_Tendales ends 0.2 m short of the box of its sea exit (ours)
#define TOWN_EXIT_REACH 0.5
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
// the exit box the hero appears in, until he steps out of it: its icon shows, the autotest does not go back
int townArriveExit = -1;
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
	// the step of the wind check (TOWN_AUTO=20): the hero walks to the right of the city, through the
	// vegetation, and stands at each spot
	int townWindStep = 0;
	// the phase of one spot of the wind check: 0 the hero walks to it, 1 the camera turns to his right
	// (90 degrees), 2 the camera follows him on
	int townWindPhase = 0;
	// TOWN_AUTO=30: the character check. the hero walks to the points of type 3 in the town's own
	// point list, where class characters stand, and the level follow camera frames him with the
	// NPC he reached: the frames of this plan are compared with the original game's shading
	int townCharStep = 0;
	int townCharPhase = 0;
// the link of the door the autotest is sent to: a door it passes on the way is not taken
string townAutoLink = "";
// the one the autotest talks to stands at townAutoGoX/Z; the hero walks to a spot townAutoK steps of
// TOWN_AUTO_STEP short of him; townAutoLastX/Z: where the hero was at the last look
float townAutoGoX, townAutoGoY, townAutoGoZ, townAutoLastX, townAutoLastZ;
int townAutoK = 0;
object TownVisited;

#define TOWN_TALK_DIST 3.0
#define TOWN_AUTO_COUNTER 0.3
#define TOWN_AUTO_STEP 0.25
// TALK_NPC / TALK_ANGLE (talk-angles.sh): the hero talks to that character from the angle, TALK_RADIUS off him
#define TALK_RADIUS 1.5
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
	Town_Handlers();
	if (TownAuto) { Town_AutoPlan(); }
	Town_Load(loc, from);
	PostEvent("Town_Tick", TOWN_TICK_MS);
}

// the handlers of the town, for its start and for a game loaded in it (save.c)
void Town_Handlers()
{
	SetEventHandler("EWhr_GetShadowDensity", "Town_ShadowDensity", 0);
	SetEventHandler("EWhr_GetFogDensity", "Town_FogDensity", 0);
	SetEventHandler("Town_Tick", "Town_Tick", 0);
	SetEventHandler("Town_Wander", "Town_Wander", 0);
	SetEventHandler("Town_AutoGo", "Town_AutoGo", 0);
	SetEventHandler("Town_AutoWhere", "Town_AutoWhere", 0);
	SetEventHandler("Town_AutoQuit", "Town_AutoQuit", 0);
	SetEventHandler("Town_AutoTalk", "Town_AutoTalk", 0);
	SetEventHandler("Town_AutoPick", "Town_AutoPick", 0);
	SetEventHandler("Town_WindWalk", "Town_WindWalk", 0);
	SetEventHandler("TownFace_Start", "TownFace_Start", 0);
	SetEventHandler("TownFace_Camera", "TownFace_Camera", 0);
	SetEventHandler("TownFace_End", "TownFace_End", 0);
	SetEventHandler("Control Activation", "Town_Control", 0);
	SetEventHandler("DialogEvent", "Town_DialogEvent", 0);
	SetEventHandler("DialogCancel", "Town_DialogLeave", 0);
	SetEventHandler("EmergencyDialogExit", "Town_DialogLeave", 0);
	SetEventHandler("Town_DialogClose", "Town_DialogClose", 0);
	SetEventHandler("Town_ExitGo", "Town_ExitGo", 0);
	SetEventHandler("Town_HudGo", "Town_HudGo", 0);
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
	// the mouse up looks up: 4 is INVERSE_CONTROL of menu.c, included after this file
	Menu_MapKey("ChrCamTurnV", 257, 4);
	// hold the right button and the mouse orbits the camera around the hero without turning him;
	// let go and the camera swings back behind; ChrCamTurnH is the orbit angle in that mode.
	MapKey("ChrCamSpecMode", 2);
	MapKey("ChrCamTurnH", 256);
	// middle button / C: first-person look and back
	MapKey("ChrCamCameraSwitch", 4);
	MapKey("ChrCamNormalize", 67);
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

// while a dialog is open the hero stands: the camera looks at the speaker, not after him
void Town_LockHero(bool lock)
{
	LockControl("ChrForward", lock);
	LockControl("ChrBackward", lock);
	LockControl("ChrTurnHL", lock);
	LockControl("ChrTurnHR", lock);
	LockControl("ChrRun", lock);
	LockControl("ChrTurnH", lock);
	LockControl("ChrCamTurnV", lock);
	LockControl("Town_Talk", lock);
	LockControl("BIFastCommand", lock);
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
	TownWeather.Sun.Ambient = argb(0, 105, 105, 115);
	TownWeather.Sun.HeightAngle = 0.62;
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
	// the vegetation on its own model: the crowns sway in the wind (WindLeaf technique)
	SendMessage(&TownLocation, "lssl", MSG_LOCATION_ADD_MODEL, data.model + "_veg", "WindLeaf", 10);
	// the shop signs on their own model: redone by pdm_world.py --signs without the BSP of the town
	SendMessage(&TownLocation, "lssl", MSG_LOCATION_ADD_MODEL, data.model + "_signs", "DLightModel", 10);
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
	townInExit = -1;
	townArriveExit = Town_ExitAt(data, &TownHero);

	CreateEntity(&TownCamera, "locationcamera");
	SendMessage(&TownCamera, "li", MSG_CAMERA_SETTARGET, &TownHero);
	SendMessage(&TownCamera, "l", MSG_CAMERA_FOLLOW);
	SendMessage(&Scene, "si", "SetActiveCamera", &TownCamera);

	Town_PlaceCharacters(data);
	Hud_CreateLog();
	Hud_LandStart();
	// the voices of many when the location is full of people
	Sound_Location(data.sound, townNpcCount > 2);
	townLoaded = true;
	townGen++;
	PostEvent("Town_Wander", TOWN_WANDER_MS, "l", townGen);
	// the autotest of saving (save.c) has no walk of its own
	if (TownAuto == 20) { PostEvent("Town_WindWalk", 3000); }
	else if (TownAuto == 30) { PostEvent("Town_CharWalk", 3000); }
	else if (TownAuto == 40 || TownAuto == 41) { PostEvent("TownFace_Start", 3000); }
	else if (TownAuto && TownAuto != SAVEFILE_AUTO) { PostEvent("Town_AutoGo", 3000); }
	Trace("PDM town: in " + loc + " from " + from + ", " + townNpcCount + " characters");
}

void Town_Release()
{
	Town_DialogClose();
	Hud_LandRelease();
	Hud_ReleaseLog();
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

// the exit point whose box the character stands in or by (TOWN_EXIT_REACH), -1 if none
int Town_ExitAt(aref data, ref chr)
{
	float x, y, z;
	SendMessage(chr, "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	int n = sti(data.points);
	string at;
	float r = TOWN_EXIT_REACH;
	for (int i = 0; i < n; i++)
	{
		at = "p" + i;
		if (sti(data.(at).type) != 1) { continue; }
		if (x >= stf(data.(at).bx0) - r && x <= stf(data.(at).bx1) + r && z >= stf(data.(at).bz0) - r && z <= stf(data.(at).bz1) + r)
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
	if (exit != townArriveExit) { townArriveExit = -2; }
	if (exit == townInExit) { return; }
	townInExit = exit;
	if (exit < 0) { Hud_SetAction("Nothing", ""); return; }
	string at = "p" + exit;
	string link = data.(at).link;
	string note = link;
	if (CheckAttribute(&PdmHud, "note." + link)) { note = PdmHud.note.(link); }
	if (link == "sea") { Hud_SetAction("ToSea", note); }
	else { Hud_SetAction("ToDoor", note); }
	// the autotest walks in and stands a moment under the icon
	if (TownAuto && exit != townArriveExit && link == townAutoLink) { PostEvent("Town_ExitGo", HUD_AUTO_EXIT_MS, "l", townGen); }
}

// Space (BI_FastCommand of hud.c): through the exit the hero stands in. Called in the frame of the log
// entity, which the location deletes: the location changes in the next event
void Town_Action()
{
	if (!townLoaded || townInExit < 0 || townTalkNpc >= 0 || screenName != "") { return; }
	PostEvent("Town_ExitGo", 0, "l", townGen);
}

void Town_ExitGo()
{
	int gen = GetEventData();
	if (!townLoaded || gen != townGen || townInExit < 0) { return; }
	aref data;
	makearef(data, PdmLocations.(townHere));
	string at = "p" + townInExit;
	Town_Go(data.(at).link);
}

// a door of type 4 with this link stands in the location the hero is in now (the rule: the door of
// a location is the marker of type 4). The original game opens the menu of the land from the reload
// list of the loaded location itself (landinterface.c:520, Locations[FindLoadedLocation()]), so a
// place with no door in this location, a tavern in a town without a tavern, is never offered
bool Town_HasDoor(string link)
{
	aref data;
	makearef(data, PdmLocations.(townHere));
	int n = sti(data.points);
	string at;
	for (int i = 0; i < n; i++)
	{
		at = "p" + i;
		if (sti(data.(at).type) == 4 && data.(at).link == link) { return true; }
	}
	return false;
}

// the menu of the land (hud.c): a place of the town the hero is not in, the sea from a town of an
// island; a place is offered only when its door is in the location the hero stands in
bool Town_CanGo(string link)
{
	if (link == "sea") { return townIsland != ""; }
	if (link == "street") { return townHere != townStreet; }
	if (!CheckAttribute(&PdmLocations, townStreet + ".interiors." + link)) { return false; }
	string to = PdmLocations.(townStreet).interiors.(link);
	if (to == townHere || !CheckAttribute(&PdmLocations, to)) { return false; }
	// Town_Go opens doors of the street from anywhere, the hero may be inside an interior now
	if (townHere == townStreet) { return Town_HasDoor(link); }
	return Town_HasDoor("street");
}

// "sl" the place, the generation of the location: the command of the menu of the land, from anywhere
void Town_HudGo()
{
	string link = GetEventData();
	int gen = GetEventData();
	if (!townLoaded || gen != townGen || townTalkNpc >= 0 || !Town_CanGo(link)) { return; }
	Town_Go(link);
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
		// the original saves the game when the ship leaves the town; after the first frames, when the ship
		// has written its place (save.c)
		PostEvent("Save_Auto", SAVEFILE_AUTO_MS);
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
	townShadow[0] = argb(255, 40, 40, 40);
	townShadow[1] = argb(255, 40, 40, 30);
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
	// the hero stops and faces the speaker; the speaker keeps the turn of his point (a drinker stays
	// on his bench, a keeper behind his counter) and only turns his head to the hero (ours)
	if (TownAuto) { SendMessage(&TownHero, "ls", MSG_NPCHARACTER_SETTASK, "Stay"); }
	Town_LockHero(true);
	SendMessage(&TownNpc[i], "li", MSG_CHARACTER_HEADLOOK_CHARACTER, &TownHero);
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
	// the neural voice of the speech (docs/voice-over.md), said after the greeting; the entity cuts the last one
	DeleteAttribute(&TownDialog, "voice");
	if (optionsVoice && CheckAttribute(&PdmVoiceLines, townTalkKey + "." + node)) { TownDialog.voice = PdmVoiceLines.(townTalkKey).(node); }
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
	SendMessage(&TownNpc[townTalkNpc], "l", MSG_CHARACTER_HEADLOOK_DEFAULT);
	Town_LockHero(false);
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
	// TALK_NPC (talk-angles.sh): the character may stand in the street, the hero talks where he arrived
	if (TalkNpc != "") { Town_PlanAdd("talk", "", ""); return; }
	// 4: out to sea and back to the pier (Sea_ToPort), then into the tavern; 5: the same, the ship
	// sails into the port by the harbour (sea.c Sea_AtHarbour)
	// 6: out to sea, over the world map to the next island and into its port (map.c)
	// 10: through the menu of the land (Tab, hud.c) from the pier to every place of the town: inside
	// a place its menu offers only the street and the sea, so each one is left by the street, the way
	// the original builds the menu from the reload list of the loaded location (landinterface.c:520);
	// at the end the tavern and the sea from it
	if (TownAuto == 10)
	{
		Town_PlanAdd("hud", "store", "");
		Town_PlanAdd("hud", "street", "");
		Town_PlanAdd("hud", "townhall", "");
		Town_PlanAdd("hud", "street", "");
		Town_PlanAdd("hud", "tavern", "");
		Town_PlanAdd("hud", "street", "");
		Town_PlanAdd("hud", "shipyard", "");
		Town_PlanAdd("hud", "street", "");
		Town_PlanAdd("hud", "tavern", "");
		Town_PlanAdd("hud", "sea", "");
		return;
	}
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
	if (TownPlan.(at) == "hud")
	{
		Hud_LandAutoOpen(TownPlan.(at).arg);
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
	townAutoLink = link;
	if (door < 0)
	{
		Trace("PDM town: autotest finds no door " + link);
		PostEvent("Town_AutoQuit", 0);
		return;
	}
	// the exit point itself lies in the door, the half of the box in the house is cut off the floor:
	// walk to the spot of the box nearest to the arrival point, Goto point stops some 0.2 m short,
	// within TOWN_EXIT_REACH
	string at = "p" + door;
	float x0 = stf(data.(at).bx0);
	float z0 = stf(data.(at).bz0);
	float x1 = stf(data.(at).bx1);
	float z1 = stf(data.(at).bz1);
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
	string need = who;
	if (TalkNpc != "") { need = TalkNpc; }
	for (int i = 0; i < townNpcCount && townAutoNpc < 0; i++)
	{
		if (Town_DialogOf(i) == "") { continue; }
		if (need == "" || TownNpc[i].id == need) { townAutoNpc = i; }
	}
	if (townAutoNpc < 0)
	{
		Trace("PDM dialog: autotest FAILED, nobody to talk to (" + need + ") in " + townHere);
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
	// a trader stands behind his counter, the box of his point (type 5): Goto point finds no way there and
	// the hero does not move. Ours: to the spot of the box nearest to the hero, TOWN_AUTO_COUNTER off it
	aref data;
	makearef(data, PdmLocations.(townHere));
	string at = "p" + TownNpc[townAutoNpc].wander.point;
	if (!sti(TownNpc[townAutoNpc].wander.on) && stf(data.(at).bx0) < stf(data.(at).bx1))
	{
		float hx, hy, hz;
		SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
		float bx = hx;
		float bz = hz;
		if (bx < stf(data.(at).bx0)) { bx = stf(data.(at).bx0); }
		if (bx > stf(data.(at).bx1)) { bx = stf(data.(at).bx1); }
		if (bz < stf(data.(at).bz0)) { bz = stf(data.(at).bz0); }
		if (bz > stf(data.(at).bz1)) { bz = stf(data.(at).bz1); }
		float len = sqrt((hx - bx) * (hx - bx) + (hz - bz) * (hz - bz));
		if (len > TOWN_AUTO_COUNTER)
		{
			x = bx + (hx - bx) * TOWN_AUTO_COUNTER / len;
			z = bz + (hz - bz) * TOWN_AUTO_COUNTER / len;
		}
	}
	if (TalkNpc != "")
	{
		// the angle of the test: the spot TALK_RADIUS off the character, TalkAngle degrees from his +x
		float ang = TalkAngle * 3.14159265 / 180.0;
		x += TALK_RADIUS * cos(ang);
		z += TALK_RADIUS * sin(ang);
	}
	townAutoGoX = x;
	townAutoGoY = y;
	townAutoGoZ = z;
	townAutoK = 0;
	Town_AutoTalkStep();
	Trace("PDM dialog: autotest goes to " + TownNpc[townAutoNpc].id + " at " + x + ", " + z);
	PostEvent("Town_AutoTalk", 1000);
}

// one sits at a table, off the patch, or on a bit of it the tables cut off the floor (pdm_world.py):
// Goto point takes no spot without a node of the patch (AICharacter::CmdGotoPoint returns false), and
// on a cut off bit it finds no way and the hero stands. Ours: the spot steps TOWN_AUTO_STEP from the one
// to talk to towards the hero till Goto point takes it; Town_AutoTalk steps on while the hero stands
void Town_AutoTalkStep()
{
	float hx, hy, hz;
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
	townAutoLastX = hx;
	townAutoLastZ = hz;
	float far = sqrt((hx - townAutoGoX) * (hx - townAutoGoX) + (hz - townAutoGoZ) * (hz - townAutoGoZ));
	int ok = 0;
	float t;
	while (ok == 0 && townAutoK * TOWN_AUTO_STEP < far)
	{
		t = townAutoK * TOWN_AUTO_STEP / far;
		ok = SendMessage(&TownHero, "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point",
			townAutoGoX + (hx - townAutoGoX) * t, townAutoGoY, townAutoGoZ + (hz - townAutoGoZ) * t);
		townAutoK++;
	}
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
		// standing still for a second: no way to that spot, the next one
		if (townAutoWait % 2 == 0)
		{
			if (abs(hx - townAutoLastX) + abs(hz - townAutoLastZ) < 0.05) { Town_AutoTalkStep(); }
			townAutoLastX = hx;
			townAutoLastZ = hz;
		}
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
	if (townAutoPicks == 0 && TalkNpc != "")
	{
		Trace("PDM dialog: autotest talked to " + TownNpc[townTalkNpc].id + " from angle " + TalkAngle + ", answer " + pick);
	}
	townAutoPicks++;
	if (townAutoPicks > 30) { Town_DialogLeave(); return; }
	Town_DialogPick(pick);
	// one character from one angle is the test: the first answer is in the log, the run ends
	if (TalkNpc != "") { PostEvent("Town_AutoQuit", 3000); return; }
	PostEvent("Town_AutoPick", 3500);
}

void Town_AutoQuit()
{
	ExitProgram();
}

// wind check (TOWN_AUTO=20): the hero walks the streets and the western yard of the town over its
// own walking points (the points of type 3 of City_HighRock in data/pdm_world.c: p19, p20, p21, p22,
// p23), and at every spot the camera looks first to his right and then to his left, four metres
// aside at his eye height (MSG_CAMERA_TOPOS of location_camera.cpp:case MSG_CAMERA_TOPOS stands the
// camera at the given point and keeps it looking at the character; MSG_CHARACTER_GETPOS of
// character.cpp and MSG_CHARACTER_GETAY of it give the real place and facing of the hero, so the
// side points are computed from him, not from a literal spot; character.cpp uses (sin(ay),0,cos(ay))
// as the way he walks and (cos(ay),0,-sin(ay)) as his right hand). MSG_CAMERA_MOVE puts the pitch at
// the eye level instead of the steep default of ax = 0.4, MSG_CAMERA_SET_RADIUS keeps five metres.
// The last leg walks the hero to the marker of the town tavern (the point of type 4 with the link
// "tavern", the marker stands just outside the box of the door that town.c:Town_ExitAt reads): the
// tick of the location notices him in the box (TOWN_EXIT_REACH of the body reach covers the gap of
// the wall) and Town_ExitGo goes through it, so the tavern interior becomes the location of the run
// and the frames show the place the hero moved into. The crowns of the vegetation sway in the wind
// (WindLeaf).
void Town_WindWalk()
{
	float x, z, hx, hy, hz, ay, r;
	int legMs = 15000;
	aref data;
	int n, i, found;
	string at, link;
	// the stops of the route are the walking points of the town that stand next to the clumps of the
	// vegetation of this town, found in the model itself: the histogram of the crown vertices of
	// city_highrock_veg.gm (one vertex buffer, stride 36, the crowns 0.34 .. 4.61 m high) cut in 2 m
	// cells puts tree3_leaves.tga and tree2_leaves.tga around x -22 .. -18 with z 24 .. 34, around
	// x -22 with z -18 .. -16 and around x 20 .. 22 with z 16 .. 18. The stops below are the points of
	// type 3 of City_HighRock in data/pdm_world.c that sit nearest to those clumps, and legMs covers
	// the way to the stop along the patch of the location
	if (townWindStep == 0) { x = -9.258; z = 19.389; legMs = 15000; }
	else if (townWindStep == 1) { x = -17.857; z = 30.376; legMs = 20000; }
	else if (townWindStep == 2) { x = -18.832; z = 18.968; legMs = 20000; }
	else if (townWindStep == 3) { x = -20.369; z = -16.739; legMs = 40000; }
	else if (townWindStep == 4) { x = 17.958; z = -21.641; legMs = 40000; }
	else if (townWindStep == 5) { x = 20.100; z = 14.722; legMs = 40000; }
	else if (townWindStep == 6)
	{
		// the marker just outside the door (the point of type 4 with the link of the tavern) is a
		// node of the AI patch, while the box of the door itself is cut off from the patch by the
		// wall: the hero stands at the marker and Town_ExitAt still counts him in the box, because
		// the reach of the body is added to the box (TOWN_EXIT_REACH of town.c, used in it)
		makearef(data, PdmLocations.(townHere));
		n = sti(data.points);
		found = 0;
		for (i = 0; i < n; i++)
		{
			at = "p" + i;
			if (found || sti(data.(at).type) != 4) { continue; }
			if (data.(at).link != "tavern") { continue; }
			x = stf(data.(at).x);
			z = stf(data.(at).z);
			found = 1;
		}
		if (!found)
		{
			// no tavern marker of this town: the marker of any door its menu can go to
			for (i = 0; i < n; i++)
			{
				at = "p" + i;
				if (found || sti(data.(at).type) != 4) { continue; }
				link = data.(at).link;
				if (!Town_CanGo(link)) { continue; }
				x = stf(data.(at).x);
				z = stf(data.(at).z);
				found = 1;
			}
		}
		if (!found)
		{
			Trace("PDM town: wind check found no door to go through, it stops here");
			PostEvent("Town_AutoQuit", 3000);
			return;
		}
		legMs = 20000;
	}
	else if (townWindStep == 7)
	{
		// the hero stands in the box of the door: the tick of the location has noticed it (townInExit
		// is the number of that box), go through the door and quit when the new place is loaded
		Trace("PDM town: wind check goes through the door of the location");
		PostEvent("Town_ExitGo", 1000, "l", townGen);
		PostEvent("Town_AutoQuit", 15000);
		return;
	}
	else
	{
		Trace("PDM town: wind check done");
		PostEvent("Town_AutoQuit", 1000);
		return;
	}
	// phase 0: the hero walks to the spot and stands there
	if (townWindPhase == 0)
	{
		Trace("PDM town: wind check walks to " + x + ", " + z);
		SendMessage(&TownHero, "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point", x, 0.115, z);
		townWindPhase = 1;
		PostEvent("Town_WindWalk", legMs);
		return;
	}
	// the place and the facing of the hero, read from him at every look
	SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
	SendMessage(&TownHero, "le", MSG_CHARACTER_GETAY, &ay);
	// the crowns of the vegetation of this town reach 4.6 m high and the clumps are 4 m wide, so the
	// look camera stands nine metres aside: closer than that it gets inside the crown and the frame
	// becomes a magnified fragment of the leaf texture instead of the tree
	r = 9.0;
	// phase 1: the camera looks to the right hand of the hero, it stands at his left hand and keeps
	// looking at him, so the view goes along his right-hand vector
	if (townWindPhase == 1)
	{
		Trace("PDM town: wind check looks to the right at " + x + ", " + z);
		SendMessage(&TownCamera, "lfffl", MSG_CAMERA_TOPOS, hx - cos(ay) * r, hy + 1.7, hz + sin(ay) * r, 1);
		townWindPhase = 2;
		PostEvent("Town_WindWalk", 5000);
		return;
	}
	// phase 3: the same spot, the camera looks to the other side, along his left hand
	if (townWindPhase == 3)
	{
		Trace("PDM town: wind check looks to the left at " + x + ", " + z);
		SendMessage(&TownCamera, "lfffl", MSG_CAMERA_TOPOS, hx + cos(ay) * r, hy + 1.7, hz - sin(ay) * r, 1);
		townWindPhase = 4;
		PostEvent("Town_WindWalk", 5000);
		return;
	}
	// phase 2 and 4: the camera goes back to the hero and follows him on, at the eye level and five
	// metres behind (MSG_CAMERA_MOVE of location_camera.cpp sets the pitch it locks, MSG_CAMERA_SET
	// RADIUS the distance of the orbit)
	SendMessage(&TownCamera, "l", MSG_CAMERA_FOLLOW);
	SendMessage(&TownCamera, "lf", MSG_CAMERA_MOVE, 0.12);
	SendMessage(&TownCamera, "lf", MSG_CAMERA_SET_RADIUS, 5.0);
	if (townWindPhase == 2)
	{
		townWindPhase = 3;
		PostEvent("Town_WindWalk", 3000);
		return;
	}
	townWindPhase = 0;
	townWindStep++;
	PostEvent("Town_WindWalk", 1500);
}

// TOWN_AUTO=30: the character check. The stops are the points of type 3 in the town's own point
// list, taken one by one in order: class characters are placed by Town_PlaceCharacters on exactly
// these points, so walking the hero to the stop brings him face to face with a standing NPC. The
// camera keeps the follow mode, a level pitch (MSG_CAMERA_MOVE of location_camera.cpp) and a short
// orbit, so the hero's back and the NPC's front fill the frame like in the original game's shots
void Town_CharWalk()
{
	aref data;
	makearef(data, PdmLocations.(townHere));
	int n = sti(data.points);
	int i, found, want;
	float x, z;
	string at;
	if (townCharPhase == 0)
	{
		found = 0; want = 0;
		// find the townCharStep-th point of type 3
		for (i = 0; i < n; i++)
		{
			at = "p" + i;
			if (sti(data.(at).type) != 3) { continue; }
			if (want == townCharStep) { found = 1; x = stf(data.(at).x); z = stf(data.(at).z); break; }
			want++;
		}
		if (!found)
		{
			Trace("PDM town: char check has no more standing points, done");
			PostEvent("Town_AutoQuit", 2000);
			return;
		}
		Trace("PDM town: char check " + townCharStep + " walks to the standing point at " + x + ", " + z);
		// the floor height of the town patch, as the wind check's legs use it
		SendMessage(&TownHero, "lsfff", MSG_NPCHARACTER_SETTASK, "Goto point", x, 0.115, z);
		townCharPhase = 1;
		PostEvent("Town_CharWalk", 12000);
		return;
	}
	// phase 1: the hero stands at the point; the camera returns to the follow mode with a level
	// pitch and a short orbit (MSG_CAMERA_MOVE and MSG_CAMERA_SET_RADIUS of location_camera.cpp)
	Trace("PDM town: char shot " + townCharStep + " taken");
	SendMessage(&TownCamera, "l", MSG_CAMERA_FOLLOW);
SendMessage(&TownCamera, "lf", MSG_CAMERA_MOVE, 0.10);
SendMessage(&TownCamera, "lf", MSG_CAMERA_SET_RADIUS, 2.5);
	townCharPhase = 0;
	townCharStep++;
	PostEvent("Town_CharWalk", 3000);
}
