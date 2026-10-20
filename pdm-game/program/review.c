// The fleet review: every ship type of WORLDS\Ships.idf on the water side by side, in the order of the
// table (from the battleships of class 1 to the boat), the camera going from one to the next.
// A check of tools/pdm_ship.py on all hulls; started by SCENE=review run.sh.

#define REVIEW_SPACING 90.0
#define REVIEW_SHOW_MS 4000
int reviewCurrent = 0;
float reviewAngle = 1.2;

void Review_Start()
{
	Sea_MapShipKeys();
	Sea_CreateWorld();
	// the ships stand still with the sails set, so the line stays a line
	seaSpeedScale = 0.0;
	int n = GetAttributesNum(&PdmShipTypes);
	aref type;
	string key;
	for (int i = 0; i < n; i++)
	{
		type = GetAttributeN(&PdmShipTypes, i);
		key = GetAttributeName(type);
		// the forts are parts of the islands
		if (key == "fort") { continue; }
		object card;
		card.id = type.type;
		// the four nations of nations.idf in turn, to show their flags
		card.nation = seaShipCount % 4;
		Sea_AddShip(&card, key, REVIEW_SPACING * seaShipCount, 0.0, 0.0);
	}
	Trace("PDM: review of " + seaShipCount + " ship types");
	Sea_CreateCamera(0);
	SetEventHandler("Review_Next", "Review_Next", 0);
	SetEventHandler("Sea_Tick", "Review_Tick", 0);
	PostEvent("Sea_Tick", SEA_TICK_MS);
	PostEvent("Review_Next", REVIEW_SHOW_MS);
	Review_Show();
}

void Review_Show()
{
	SendMessage(&SeaCameras, "lia", AI_CAMERAS_SET_CAMERA, &ShipCamera, &SeaShips[reviewCurrent]);
	Trace("PDM: review " + reviewCurrent + " " + SeaShipTypes[reviewCurrent].Name + " (" + SeaShips[reviewCurrent].id + ")");
}

void Review_Next()
{
	reviewCurrent = reviewCurrent + 1;
	if (reviewCurrent >= seaShipCount)
	{
		Trace("PDM: review done");
		ExitProgram();
		return;
	}
	Review_Show();
	PostEvent("Review_Next", REVIEW_SHOW_MS);
}

void Review_Tick()
{
	reviewAngle = reviewAngle + 0.01;
	ShipCamera.AngleY = reviewAngle;
	PostEvent("Sea_Tick", SEA_TICK_MS);
}
