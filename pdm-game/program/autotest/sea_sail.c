// TOWN_AUTO=15, SCENE=sea: the autotest of "Plbть к" at sea, driving the real bottom hub menu,
// the bar whose buttons also give access to the world map (hud.c defines its commands: board,
// sail_to, land, sea_map, skip_time, cancel). No event is posted to Sea_SailTo here: the test
// sends the same message the keyboard controls feed the hub with, MSG_BATTLE_LAND_MAKE_COMMAND
// ("s", shared\battle_interface\msg_control.h 46105), whose steps "activate"/"left"/"right"/
// "confirm" the fork added to i_battle.cpp ProcessMessage mirror the land hub of battle_land.cpp:
// activate opens the bar (BIShipIcon::SetActive), "right" walks the selection to the sail-to
// button and "confirm" runs BIShipIcon::ExecuteCommand(Command_confirm) -> ExecuteConfirm
// (battle_command.cpp) -> BI_LaunchCommand, which our Hud_LaunchCommand turns into Sea_SailTo.
// The same confirm makes BI_CommandEndChecking return SEA_SAIL_TO_MODE, so the target-icon bar
// (FillIcons in battle_ship_command.cpp) draws a ship, the town, the fort and the land of the
// island near the hero: the witnesses of evntCheckEnableLocator and the capture prove it.
void SeaSailAuto_Press()
{
	// open the bottom hub, exactly as the player's key for BICommands... does
	Trace("PDM sailto autotest: hub activate");
	SendMessage(&BattleInterface, "ls", 46105, "activate");
	PostEvent("SeaSailAuto_Step3", 600);
}


void SeaSailAuto_Step3()
{
	// press the button: ExecuteConfirm launches the command through the engine's own
	// BI_LaunchCommand, and the returned mode puts the target-icon bar on the screen
	Trace("PDM sailto autotest: hub confirm, the press of Plbть к");
	// first confirm: BI_CommandEndChecking returns SEA_SAIL_TO_MODE, so ExecuteConfirm
	// only rewrites the bar into the target-icon bar of battle_ship_command.cpp:FillIcons
	// (ships, the town, the fort, the land in reach); one right picks the next icon there
	SendMessage(&BattleInterface, "ls", 46105, "confirm");
	PostEvent("SeaSailAuto_Step4", 700);
	PostEvent("SeaSailAuto_Step5", 1400);
}


void SeaSailAuto_Step4()
{
	// step along the target-icon bar, its first icon is already selected by
	// battle_command.cpp:Update (the mode changed, so m_nSelectedCommandIndex resets to 0)
	Trace("PDM sailto autotest: hub step right in the target bar");
	SendMessage(&BattleInterface, "ls", 46105, "right");
}

void SeaSailAuto_Step5()
{
	// the second confirm launches the selected icon: the entry has no command name,
	// endCode stays 0 and ExecuteConfirm posts BI_LaunchCommand (battle_command.cpp)
	Trace("PDM sailto autotest: hub confirm of the target icon");
	SendMessage(&BattleInterface, "ls", 46105, "confirm");
	PostEvent("Sea_SailToCheck", 700);
	PostEvent("SeaSailAuto_End", 2200);
}
void SeaSailAuto_End()
{
	// all witnesses above are the engine's own traces (Hud_LaunchCommand, Hud_LocatorCheck,
	// Sea_SailToCheck); leave the sea back to the world map as the run's end
	Trace("PDM: autotest done, sail to at sea");
	Sea_ToMap();
}
