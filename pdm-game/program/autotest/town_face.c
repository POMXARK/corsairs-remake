// TOWN_AUTO=40: the close-up of the hero's face, for checking the eyelid blink. The camera point is fixed
// first, 0.9 m from the hero along the world Z at eye level; the hero turns to that point
// (MSG_CHARACTER_TURNBYPOINT, it is atan2(dx, dz) inside: he looks along +(sin ay, cos ay)), and when the
// turn is over the camera goes there and keeps looking at him (MSG_CAMERA_TOPOS, the same message as the
// wind check of town.c). The test ends itself after TOWN_FACE_MS, nothing is pressed.
// TOWN_AUTO=41 is the same for the NPC number TOWN_FACE_NPC (the eyes.ini heads, not hero_head).
// Driving the hero and the camera from a script: .claude/skills/storm-land-scenario-control/SKILL.md
#define TOWN_FACE_MS 10000
#define TOWN_FACE_TURN_MS 1500
#define TOWN_FACE_NPC 3

float townFaceX;
float townFaceY;
float townFaceZ;
int townFaceNpc = -1;

void TownFace_Start()
{
	float hx, hy, hz;
	townFaceNpc = -1;
	if (TownAuto == 41)
	{
		townFaceNpc = TOWN_FACE_NPC;
		if (townFaceNpc >= townNpcCount) { townFaceNpc = 0; }
		TownNpc[townFaceNpc].wander.hold = 1;
		SendMessage(&TownNpc[townFaceNpc], "ls", MSG_NPCHARACTER_SETTASK, "Stay");
		SendMessage(&TownNpc[townFaceNpc], "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz);
	}
	else { SendMessage(&TownHero, "leee", MSG_CHARACTER_GETPOS, &hx, &hy, &hz); }
	townFaceX = hx;
	townFaceY = hy + 1.8;
	townFaceZ = hz + 0.9;
	Trace("PDM face: the hero turns to the camera point " + townFaceX + ", " + townFaceZ);
	if (townFaceNpc >= 0) { SendMessage(&TownNpc[townFaceNpc], "lfff", MSG_CHARACTER_TURNBYPOINT, townFaceX, townFaceY, townFaceZ); }
	else { SendMessage(&TownHero, "lfff", MSG_CHARACTER_TURNBYPOINT, townFaceX, townFaceY, townFaceZ); }
	PostEvent("TownFace_Camera", TOWN_FACE_TURN_MS);
	PostEvent("TownFace_End", TOWN_FACE_MS);
}

void TownFace_Camera()
{
	if (townFaceNpc >= 0) { SendMessage(&TownCamera, "li", MSG_CAMERA_SETTARGET, &TownNpc[townFaceNpc]); }
	else { SendMessage(&TownCamera, "li", MSG_CAMERA_SETTARGET, &TownHero); }
	SendMessage(&TownCamera, "lfffl", MSG_CAMERA_TOPOS, townFaceX, townFaceY, townFaceZ, 1);
	Trace("PDM face: camera in front of the hero");
}

void TownFace_End()
{
	Trace("PDM face: autotest done, camera in front of the hero");
	ExitProgram();
}
