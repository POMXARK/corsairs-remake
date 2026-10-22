// The toolbar of the original (SQUAD_CONTROL.dll on TEXTURES/toolbar), tools/pdm_hud.py converts its pictures
// into battle_interface\pdm and its notes into data\pdm_hud.c (PdmHud).
//
// At sea BATTLE_INTERFACE draws the picture of the ship of the hero bottom left, with the flag of his nation, the
// class of the ship and the bars of the hull and the sails above it. Tab opens the commands to the right of it:
// arrows pick, Enter gives, Escape closes, as in the original. Bottom right the panel of the charges (ship_info:
// the sails, the crew and the hull, the balls, the grapes, the knippels and the bombs in the hold, the loaded one
// lit) or the pictures of the enemy ships pressed to the right edge, or nothing: "=" changes them in turn. The commands are the transitions: "На землю" at the harbour of a town, "Карта" (the
// world map), "Ускорение" (the time), "Абордаж" in the battle near the enemy (boarding.c). On the land ILogAndActions shows the icon of the exit the hero stands
// in with the name of the place it leads to; Space goes through it (the original "Действие").
// Top right at sea the navigator (NAVIGATOR.dll): the map of the island round the ship in the brooch, the letters
// of the compass and the wind arrow turned with the heading, the speeds of the ship and the wind on its plate.
// Space at sea does the possible action: lands at the harbour (ours: the original lands by the menu only).

// shared/battle_interface/msg_control.h and log_and_action.h
#define BI_IN_CREATE_SHIP 46011
#define BI_RELATION_FRIEND 1
#define LOG_ADD_STRING 45020
#define LOG_SET_ACTIVE_ACTION 45021
#define LOG_AND_ACTIONS_INIT 45022
// the keys of the original (controls.ini): Tab the icons, arrows and Enter in them, F2 the possible action,
// Space the action on the land
#define HUD_KEY_MENU 9
#define HUD_KEY_ACTION 32
// "=" (VK_OEM_PLUS, control19 of controls.ini): the corner bottom right, the charges, the enemies or nothing
#define HUD_KEY_CORNER 187
#define HUD_CORNER_INFO 0
#define HUD_CORNER_ENEMIES 1
#define HUD_CORNER_NONE 2
// the layout of the original is for 800x600 (ours: everything scales with the height of the window)
#define HUD_BASE_H 600.0
// the navigator: the size of its brooch (the frame of 128 of the original), its map inside the ring of the frame
// (radius 58), the speeds on the plate below it (at 56 under the centre, 42 to the sides), all in pixels of 800x600
#define HUD_NAV_FRAME 128.0
#define HUD_NAV_MAP 58.0
#define HUD_NAV_PLATE_Y 56.0
#define HUD_NAV_PLATE_X 42.0
// the toolbar of SQUAD_CONTROL.dll: a picture of 64x50 at 5 from the left and the bottom, the next one 66 to the
// right; its plate of the bars (64x20) 22 above it; the panel of the charges 256x50 at 5 from the right
#define HUD_PIC_W 64.0
#define HUD_PIC_STEP 66.0
#define HUD_PIC_MARGIN 5.0
#define HUD_PIC_H 50.0
#define HUD_PLATE_UP 22.0
#define HUD_INFO_W 256.0
// the charges in the order of the rows of ship_info: the balls, the grapes, the knippels, the bombs
#define HUD_CHARGES 4
// TOWN_AUTO: the autotest stands in an exit this long before it goes through, so its icon is on the video
#define HUD_AUTO_EXIT_MS 1500
// TOWN_AUTO=7: the corner shows the enemies from then on
#define HUD_AUTO_CORNER_MS 20000
#define MSG_BATTLE_LAND_MAKE_COMMAND 46105
// TOWN_AUTO=10: the pause between the steps of the autotest in the menu of the land
#define HUD_AUTO_LAND_MS 700
// the places of a town in the menu of the land, in the order of the street
#define HUD_LAND_PLACES 6
string hudLandPlaces[HUD_LAND_PLACES] = {"street", "tavern", "store", "shipyard", "townhall", "sea"};
object LandInterface;
bool hudLand = false;
string hudLandAuto = "";
int hudLandAutoSteps = 0;

object BattleInterface;
object ScreenLog;
int hudW = 800;
int hudH = 600;
// what BI_GetData returns: the cell of the picture, its lit cell, the texture of the list, dead
int hudShipPicture[4];
// what GetCurrentCharge returns: the row of the panel of the charges (the lit charge, or the empty one), the sails,
// the wind, the powder, the powder run out
int hudCharge[5];
// what the corner bottom right shows (HUD_CORNER_*), kept for the next sea as the original keeps it on the hero
int hudCorner = HUD_CORNER_INFO;
string hudChargeGoods[HUD_CHARGES] = {"Cannonballs", "Grapes", "Knippels", "Bombs"};
// the loaded charge (ours: the guns fire balls only, the other charges are not done yet)
int hudChargeLoaded = 0;
bool hudSea = false;
// the engine finds no enemy near: the map may be opened (BI_SetSeaState)
bool hudMapFree = true;
// the action ILogAndActions shows, set only when it changes
string hudAction = "";

// a length of the layout of 800x600 in pixels of the window
int Hud_Px(float v)
{
	return makeint(v * hudH / HUD_BASE_H);
}

string Hud_Pos(float x, float y)
{
	return Hud_Px(x) + "," + Hud_Px(y);
}

// asked by ILogAndActions when it is created
void Hud_WindowSize()
{
	hudW = GetEventData();
	hudH = GetEventData();
}

// The log of the messages at the top and the icon of the possible action top right; text1 is the note of the
// action, refreshed from the attribute every frame.
void Hud_CreateLog()
{
	DeleteAttribute(&ScreenLog, "");
	SetEventHandler("SetWindowSize", "Hud_WindowSize", 0);
	CreateEntity(&ScreenLog, "ILogAndActions");
	DelEventHandler("SetWindowSize", "Hud_WindowSize");
	ScreenLog.Log.left = Hud_Px(128.0);
	ScreenLog.Log.up = Hud_Px(12.0);
	ScreenLog.Log.width = Hud_Px(520.0);
	ScreenLog.Log.height = Hud_Px(120.0);
	ScreenLog.Log.font = "PDM_LOGBOOK_16";
	ScreenLog.Log.fontscale = 1.0;
	ScreenLog.Log.color = argb(0, 255, 245, 215);
	ScreenLog.Log.offsetString = Hud_Px(22.0);
	ScreenLog.Log.speed = 0.1;
	ScreenLog.Log.color_speed = 0.03;

	aref act;
	makearef(act, ScreenLog.ActiveActions);
	act.TextureName = "battle_interface\pdm\commands.tga";
	act.horzQ = sti(PdmHud.command_cols);
	act.vertQ = sti(PdmHud.command_rows);
	act.width = Hud_Px(64.0);
	act.height = Hud_Px(64.0);
	// at sea the navigator takes the top right corner, the icon goes under it
	float top = 16.0;
	if (hudSea) { top = HUD_NAV_FRAME + 24.0; }
	act.left = hudW - Hud_Px(80.0);
	act.top = Hud_Px(top);
	act.text1.font = "PDM_HUD_18";
	act.text1.scale = 1.0;
	act.text1.color = argb(255, 255, 230, 160);
	// the note ends at the right edge of the icon: "Выход в море" is wider than the icon (ours)
	act.text1.align = "right";
	act.text1.pos.x = hudW - Hud_Px(16.0);
	act.text1.pos.y = Hud_Px(top + 54.0);
	act.text1.text = "";
	act.text1.refreshable = 1;
	Hud_DefineAction("Nothing", -1);
	Hud_DefineAction("Land", sti(PdmHud.command.town));
	Hud_DefineAction("ToSea", sti(PdmHud.command.ocean));
	Hud_DefineAction("ToDoor", sti(PdmHud.command.town));
	Hud_DefineAction("Board", sti(PdmHud.command.board));

	LayerAddObject(EXECUTE, &ScreenLog, 100);
	LayerAddObject(REALIZE, &ScreenLog, 65535);
	SendMessage(&ScreenLog, "lll", LOG_AND_ACTIONS_INIT, 1, 1);
	hudAction = "";
	Hud_SetAction("Nothing", "");
	SetEventHandler("BI_FastCommand", "Hud_FastCommand", 0);
	// Space is the action on the land and at sea, as F2 of controls.ini (ours: one key for both)
	MapKey("BIFastCommand", HUD_KEY_ACTION);
}

void Hud_DefineAction(string name, int icon)
{
	ScreenLog.ActiveActions.(name).IconNum = icon;
}

void Hud_ReleaseLog()
{
	DelEventHandler("BI_FastCommand", "Hud_FastCommand");
	DeleteClass(&ScreenLog);
	hudAction = "";
}

void Hud_Log(string text)
{
	SendMessage(&ScreenLog, "lls", LOG_ADD_STRING, 0, text);
}

// the icon of the action and its note; the engine reads the icon again only for another name
void Hud_SetAction(string name, string note)
{
	ScreenLog.ActiveActions.text1.text = note;
	if (name == hudAction) { return; }
	hudAction = name;
	SendMessage(&ScreenLog, "ls", LOG_SET_ACTIVE_ACTION, name);
}

// Space: the action of the icon; deleting the log entity here is not safe, the actions post
void Hud_FastCommand()
{
	string action = GetEventData();
	if (hudSea)
	{
		if (action == "Land") { PostEvent("Sea_ToPort", 0); }
		if (action == "Board") { PostEvent("Board_Start", 0); }
		return;
	}
	Town_Action();
}

// ---------- on the land ----------

// Tab on the land: the places of the town (street, tavern, store, shipyard, townhall) and the sea, the hero goes
// there from wherever he stands (ours: Sea Dogs has no such menu, the hero walks to the doors). The menu of
// BATTLE_LAND_INTERFACE, with no faces of the party (no data.icons), in the place of the toolbar at sea
void Hud_LandStart()
{
	hudLand = true;
	DeleteAttribute(&LandInterface, "");
	LandInterface.Parameters.DoShowCommandos = 1;
	// the row bottom left, the top of its icons the top line of the list
	LandInterface.ManSign.iconoffset1 = "0," + (hudH - Hud_Px(HUD_PIC_MARGIN + HUD_PIC_W));
	LandInterface.ManSign.commandlistverticaloffset = 0;
	aref list;
	makearef(list, LandInterface.CommandList);
	list.CommandIconLeft = Hud_Px(HUD_PIC_MARGIN);
	list.CommandIconWidth = Hud_Px(64.0);
	list.CommandIconHeight = Hud_Px(64.0);
	list.CommandIconSpace = Hud_Px(HUD_PIC_STEP - HUD_PIC_W);
	list.CommandMaxIconQuantity = 8;
	list.CommandNoteFont = "PDM_HUD_18";
	list.CommandNoteColor = argb(255, 255, 230, 160);
	list.CommandNoteScale = 1.0;
	list.CommandNoteOffset = Hud_Pos(0.0, -56.0);
	list.ActiveIcon_Size = "0,0";
	LandInterface.CommandTextures.list.t0.name = "battle_interface\pdm\commands.tga";
	LandInterface.CommandTextures.list.t0.xsize = sti(PdmHud.command_cols);
	LandInterface.CommandTextures.list.t0.ysize = sti(PdmHud.command_rows);
	LandInterface.CommandTextures.CommandTexNum = 0;
	// the toolbar has no pictures of the buildings: the town of "На землю" for each, its note names the place
	string place;
	for (int i = 0; i < HUD_LAND_PLACES; i++)
	{
		place = hudLandPlaces[i];
		if (place == "sea") { Hud_LandCommand(place, "ocean"); }
		else { Hud_LandCommand(place, "town"); }
	}
	Hud_LandCommand("Cancel", "cancel");

	SetEventHandler("BI_SetPossibleCommands", "Hud_LandPossible", 0);
	SetEventHandler("BI_CommandEndChecking", "Hud_CommandEndChecking", 0);
	SetEventHandler("BI_LaunchCommand", "Hud_LandLaunch", 0);
	SetEventHandler("Hud_LandAuto", "Hud_LandAuto", 0);
	MapKey("LICommandsActivate", HUD_KEY_MENU);
	MapKey("BICommandsLeft", 37);
	MapKey("BICommandsRight", 39);
	MapKey("BICommandsConfirm", 13);
	MapKey("BICommandsCancel", 27);
	CreateEntity(&LandInterface, "battle_land_interface");
	LayerAddObject(EXECUTE, &LandInterface, 65534);
	LayerAddObject(REALIZE, &LandInterface, 65534);
}

void Hud_LandCommand(string name, string picture)
{
	int cell = sti(PdmHud.command.(picture));
	LandInterface.Commands.(name).enable = 0;
	LandInterface.Commands.(name).picNum = cell;
	LandInterface.Commands.(name).selPicNum = cell + 1;
	LandInterface.Commands.(name).texNum = 0;
	LandInterface.Commands.(name).event = name;
	LandInterface.Commands.(name).note = "";
	if (CheckAttribute(&PdmHud, "note." + name)) { LandInterface.Commands.(name).note = PdmHud.note.(name); }
}

void Hud_LandRelease()
{
	if (!hudLand) { return; }
	hudLand = false;
	DelEventHandler("BI_SetPossibleCommands", "Hud_LandPossible");
	DelEventHandler("BI_CommandEndChecking", "Hud_CommandEndChecking");
	DelEventHandler("BI_LaunchCommand", "Hud_LandLaunch");
	DelEventHandler("Hud_LandAuto", "Hud_LandAuto");
	DeleteClass(&LandInterface);
}

// every place of the town but the one the hero is in; the sea from a town of an island
void Hud_LandPossible()
{
	int chr = GetEventData();
	string place;
	for (int i = 0; i < HUD_LAND_PLACES; i++)
	{
		place = hudLandPlaces[i];
		LandInterface.Commands.(place).enable = Town_CanGo(place);
	}
	LandInterface.Commands.Cancel.enable = 1;
}

// "lsls": the location changes outside the frame of the interface, which it deletes
void Hud_LandLaunch()
{
	int chr = GetEventData();
	string name = GetEventData();
	Trace("PDM hud: land command " + name);
	if (name != "Cancel") { PostEvent("Town_HudGo", 0, "sl", name, townGen); }
}

// TOWN_AUTO=10: opens the menu and steps to the place as the arrows do, one step a while, then confirms it: the
// command goes through BI_LaunchCommand as from the keys
void Hud_LandAutoOpen(string place)
{
	hudLandAuto = place;
	hudLandAutoSteps = 0;
	string at;
	for (int i = 0; i < HUD_LAND_PLACES; i++)
	{
		at = hudLandPlaces[i];
		if (at == place) { break; }
		if (Town_CanGo(at)) { hudLandAutoSteps++; }
	}
	SendMessage(&LandInterface, "ls", MSG_BATTLE_LAND_MAKE_COMMAND, "activate");
	PostEvent("Hud_LandAuto", HUD_AUTO_LAND_MS);
}

void Hud_LandAuto()
{
	if (!hudLand) { return; }
	if (hudLandAutoSteps > 0)
	{
		hudLandAutoSteps--;
		SendMessage(&LandInterface, "ls", MSG_BATTLE_LAND_MAKE_COMMAND, "right");
		PostEvent("Hud_LandAuto", HUD_AUTO_LAND_MS);
		return;
	}
	Trace("PDM hud: land command " + hudLandAuto + " (autotest)");
	SendMessage(&LandInterface, "ls", MSG_BATTLE_LAND_MAKE_COMMAND, "confirm");
}

// ---------- at sea ----------

void Hud_Start()
{
	hudSea = true;
	hudMapFree = true;
	Hud_CreateLog();
	DeleteAttribute(&BattleInterface, "");
	BattleInterface.MainChrIndex = seaHero;
	BattleInterface.ShowNavigator = 1;
	BattleInterface.ShowCommands = 1;
	// no "battle on" border: the original has none, and without the attribute the engine draws a white
	// one fixed to 1024x768 while an enemy is near
	BattleInterface.battleborder.used = 0;

	// the pictures of the ships of the hero in a row from the bottom left, the enemy ships pressed to the bottom
	// right, as SQUAD_CONTROL.dll; the engine takes the centre of the picture of 64x64 (the top 50 rows drawn)
	int pictureY = hudH - Hud_Px(HUD_PIC_MARGIN + HUD_PIC_H - HUD_PIC_W / 2.0);
	aref icon;
	makearef(icon, BattleInterface.ShipIcon);
	Hud_ShipIcon(icon);
	string key;
	for (int i = 1; i <= 8; i++)
	{
		key = "iconoffset" + i;
		icon.(key) = Hud_Px(HUD_PIC_MARGIN + HUD_PIC_W / 2.0 + HUD_PIC_STEP * (i - 1)) + "," + pictureY;
	}
	aref enemy;
	makearef(enemy, BattleInterface.EnemyIcon);
	Hud_ShipIcon(enemy);
	enemy.rowright = (hudW - Hud_Px(HUD_PIC_MARGIN + HUD_PIC_W / 2.0)) + "," + pictureY;
	enemy.rowstep = Hud_Px(HUD_PIC_STEP);
	// the commands in a row from the right of the picture, level with it
	icon.commandlistverticaloffset = -Hud_Px(HUD_PIC_W / 2.0);

	Hud_Navigator();
	Hud_InfoPanel();
	Hud_ShowCorner();

	aref list;
	makearef(list, BattleInterface.CommandList);
	list.CommandIconLeft = Hud_Px(HUD_PIC_MARGIN + HUD_PIC_STEP);
	list.CommandIconWidth = Hud_Px(64.0);
	list.CommandIconHeight = Hud_Px(64.0);
	list.CommandIconSpace = Hud_Px(HUD_PIC_STEP - HUD_PIC_W);
	list.CommandMaxIconQuantity = 8;
	list.CommandNoteFont = "PDM_HUD_18";
	list.CommandNoteColor = argb(255, 255, 230, 160);
	list.CommandNoteScale = 1.0;
	// the note above the icon, where the original prints it over the row (ours: it follows the chosen icon)
	list.CommandNoteOffset = Hud_Pos(0.0, -56.0);
	// no frame round the chosen icon: the toolbar lights the icon itself (its _a picture)
	list.ActiveIcon_Size = "0,0";
	BattleInterface.CommandTextures.list.t0.name = "battle_interface\pdm\commands.tga";
	BattleInterface.CommandTextures.list.t0.xsize = sti(PdmHud.command_cols);
	BattleInterface.CommandTextures.list.t0.ysize = sti(PdmHud.command_rows);
	BattleInterface.CommandTextures.list.t1.name = "battle_interface\pdm\ships.tga";
	BattleInterface.CommandTextures.list.t1.xsize = sti(PdmHud.ship_cols);
	BattleInterface.CommandTextures.list.t1.ysize = sti(PdmHud.ship_cols);
	BattleInterface.CommandTextures.CommandTexNum = 0;
	// in the order of the toolbar; enable is set by Hud_PossibleCommands when the menu opens
	Hud_DefineCommand("board", "board", PdmHud.note.boarding);
	Hud_DefineCommand("sail_to", "chase", PdmHud.note.sail_to);
	Hud_DefineCommand("land", "town", PdmHud.note.land);
	Hud_DefineCommand("sea_map", "map2", PdmHud.note.sea_map);
	Hud_DefineCommand("skip_time", "time", PdmHud.note.ControlTurboMode);
	Hud_DefineCommand("Cancel", "cancel", "");

	SetEventHandler("BI_GetData", "Hud_GetData", 0);
	SetEventHandler("BI_SetPossibleCommands", "Hud_PossibleCommands", 0);
	SetEventHandler("BI_CommandEndChecking", "Hud_CommandEndChecking", 0);
	SetEventHandler("BI_LaunchCommand", "Hud_LaunchCommand", 0);
	SetEventHandler("BI_SetSeaState", "Hud_SeaState", 0);
	SetEventHandler("GetCurrentCharge", "Hud_GetCharge", 0);
	MapKey("Hud_Corner", HUD_KEY_CORNER);
	// TOWN_AUTO=7: "=" by itself, the enemies in the corner for the video
	SetEventHandler("Hud_AutoCorner", "Hud_AutoCorner", 0);
	if (TownAuto == 7) { PostEvent("Hud_AutoCorner", HUD_AUTO_CORNER_MS); }
	MapKey("BICommandsActivate", HUD_KEY_MENU);
	MapKey("BICommandsLeft", 37);
	MapKey("BICommandsRight", 39);
	MapKey("BICommandsUp", 38);
	MapKey("BICommandsDown", 40);
	MapKey("BICommandsConfirm", 13);
	MapKey("BICommandsCancel", 27);

	CreateEntity(&BattleInterface, "battle_interface");
	LayerAddObject(EXECUTE, &BattleInterface, 65534);
	LayerAddObject(REALIZE, &BattleInterface, 65534);
	// the panel reads the hull, the sails and the name from Ship of the character, their full values from the type
	SeaShips[seaHero].Ship.Name = PlayerShipCard.name;
	SeaShips[seaHero].Ship.HP = sti(SeaShipTypes[seaHero].HP);
	SeaShips[seaHero].Ship.SP = 100;
	SeaShipTypes[seaHero].SP = 100;
	SendMessage(&BattleInterface, "llaall", BI_IN_CREATE_SHIP, seaHero, &SeaShips[seaHero], &SeaShipTypes[seaHero], 1, BI_RELATION_FRIEND);
}

// the picture of a ship (its top 50 rows of 64, the rest keyed out); the bars above it, on the plate of
// back.tga (64x20): the sails at 5 from its top, the hull at 15, as on ship_status.tga
void Hud_ShipIcon(aref icon)
{
	icon.shiptexturename = "battle_interface\pdm\ships.tga";
	icon.xsize = sti(PdmHud.ship_cols);
	icon.ysize = sti(PdmHud.ship_cols);
	icon.shipoffset = "0,0";
	icon.shipiconsize = Hud_Pos(64.0, 64.0);
	icon.backtexturename = "battle_interface\pdm\back.tga";
	icon.backuv = "0,0,1,1";
	// the centre of the plate from the centre of the picture
	float plate = HUD_PIC_W / 2.0 + HUD_PLATE_UP - 10.0;
	icon.backoffset = Hud_Pos(0.0, -plate);
	icon.backiconsize = Hud_Pos(64.0, 20.0);
	icon.shipstatetexturename = "battle_interface\pdm\status.tga";
	// the bars empty from the right, as the original
	icon.shipstatehorizontal = 1;
	icon.shipspuv = "0.046875,0.359375,0.953125,0.421875";
	icon.shipspoffset = Hud_Pos(0.0, -plate - 5.0);
	icon.shipspiconsize = Hud_Pos(58.0, 4.0);
	icon.shiphpuv = "0.046875,0.515625,0.953125,0.578125";
	icon.shiphpoffset = Hud_Pos(0.0, -plate + 5.0);
	icon.shiphpiconsize = Hud_Pos(58.0, 4.0);
	// no class picture: the class is in the picture (tools/pdm_hud.py); no Ship.Crew.quantity, so no number of
	// the crew either
	icon.shipclasstexturename = "battle_interface\pdm\status.tga";
	icon.shipclassuv = "0,0,0,0";
	icon.shipclassoffset = "0,0";
	icon.shipclassiconsize = "0,0";
	icon.shipnamefontid = "PDM_LOGBOOK_16";
	icon.shipnamefontcolor = argb(255, 255, 230, 160);
	icon.shipnamefontscale = 1.0;
	// no name: the toolbar of the original has none, the engine always prints it, so out of the window
	icon.shipnamefontoffset = "0,-10000";
}

// the panel of the charges bottom right: the navigator draws ship_info as its picture of the charge (the row of
// the lit charge), the texts of TextInfo over it; Hud_SeaTick refreshes them
void Hud_InfoPanel()
{
	aref nav;
	makearef(nav, BattleInterface.navigation);
	int left = hudW - Hud_Px(HUD_PIC_MARGIN + HUD_INFO_W);
	int top = hudH - Hud_Px(HUD_PIC_MARGIN + HUD_PIC_H);
	// chargePos is the centre of the picture from the centre of the navigator
	int x = left + Hud_Px(HUD_INFO_W / 2.0) - (sti(nav.rightPos) - sti(nav.navigatorWidth) / 2);
	int y = top + Hud_Px(HUD_PIC_W / 2.0) - (sti(nav.topPos) + sti(nav.navigatorHeight) / 2);
	nav.chargeTexture = "battle_interface\pdm\info.tga";
	nav.chargeTextureGreed = "1," + sti(PdmHud.info_rows);
	nav.chargePos = x + "," + y;
	nav.chargePictureSize = Hud_Pos(HUD_INFO_W, HUD_PIC_W);
	hudCharge[0] = sti(PdmHud.info_empty);
	hudCharge[1] = 0;
	hudCharge[2] = 0;
	hudCharge[3] = 0;
	hudCharge[4] = 0;

	// FUN_10002320 of SQUAD_CONTROL.dll: info_bar at 15,6 of the panel, the numbers of the charges at 30, 92, 154
	// and 216 by 28, the loaded one black (ours: PDM_LOGBOOK_13 for arial 10)
	Hud_InfoText("bar", left + Hud_Px(15.0), top + Hud_Px(5.0), argb(255, 255, 255, 255));
	string key;
	for (int i = 0; i < HUD_CHARGES; i++)
	{
		x = left + Hud_Px(30.0 + 62.0 * i);
		key = "charge" + i;
		Hud_InfoText(key, x, top + Hud_Px(27.0), argb(255, 255, 255, 255));
		key = "loaded" + i;
		Hud_InfoText(key, x, top + Hud_Px(27.0), argb(255, 0, 0, 0));
	}
}

void Hud_InfoText(string name, int x, int y, int color)
{
	BattleInterface.TextInfo.(name).font = "PDM_LOGBOOK_13";
	BattleInterface.TextInfo.(name).scale = 1.0;
	BattleInterface.TextInfo.(name).color = color;
	BattleInterface.TextInfo.(name).shadow = 0;
	BattleInterface.TextInfo.(name).align = "left";
	BattleInterface.TextInfo.(name).pos.x = x;
	BattleInterface.TextInfo.(name).pos.y = y;
	BattleInterface.TextInfo.(name).text = "";
	BattleInterface.TextInfo.(name).refreshable = 1;
}

// "=": the charges, the enemies, nothing, as action 0x13 of SQUAD_CONTROL.dll
void Hud_Control(string control)
{
	if (control != "Hud_Corner" || !hudSea) { return; }
	hudCorner = (hudCorner + 1) % 3;
	Trace("PDM hud: corner " + hudCorner);
	Hud_ShowCorner();
	Hud_SeaTick();
}

void Hud_AutoCorner()
{
	Hud_Control("Hud_Corner");
}

void Hud_ShowCorner()
{
	BattleInterface.EnemyIcon.hide = hudCorner != HUD_CORNER_ENEMIES;
}

// the goods of the hold by the name: the cargo keeps them as n<the index in PdmGoods>
string Hud_GoodsKey(string goods)
{
	int n = GetAttributesNum(&PdmGoods);
	for (int i = 0; i < n; i++)
	{
		aref row = GetAttributeN(&PdmGoods, i);
		if (GetAttributeName(row) == goods) { return "n" + i; }
	}
	return "";
}

int Hud_Goods(string goods)
{
	aref cargo;
	makearef(cargo, PlayerShipCard.cargo);
	return Pdm_Count(cargo, Hud_GoodsKey(goods));
}

// the hold of the hero loses a shot of the loaded charge (ours: one a gun)
void Hud_SpendCharge()
{
	aref cargo;
	makearef(cargo, PlayerShipCard.cargo);
	string key = Hud_GoodsKey(hudChargeGoods[hudChargeLoaded]);
	int left = Pdm_Count(cargo, key) - 1;
	if (left < 0) { left = 0; }
	cargo.(key) = left;
}

int Hud_ChargeLeft()
{
	return Hud_Goods(hudChargeGoods[hudChargeLoaded]);
}

// "": [the row of the panel, the sails, the wind, the powder, the powder run out]; the empty row hides it
ref Hud_GetCharge()
{
	return &hudCharge;
}

// the texts of the panel of the charges, every tick of the sea
void Hud_InfoTick()
{
	bool shown = hudCorner == HUD_CORNER_INFO;
	if (shown) { hudCharge[0] = hudChargeLoaded; }
	else { hudCharge[0] = sti(PdmHud.info_empty); }
	string text = "";
	if (shown)
	{
		int hp = makeint(100.0 * stf(SeaShips[seaHero].Ship.HP) / stf(SeaShipTypes[seaHero].HP));
		text = PdmHud.note.info_bar;
		text = Hud_Format(text, makeint(stf(SeaShips[seaHero].Ship.SP)));
		text = Hud_Format(text, Pdm_Count(&PlayerShipCard, "crew"));
		text = Hud_Format(text, hp);
	}
	BattleInterface.TextInfo.bar.text = text;
	string key;
	string number;
	for (int i = 0; i < HUD_CHARGES; i++)
	{
		number = "";
		if (shown) { number = "" + Hud_Goods(hudChargeGoods[i]); }
		key = "charge" + i;
		BattleInterface.TextInfo.(key).text = "";
		if (i != hudChargeLoaded) { BattleInterface.TextInfo.(key).text = number; }
		key = "loaded" + i;
		BattleInterface.TextInfo.(key).text = "";
		if (i == hudChargeLoaded) { BattleInterface.TextInfo.(key).text = number; }
	}
}

// the first %d of the text by the number
string Hud_Format(string text, int n)
{
	int at = findSubStr(text, "%d", 0);
	if (at < 0) { return text; }
	string head = "";
	if (at > 0) { head = strcut(text, 0, at - 1); }
	string tail = "";
	if (at + 2 < strlen(text)) { tail = strcut(text, at + 2, strlen(text) - 1); }
	return head + n + tail;
}

// The navigator reads its attributes in Init. Its square textures are nav_scale times the brooch (tools/pdm_hud.py),
// the band of the guns round the brooch; the arcs of the sides are in degrees clockwise from the bow.
void Hud_Navigator()
{
	BattleInterface.MaxWind = 30.0;
	BattleInterface.MaxShipSpeed = 20.0;
	BattleInterface.ShipSpeedScaler = 1.0;
	aref nav;
	makearef(nav, BattleInterface.navigation);
	int size = Hud_Px(HUD_NAV_FRAME * stf(PdmHud.nav_scale));
	nav.navigatorWidth = size;
	nav.navigatorHeight = size;
	nav.rightPos = hudW - Hud_Px(8.0) - (size - Hud_Px(HUD_NAV_FRAME)) / 2;
	nav.topPos = Hud_Px(8.0) - (size - Hud_Px(HUD_NAV_FRAME)) / 2;
	nav.mapRadius = Hud_Px(HUD_NAV_MAP);
	nav.horizontRadius = 400;
	nav.minScale = 0.5;
	nav.maxScale = 2.0;
	nav.curScale = 1.0;
	nav.scaleStep = 0.02;
	nav.shipShowRadius = 6.0;
	nav.windWidth = Hud_Px(2.0 * HUD_NAV_MAP);
	nav.windHeight = Hud_Px(2.0 * HUD_NAV_MAP);
	// the colours of the needles of the original (object_*.tf): the enemy red, ours green
	nav.argbSeaColor = argb(255, 24, 58, 86);
	nav.argbFireZoneColor = argb(70, 255, 220, 150);
	nav.argbEnemyShipColor = argb(255, 230, 40, 30);
	nav.argbFrendShipColor = argb(255, 100, 250, 0);
	nav.argbNeutralShipColor = argb(255, 255, 250, 255);
	nav.argbDeadShipColor = argb(255, 60, 60, 60);
	nav.argbReadyCannonColor = argb(255, 230, 200, 110);
	nav.argbChargeCannonColor = argb(255, 200, 90, 40);
	nav.argbDamageCannonColor = argb(255, 90, 30, 20);
	// the reload of the sides (Cannons.Borts of battle.c), an arc of each side that fills as its guns load, clear
	// of the plate of the brooch (ours: NAVIGATOR.dll shows the guns on a panel of their own, guns_info); the bow
	// and the stern have no arcs
	nav.leftChargeBegAngle = 230;
	nav.leftChargeEndAngle = 310;
	nav.rightChargeBegAngle = 130;
	nav.rightChargeEndAngle = 50;
	nav.forwardChargeBegAngle = 0;
	nav.forwardChargeEndAngle = 0;
	nav.backwardChargeBegAngle = 0;
	nav.backwardChargeEndAngle = 0;
	nav.speedShowFont = "PDM_LOGBOOK_16";
	nav.fontScale = 1.0;
	nav.speedOutYOffset = Hud_Px(HUD_NAV_PLATE_Y - 8.0);
	nav.shipSpeedXOffset = Hud_Px(HUD_NAV_PLATE_X);
	nav.windSpeedXOffset = -Hud_Px(HUD_NAV_PLATE_X);
	nav.compasTexture = "battle_interface\pdm\nav_compass.tga";
	nav.cannonsTexture = "battle_interface\pdm\nav_cannons.tga";
	nav.emptyTexture = "battle_interface\pdm\nav_frame.tga";
	nav.windTexture = "battle_interface\pdm\nav_wind.tga";
	// no icons of the sails and the wind: the original has none on the navigator; the picture of the charge is the
	// panel of the charges (Hud_InfoPanel)
	nav.sailstatePictureSize = "0,0";
	nav.windPictureSize = "0,0";
}

void Hud_DefineCommand(string name, string picture, string note)
{
	int cell = sti(PdmHud.command.(picture));
	BattleInterface.Commands.(name).enable = 0;
	BattleInterface.Commands.(name).picNum = cell;
	BattleInterface.Commands.(name).selPicNum = cell + 1;
	BattleInterface.Commands.(name).texNum = 0;
	BattleInterface.Commands.(name).event = name;
	BattleInterface.Commands.(name).note = note;
}

void Hud_Release()
{
	if (!hudSea) { return; }
	hudSea = false;
	DelEventHandler("BI_GetData", "Hud_GetData");
	DelEventHandler("BI_SetPossibleCommands", "Hud_PossibleCommands");
	DelEventHandler("BI_CommandEndChecking", "Hud_CommandEndChecking");
	DelEventHandler("BI_LaunchCommand", "Hud_LaunchCommand");
	DelEventHandler("BI_SetSeaState", "Hud_SeaState");
	DelEventHandler("GetCurrentCharge", "Hud_GetCharge");
	DelEventHandler("Hud_AutoCorner", "Hud_AutoCorner");
	DeleteClass(&BattleInterface);
	Hud_ReleaseLog();
}

// the menu of the commands is open: Escape closes it and does not quit
bool Hud_MenuOpen()
{
	if (hudLand) { return CheckAttribute(&LandInterface, "ComState") && sti(LandInterface.ComState) != 0; }
	return hudSea && CheckAttribute(&BattleInterface, "ComState") && sti(BattleInterface.ComState) != 0;
}

// "ll" BIDT_SHIPPICTURE, the character: the picture of his ship (icon of its record of Ships.idf) with the flag of
// his nation
ref Hud_GetData()
{
	int what = GetEventData();
	int chr = GetEventData();
	string type = SeaShipTypes[chr].Name;
	string icon = "unk";
	if (CheckAttribute(&PdmShipTypes, type + ".icon")) { icon = PdmShipTypes.(type).icon; }
	if (!CheckAttribute(&PdmHud, "icon." + icon)) { icon = "unk"; }
	string nation = Hud_NationOf(sti(SeaShips[chr].nation));
	int cell = (sti(PdmHud.icon.(icon)) * sti(PdmHud.flag_count) + sti(PdmHud.flag.(nation))) * 2;
	hudShipPicture[0] = cell;
	hudShipPicture[1] = cell + 1;
	hudShipPicture[2] = 1;
	hudShipPicture[3] = 0;
	return &hudShipPicture;
}

// the flag of the nation (an index of WORLDS\nations.idf) by its name
string Hud_NationOf(int n)
{
	aref nation = GetAttributeN(&PdmNations, n);
	string name = nation.name;
	if (CheckAttribute(&PdmHud, "flag." + name)) { return name; }
	return "pirate";
}

void Hud_PossibleCommands()
{
	int chr = GetEventData();
	BattleInterface.Commands.board.enable = Board_Can();
	BattleInterface.Commands.sail_to.enable = Battle_CanSailTo();
	BattleInterface.Commands.land.enable = Hud_CanLand();
	BattleInterface.Commands.sea_map.enable = hudMapFree;
	BattleInterface.Commands.skip_time.enable = 1;
	BattleInterface.Commands.Cancel.enable = 1;
}

// the ship is at the harbour of a town: no farther off than where it appears leaving the town
bool Hud_CanLand()
{
	if (Sea_PortTown() == "") { return false; }
	return Sea_NearHarbour(Sea_HeroHarbourDistance());
}

// every command is done at once, none asks for a target
int Hud_CommandEndChecking()
{
	string name = GetEventData();
	return 0;
}

// "lsls" the character, the command, the target, the locator; the scene is changed outside the frame
void Hud_LaunchCommand()
{
	int chr = GetEventData();
	string name = GetEventData();
	Trace("PDM hud: command " + name);
	if (name == "land") { PostEvent("Sea_ToPort", 0); }
	if (name == "sea_map") { PostEvent("Sea_ToMap", 0); }
	if (name == "board") { PostEvent("Board_Start", 0); }
	if (name == "sail_to") { PostEvent("Battle_SailTo", 0); }
	if (name == "skip_time") { Sea_NextTimeScale(); }
}

// "lllllll" sail to, land troops, map, attack, defend, reload, the reload target: every frame
void Hud_SeaState()
{
	int sailTo = GetEventData();
	int landTroops = GetEventData();
	int map = GetEventData();
	hudMapFree = map != 0;
}

// every tick of the sea: the possible action of Space
void Hud_SeaTick()
{
	if (!hudSea) { return; }
	Hud_InfoTick();
	if (Board_Can()) { Hud_SetAction("Board", PdmHud.note.boarding); }
	else if (Hud_CanLand()) { Hud_SetAction("Land", PdmHud.note.land); }
	else { Hud_SetAction("Nothing", ""); }
}
