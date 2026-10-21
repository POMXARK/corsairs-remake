// The toolbar of the original (SQUAD_CONTROL.dll on TEXTURES/toolbar), tools/pdm_hud.py converts its pictures
// into battle_interface\pdm and its notes into data\pdm_hud.c (PdmHud).
//
// At sea BATTLE_INTERFACE draws the picture of the ship of the hero top left, with the flag of his nation and the
// bars of the hull and the sails. Tab opens the commands to the right of it: arrows pick, Enter gives, Escape
// closes, as in the original. The commands are the transitions: "На землю" at the harbour of a town, "Карта" (the
// world map), "Ускорение" (the time). On the land ILogAndActions shows the icon of the exit the hero stands
// in with the name of the place it leads to; Space goes through it (the original "Действие").
// Top right at sea the navigator (NAVIGATOR.dll): the map of the island round the ship in the brooch, the letters
// of the compass and the wind arrow turned with the heading, the speeds of the ship and the wind on its plate.
// F2 at sea does the possible action: lands at the harbour (ours: the original lands by the menu only).

// shared/battle_interface/msg_control.h and log_and_action.h
#define BI_IN_CREATE_SHIP 46011
#define BI_RELATION_FRIEND 1
#define LOG_ADD_STRING 45020
#define LOG_SET_ACTIVE_ACTION 45021
#define LOG_AND_ACTIONS_INIT 45022
// the keys of the original (controls.ini): Tab the icons, arrows and Enter in them, F2 the possible action,
// Space the action on the land
#define HUD_KEY_MENU 9
#define HUD_KEY_FAST 113
#define HUD_KEY_ACTION 32
// the layout of the original is for 800x600 (ours: everything scales with the height of the window)
#define HUD_BASE_H 600.0
// the navigator: the size of its brooch (the frame of 128 of the original), its map inside the ring of the frame
// (radius 58), the speeds on the plate below it (at 56 under the centre, 42 to the sides), all in pixels of 800x600
#define HUD_NAV_FRAME 128.0
#define HUD_NAV_MAP 58.0
#define HUD_NAV_PLATE_Y 56.0
#define HUD_NAV_PLATE_X 42.0
// TOWN_AUTO: the autotest stands in an exit this long before it goes through, so its icon is on the video
#define HUD_AUTO_EXIT_MS 1500

object BattleInterface;
object ScreenLog;
int hudW = 800;
int hudH = 600;
// what BI_GetData returns: the cell of the picture, its lit cell, the texture of the list, dead
int hudShipPicture[4];
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
	act.text1.font = "PDM_LOGBOOK_18";
	act.text1.scale = 1.0;
	act.text1.color = argb(255, 255, 230, 160);
	act.text1.pos.x = hudW - Hud_Px(48.0);
	act.text1.pos.y = Hud_Px(top + 54.0);
	act.text1.text = "";
	act.text1.refreshable = 1;
	Hud_DefineAction("Nothing", -1);
	Hud_DefineAction("Land", sti(PdmHud.command.town));
	Hud_DefineAction("ToSea", sti(PdmHud.command.ocean));
	Hud_DefineAction("ToDoor", sti(PdmHud.command.town));

	LayerAddObject(EXECUTE, &ScreenLog, 100);
	LayerAddObject(REALIZE, &ScreenLog, 65535);
	SendMessage(&ScreenLog, "lll", LOG_AND_ACTIONS_INIT, 1, 1);
	hudAction = "";
	Hud_SetAction("Nothing", "");
	SetEventHandler("BI_FastCommand", "Hud_FastCommand", 0);
	MapKey("BIFastCommand", HUD_KEY_FAST);
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

// F2 (Space on the land): the action of the icon; deleting the log entity here is not safe, the actions post
void Hud_FastCommand()
{
	string action = GetEventData();
	if (hudSea)
	{
		if (action == "Land") { PostEvent("Sea_ToPort", 0); }
		return;
	}
	Town_Action();
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

	// the picture of the ship top left (its top 50 rows of 64, the rest keyed out); the bars right under it,
	// on the plate of back.tga (64x20): the sails at 5 from its top, the hull at 15, as on ship_status.tga
	aref icon;
	makearef(icon, BattleInterface.ShipIcon);
	icon.iconoffset1 = Hud_Pos(48.0, 48.0);
	icon.shiptexturename = "battle_interface\pdm\ships.tga";
	icon.xsize = sti(PdmHud.ship_cols);
	icon.ysize = sti(PdmHud.ship_cols);
	icon.shipoffset = "0,0";
	icon.shipiconsize = Hud_Pos(64.0, 64.0);
	icon.backtexturename = "battle_interface\pdm\back.tga";
	icon.backuv = "0,0,1,1";
	icon.backoffset = Hud_Pos(0.0, 28.0);
	icon.backiconsize = Hud_Pos(64.0, 20.0);
	icon.shipstatetexturename = "battle_interface\pdm\status.tga";
	// the bars empty from the right, as the original
	icon.shipstatehorizontal = 1;
	icon.shipspuv = "0.046875,0.359375,0.953125,0.421875";
	icon.shipspoffset = Hud_Pos(0.0, 23.0);
	icon.shipspiconsize = Hud_Pos(58.0, 4.0);
	icon.shiphpuv = "0.046875,0.515625,0.953125,0.578125";
	icon.shiphpoffset = Hud_Pos(0.0, 33.0);
	icon.shiphpiconsize = Hud_Pos(58.0, 4.0);
	// no class picture: the original has none; no Ship.Crew.quantity, so no number of the crew either
	icon.shipclasstexturename = "battle_interface\pdm\status.tga";
	icon.shipclassuv = "0,0,0,0";
	icon.shipclassoffset = "0,0";
	icon.shipclassiconsize = "0,0";
	icon.shipnamefontid = "PDM_LOGBOOK_16";
	icon.shipnamefontcolor = argb(255, 255, 230, 160);
	icon.shipnamefontscale = 1.0;
	icon.shipnamefontoffset = Hud_Pos(0.0, 40.0);
	// the commands in a row from the right of the picture, level with it
	icon.commandlistverticaloffset = Hud_Px(-32.0);

	Hud_Navigator();

	aref list;
	makearef(list, BattleInterface.CommandList);
	list.CommandIconLeft = Hud_Px(96.0);
	list.CommandIconWidth = Hud_Px(64.0);
	list.CommandIconHeight = Hud_Px(64.0);
	list.CommandIconSpace = Hud_Px(4.0);
	list.CommandMaxIconQuantity = 8;
	list.CommandNoteFont = "PDM_LOGBOOK_18";
	list.CommandNoteColor = argb(255, 255, 230, 160);
	list.CommandNoteScale = 1.0;
	list.CommandNoteOffset = Hud_Pos(0.0, 30.0);
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
	Hud_DefineCommand("land", "town", PdmHud.note.land);
	Hud_DefineCommand("sea_map", "map2", PdmHud.note.sea_map);
	Hud_DefineCommand("skip_time", "time", PdmHud.note.ControlTurboMode);
	Hud_DefineCommand("Cancel", "cancel", "");

	SetEventHandler("BI_GetData", "Hud_GetData", 0);
	SetEventHandler("BI_SetPossibleCommands", "Hud_PossibleCommands", 0);
	SetEventHandler("BI_CommandEndChecking", "Hud_CommandEndChecking", 0);
	SetEventHandler("BI_LaunchCommand", "Hud_LaunchCommand", 0);
	SetEventHandler("BI_SetSeaState", "Hud_SeaState", 0);
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
	// no arcs of the sides yet: the ship has no Cannons.Borts (П4), and without them the engine draws the arcs from
	// the angle 0, a closed ring. With the guns: left 230..310, right 130..50, clear of the plate of the brooch
	nav.leftChargeBegAngle = 0;
	nav.leftChargeEndAngle = 0;
	nav.rightChargeBegAngle = 0;
	nav.rightChargeEndAngle = 0;
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
	// no icons of the charge, the sails and the wind: the original has none on the navigator
	nav.chargePictureSize = "0,0";
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
	DeleteClass(&BattleInterface);
	Hud_ReleaseLog();
}

// the menu of the commands is open: Escape closes it and does not quit
bool Hud_MenuOpen()
{
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

// every tick of the sea: the possible action of F2
void Hud_SeaTick()
{
	if (!hudSea) { return; }
	if (Hud_CanLand()) { Hud_SetAction("Land", PdmHud.note.land); }
	else { Hud_SetAction("Nothing", ""); }
}
