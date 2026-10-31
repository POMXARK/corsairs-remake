// The movies of the original (RESOURCE/DESC/*.ani, tools/pdm_cutscene.py -> data\pdm_cutscenes.c): a playlist is
// played scene by scene, a scene is the still models, the camera keys (a key a frame, 15 frames a second) and
// the sounds at their frames. Space or Enter skips the movie, as Shift did in the original (Esc is the menu of the game).

#define CUT_FRAME_MS 66.0
#define CUT_MAX_MODELS 16
#define CUT_PI 3.14159265
// the movies stand a little above the sea of the game: the water of the original is lower than y = 0 of the models
// the models and the camera of a movie sit this much above the sea of the game (a scene may set its own: .lift)
#define CUT_LIFT 0.8
#define CUT_FLIP_MS 70.0
#define CUT_HIT_TILT 0.9
// the keys put the keel of a hull on y = 0, the waterline of the movie: the hull sinks a little under the wave
#define CUT_DRAFT 0.0
#define CUT_FADER_OUT 33000
#define CUT_FADER_IN 33001
#define MSG_MODEL_LOAD_ANI 20501
#define MSG_MODEL_PLAY_ACTION 20601
#define MSG_MODEL_SET_POSITION 20506
#define MSG_MODEL_SET_TECHNIQUE 20510
#define MSG_SEA_GET_HEIGHT 50202
#define CUT_PS_CREATE 10000
#define FADER_PICTURE0 33004
#define CUT_FAR_RAISE 0.3

int cutModelCount = 0;
// the flags wave as a flipbook: models of the cloth in cutFlipCount shapes, from the model cutFlipFirst, one of them shows at a time
int cutFlipFirst = 0;
int cutFlipCount = 0;
int cutFlipShown = -1;
object CutModel[48];
object CutCamera;
object CutWeather;
object CutMoon;
object CutFader;
object CutParticles;
bool cutFx = false;
bool cutFading = false;
string cutPlaylist = "";
string cutScene = "";
string cutAfter = "";
int cutIndex = 0;
bool cutKeepSea = false;
string cutSeaKind = "";
int cutFirst = 0; // the piece of the scene that the playlist plays: from this frame
int cutLast = 0; // to this one
int cutBino = -1; // the frame where the view through a spyglass starts (-1: none)
bool cutBinoOn = false;
object CutBinoView;
float cutTime = 0.0;
float cutLift = CUT_LIFT;
// a turn of the room about the axis of the view (radians): the room goes up against the horizon of the sea (.tilt)
float cutTilt = 0.0;
float cutDraft = CUT_DRAFT;
float cutDt = 16.0;
bool cutWaveInit = false;
float cutWaveM = 0.0;
float cutWaveC = 0.0;
bool cutSmoothInit = false; // the low-pass of the camera on the keys: x y z and three angles
float cutSm[6];
int cutLastKey = -1;
float cutWaveM1 = 0.0; // the first stage of the filters (the second stage is cutWaveM / cutWaveC)
float cutWaveC1 = 0.0;
int cutFar = -1; // the model of the far ships (it stands at its own origin), -1 when the scene has none
float cutFarX = 0.0;
float cutFarZ = 0.0;
float cutCamLift = 0.0; // the lift of the camera: the same shift as the models, when the actors stand on the decks
int cutSound = 0;
bool cutRunning = false;
bool cutSea = false;
bool cutLight = false;
aref cutCam;

void Cut_Start(string playlist, string after)
{
	cutPlaylist = playlist;
	cutAfter = after;
	cutIndex = 0;
	// "intro:3" starts the playlist from its fourth movie (to look at one scene of a long list)
	int colon = findSubStr(playlist, ":", 0);
	if (colon > 0)
	{
		cutPlaylist = strcut(playlist, 0, colon - 1);
		cutIndex = sti(strcut(playlist, colon + 1, strlen(playlist) - 1));
	}
	cutRunning = true;
	MapKey("Cut_Skip", 32);
	MapKey("Cut_Skip", 13);
	Render.BackColor = argb(255, 120, 160, 200);
	// the camera of the movie: the script puts it where the key is every frame (engine free_camera.cpp, Scripted)
	CutCamera.Scripted = 1;
	CutCamera.position.x = 0.0; CutCamera.position.y = 0.0; CutCamera.position.z = 0.0;
	CutCamera.angle.x = 0.0; CutCamera.angle.y = 0.0; CutCamera.angle.z = 0.0;
	CreateEntity(&CutCamera, "FREE_CAMERA");
	SendMessage(&Scene, "si", "SetActiveCamera", &CutCamera);
	SetEventHandler("frame", "Cut_Frame", 0);
	SetEventHandler("Control Activation", "Cut_Control", 0);
	if (!Cut_Next()) { Cut_End(); }
}

// the next scene of the playlist that was converted; the end of the list ends the movie
bool Cut_Next()
{
	string child;
	string scene;
	while (cutIndex < sti(PdmCut.(cutPlaylist).count))
	{
		child = "c" + cutIndex;
		cutIndex++;
		scene = PdmCut.(cutPlaylist).(child).scene;
		PdmCut_Load(scene);
		if (CheckAttribute(&PdmCut, scene + ".frames"))
		{
			cutFirst = 0;
			cutLast = sti(PdmCut.(scene).frames);
			if (CheckAttribute(&PdmCut, cutPlaylist + "." + child + ".last"))
			{
				cutFirst = sti(PdmCut.(cutPlaylist).(child).first);
				cutLast = sti(PdmCut.(cutPlaylist).(child).last);
			}
			// the next piece of the same sea and sky keeps the sea of the last one: making a sea is the pause between the pieces
			cutKeepSea = cutSea && stf(PdmCut.(scene).sea) > 0.0 && Cut_SeaKind(scene) == cutSeaKind;
			Cut_Unload();
			cutKeepSea = false;
			Cut_Load(scene);
			return true;
		}
		Trace("PDM cutscene: skipped " + scene);
	}
	Cut_Unload();
	return false;
}

// what the sea and the sky of a scene are made of: the pieces of one kind share one sea
string Cut_SeaKind(string scene)
{
	string kind = "day";
	if (CheckAttribute(&PdmCut, scene + ".sky")) { kind = PdmCut.(scene).sky; }
	if (CheckAttribute(&PdmCut, scene + ".night") && stf(PdmCut.(scene).night) > 0.0) { kind = kind + "-night"; }
	return kind;
}

void Cut_Load(string scene)
{
	cutScene = scene;
	cutTime = cutFirst * CUT_FRAME_MS;
	cutBino = -1;
	if (CheckAttribute(&PdmCut, scene + ".bino")) { cutBino = sti(PdmCut.(scene).bino); }
	cutSound = 0;
	cutLift = CUT_LIFT;
	cutTilt = 0.0;
	cutDraft = CUT_DRAFT;
	cutCamLift = cutLift;
	cutWaveInit = false;
	cutSmoothInit = false;
	cutLastKey = -1;
	// a cabin: past the edge of the map is the dark wood of the table, not the blue of the sky
	Render.BackColor = argb(255, 120, 160, 200);
	if (CheckAttribute(&PdmCut, scene + ".room")) { Render.BackColor = argb(255, 45, 28, 15); }
	if (CheckAttribute(&PdmCut, scene + ".draft")) { cutDraft = stf(PdmCut.(scene).draft); }
	if (CheckAttribute(&PdmCut, scene + ".lift")) { cutLift = stf(PdmCut.(scene).lift); }
	if (CheckAttribute(&PdmCut, scene + ".tilt")) { cutTilt = stf(PdmCut.(scene).tilt); }
	cutModelCount = sti(PdmCut.(scene).models.count);
	cutFlipCount = 0;
	cutFlipShown = -1;
	if (CheckAttribute(&PdmCut, scene + ".flip.count"))
	{
		cutFlipFirst = sti(PdmCut.(scene).flip.first);
		cutFlipCount = sti(PdmCut.(scene).flip.count);
	}
	for (int i = 0; i < cutModelCount; i++)
	{
		string name = "m" + i;
		CreateEntity(&CutModel[i], "modelr");
		SendMessage(&CutModel[i], "ls", MSG_MODEL_LOAD_GEO, PdmCut.(scene).models.(name));
		SendMessage(&CutModel[i], "ls", MSG_MODEL_SET_TECHNIQUE, "DLightModel");
		LayerAddObject(EXECUTE, &CutModel[i], 10);
		LayerAddObject(REALIZE, &CutModel[i], 10);
		SendMessage(&CutModel[i], "lffffffffffff", MSG_MODEL_SET_POSITION, 0.0, cutLift, 0.0, cos(cutTilt), sin(cutTilt), 0.0, -sin(cutTilt), cos(cutTilt), 0.0, 0.0, 0.0, 1.0);
	}
	// the animated parts (NPCs, ships under way): one skinned model, every object of it a bone that moves by the keys
	if (CheckAttribute(&PdmCut, scene + ".actors"))
	{
		int a = cutModelCount;
		cutModelCount++;
		CreateEntity(&CutModel[a], "modelr");
		SendMessage(&CutModel[a], "ls", MSG_MODEL_LOAD_GEO, PdmCut.(scene).actors);
		SendMessage(&CutModel[a], "ls", MSG_MODEL_LOAD_ANI, PdmCut.(scene).anim);
		SendMessage(&CutModel[a], "ls", MSG_MODEL_SET_TECHNIQUE, "DLightModel");
		LayerAddObject(EXECUTE, &CutModel[a], 10);
		LayerAddObject(REALIZE, &CutModel[a], 10);
		SendMessage(&CutModel[a], "lffffffffffff", MSG_MODEL_SET_POSITION, 0.0, cutLift, 0.0, cos(cutTilt), sin(cutTilt), 0.0, -sin(cutTilt), cos(cutTilt), 0.0, 0.0, 0.0, 1.0);
		SendMessage(&CutModel[a], "lls", MSG_MODEL_PLAY_ACTION, 0, Cut_Action());
	}
	// the ships far from the origin: a model that stands at its own origin
	cutFar = -1;
	if (CheckAttribute(&PdmCut, scene + ".far.model"))
	{
		int fa = cutModelCount;
		cutModelCount++;
		cutFar = fa;
		cutFarX = stf(PdmCut.(scene).far.x);
		cutFarZ = stf(PdmCut.(scene).far.z);
		CreateEntity(&CutModel[fa], "modelr");
		SendMessage(&CutModel[fa], "ls", MSG_MODEL_LOAD_GEO, PdmCut.(scene).far.model);
		SendMessage(&CutModel[fa], "ls", MSG_MODEL_LOAD_ANI, PdmCut.(scene).far.anim);
		SendMessage(&CutModel[fa], "ls", MSG_MODEL_SET_TECHNIQUE, "DLightModel");
		LayerAddObject(EXECUTE, &CutModel[fa], 10);
		LayerAddObject(REALIZE, &CutModel[fa], 10);
		SendMessage(&CutModel[fa], "lffffffffffff", MSG_MODEL_SET_POSITION, cutFarX, cutLift, cutFarZ, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0);
		SendMessage(&CutModel[fa], "lls", MSG_MODEL_PLAY_ACTION, 0, Cut_Action());
	}
	// the sea and the sky of the shot (the weather of the game), the lens of the movie
	if (stf(PdmCut.(scene).sea) > 0.0)
	{
		seaSkyDir = "day";
		string skyKind = "day";
		if (CheckAttribute(&PdmCut, scene + ".sky")) { skyKind = PdmCut.(scene).sky; }
		if (skyKind == "overcast") { seaSkyDir = "storm"; } else { seaSkyDir = skyKind; }
		if (!cutSea) { Sea_CreateWorld(); }
		cutSea = true;
		cutSeaKind = Cut_SeaKind(scene);
		if (CheckAttribute(&PdmCut, scene + ".sun"))
		{
			// the light of the shot as the movie sets it
			Weather.Sun.Color = sti(PdmCut.(scene).sun);
			// the ambient light of the record: its colour x its intensity
			Weather.Sun.Ambient = sti(PdmCut.(scene).ambient);
			if (CheckAttribute(&PdmCut, scene + ".amp"))
			{
				// the swell of the movie (sea_amplitude of the record), far lower than the swell of the game
				Sea.Sea2.Amp1 = stf(PdmCut.(scene).amp);
				Sea.Sea2.Amp2 = stf(PdmCut.(scene).amp) * 0.3;
				// a calm water: no foam, a smooth surface, a slow swell and a slow shimmer of the bump map
				Sea.Sea2.FoamEnable = 0;
				Sea.Sea2.BumpScale = 0.01;
				// a mirror-calm water (a harbour): the smallest ripple
				if (stf(PdmCut.(scene).amp) < 0.005) { Sea.Sea2.BumpScale = 0.004; }
				Sea.Sea2.AnimSpeed1 = 0.8;
				Sea.Sea2.AnimSpeed2 = 1.6;
				Sea.Sea2.BumpSpeed = 0.15;
			}
			Weather.Sun.HeightAngle = stf(PdmCut.(scene).height);
			Weather.Sun.AzimuthAngle = stf(PdmCut.(scene).azimuth);
			Weather.isDone = "";
			Weather.Fog.Color = sti(PdmCut.(scene).fog);
			Sea.Fog.Color = sti(PdmCut.(scene).fog);
			if (skyKind == "storm") { Sea.Sea2.WaterColor = argb(0, 25, 60, 75); }
			if (skyKind == "sunset") { Sea.Sea2.WaterColor = argb(0, 60, 95, 85); }
		}
		if (CheckAttribute(&PdmCut, scene + ".water")) { Sea.Sea2.WaterColor = argb(0, sti(PdmCut.(scene).water.r), sti(PdmCut.(scene).water.g), sti(PdmCut.(scene).water.b)); }
		if (skyKind == "overcast")
		{
			// a grey sky over a dark teal sea
			Sky.Color = argb(0, 190, 200, 215);
			Sea.Sea2.WaterColor = argb(0, 10, 55, 75);
			Sea.Sea2.SkyColor = argb(0, 150, 165, 180);
		}
		if (skyKind == "haze")
		{
			// a pale yellow haze over a teal sea: the far hulls melt into the sky
			Sea.Sea2.WaterColor = argb(0, 70, 150, 165);
			Sea.Sea2.SkyColor = argb(0, 240, 240, 190);
			// the sun and the sky light the wood to a pale cream
			Weather.Sun.Ambient = argb(0, 215, 215, 190);
			Weather.Sun.Color = argb(0, 255, 250, 215);
			Weather.Fog.Enable = 1;
			Weather.Fog.Density = 0.012;
			Weather.Fog.Color = argb(0, 232, 235, 185);
			Sky.Color = argb(0, 245, 245, 195);
			Sea.Fog.Color = argb(0, 232, 235, 185);
			Weather.isDone = "";
		}
		if (CheckAttribute(&PdmCut, scene + ".night") && stf(PdmCut.(scene).night) > 0.0)
		{
			// the night: dark sky and water
			Sky.Color = argb(0, 70, 80, 120);
			Sea.Sea2.WaterColor = argb(0, 8, 20, 35);
			Sea.Sea2.SkyColor = argb(0, 50, 70, 110);
			Weather.Sun.Ambient = argb(0, 50, 60, 85);
			Weather.Sun.Color = argb(0, 90, 105, 150);
			// a darker night (.dark, the share of the light left): a black sky with grey clouds, a dim teal sea
			if (CheckAttribute(&PdmCut, scene + ".dark"))
			{
				float dk = stf(PdmCut.(scene).dark);
				Sky.Color = argb(0, makeint(55.0 * dk), makeint(60.0 * dk), makeint(75.0 * dk));
				Sea.Sea2.WaterColor = argb(0, makeint(22.0 * dk), makeint(50.0 * dk), makeint(55.0 * dk));
				Sea.Sea2.SkyColor = argb(0, makeint(45.0 * dk), makeint(55.0 * dk), makeint(65.0 * dk));
				Weather.Sun.Ambient = argb(0, makeint(70.0 * dk), makeint(78.0 * dk), makeint(100.0 * dk));
				Weather.Fog.Color = argb(0, makeint(40.0 * dk), makeint(48.0 * dk), makeint(58.0 * dk));
				Sea.Fog.Color = argb(0, makeint(40.0 * dk), makeint(48.0 * dk), makeint(58.0 * dk));
			}
			// the azimuth of the record counts from the view of the movie, the one of the engine from the x axis
			Weather.Sun.AzimuthAngle = stf(PdmCut.(scene).azimuth) - 1.5708;
			Weather.isDone = "";
			// the moon disc (the sun glow in its moon mode)
			CreateEntity(&CutMoon, "SunGlow");
			LayerAddObject(17, &CutMoon, -1);
			CutMoon.Moon = 1;
			CutMoon.Glow.Dist = 3500.0;
			CutMoon.Glow.MoonSize = 150.0;
			CutMoon.Glow.Size = 150.0;
			CutMoon.Glow.Color = argb(0, 235, 240, 255);
			CutMoon.Glow.MoonTexture = "weather\moon.tga.tx";
			CutMoon.Glow.SunTexture = "weather\moon.tga.tx";
			CutMoon.Glow.TechniqueZ = "moon_z";
			CutMoon.Glow.TechniqueNoZ = "sunglow_noz";
			CutMoon.isDone = true;
		}
	}
	else
	{
		CreateEntity(&CutWeather, "weather");
		CutWeather.Fog.Enable = 0;
		CutWeather.Sun.Color = argb(0, 255, 236, 200);
		CutWeather.Sun.Ambient = argb(0, 140, 140, 150);
		CutWeather.Sun.HeightAngle = 0.8;
		CutWeather.Sun.AzimuthAngle = 0.6;
		CutWeather.isDone = "";
		cutLight = true;
	}
	// the effects the keys do not hold (the guns of a ship, the hits): the particles of the game at a point of the screen
	cutFx = CheckAttribute(&PdmCut, scene + ".fx.count");
	if (cutFx) { CreateEntity(&CutParticles, "particles"); }
	if (CheckAttribute(&PdmCut, scene + ".fov")) { CutCamera.Perspective = stf(PdmCut.(scene).fov) * 0.017453; }
	Cut_Skipped(scene);
	Cut_Camera(cutFirst);
	Trace("PDM cutscene: " + scene + ", " + PdmCut.(scene).frames + " frames");
}

// what happened before the piece that starts at cutFirst does not happen again: the fades, the sounds
void Cut_Skipped(string scene)
{
	int n = sti(PdmCut.(scene).fades.count);
	for (int d = 0; d < n; d++)
	{
		string fname = "f" + d;
		if (stf(PdmCut.(scene).fades.(fname).frame) < cutFirst) { PdmCut.(scene).fades.(fname).played = 1; }
	}
	n = sti(PdmCut.(scene).sounds.count);
	for (int k = 0; k < n; k++)
	{
		string sname = "s" + k;
		if (stf(PdmCut.(scene).sounds.(sname).frame) < cutFirst) { PdmCut.(scene).sounds.(sname).played = 1; }
	}
}

void Cut_Unload()
{
	for (int u = 0; u < cutModelCount; u++) { DeleteClass(&CutModel[u]); }
	cutModelCount = 0;
	cutScene = "";
	if (cutLight) { DeleteClass(&CutWeather); cutLight = false; }
	if (isEntity(&CutMoon)) { DeleteClass(&CutMoon); }
	if (cutFx) { DeleteClass(&CutParticles); cutFx = false; }
	if (cutBinoOn) { DeleteClass(&CutBinoView); cutBinoOn = false; }
	if (cutSea && !cutKeepSea)
	{
		DelEventHandler("WhrCalcFogColor", "Sea_FogColor");
		DeleteClass(&Sea);
		DeleteClass(&Sky);
		DeleteClass(&Weather);
		cutSea = false;
	}
}

void Cut_Frame()
{
	if (!cutRunning || cutScene == "") { return; }
	// a scene that was just loaded stalls one frame: that stall must not eat the first frames of the movie
	float dt = GetDeltaTime();
	if (dt > 100.0) { dt = 100.0; }
	cutTime = cutTime + dt;
	cutDt = dt;
	float frame = cutTime / CUT_FRAME_MS;
	if (frame >= cutLast)
	{
		if (!Cut_Next()) { Cut_End(); }
		return;
	}
	Cut_Camera(frame);
	Cut_Ride();
	Cut_Flip();
	// the spyglass: the black bars and the dark edges of its view over the picture
	if (cutBino >= 0 && frame >= cutBino && !cutBinoOn)
	{
		cutBinoOn = true;
		CreateEntity(&CutBinoView, "fader");
		SendMessage(&CutBinoView, "ls", FADER_PICTURE0, "cinema\binocular.tga.tx");
		SendMessage(&CutBinoView, "lfl", CUT_FADER_OUT, 0.0, 0);
	}
	// the fades: from black (seconds < 0) or to black
	int fades = sti(PdmCut.(cutScene).fades.count);
	for (int d = 0; d < fades; d++)
	{
		string fname = "f" + d;
		if (stf(PdmCut.(cutScene).fades.(fname).frame) <= frame && !CheckAttribute(&PdmCut, cutScene + ".fades." + fname + ".played"))
		{
			PdmCut.(cutScene).fades.(fname).played = 1;
			float seconds = stf(PdmCut.(cutScene).fades.(fname).seconds);
			if (!cutFading) { CreateEntity(&CutFader, "fader"); cutFading = true; }
			if (seconds < 0.0) { SendMessage(&CutFader, "lfl", CUT_FADER_IN, -seconds, 0); }
			else { SendMessage(&CutFader, "lfl", CUT_FADER_OUT, seconds, 0); }
		}
	}
	if (cutFx) { Cut_Effects(frame); }
	// the sounds whose frame has come
	int count = sti(PdmCut.(cutScene).sounds.count);
	for (int n = 0; n < count; n++)
	{
		string sname = "s" + n;
		if (stf(PdmCut.(cutScene).sounds.(sname).frame) <= frame && !CheckAttribute(&PdmCut, cutScene + ".sounds." + sname + ".played"))
		{
			PdmCut.(cutScene).sounds.(sname).played = 1;
			SendMessage(&Sound, "lslllllllf", MSG_SOUND_PLAY, PdmCut.(cutScene).sounds.(sname).file, PCM_STEREO, VOLUME_FX, false, false, false, 0, 0, 1.0);
		}
	}
}

// the action of the animation of the scene: from the start, or from the frame where its second piece begins
string Cut_Action()
{
	if (cutFirst > 0) { return "late"; }
	return "play";
}

// the effects of the scene (.fx.fN: frame, kind of the particle system, point x y z of the movie as the camera keys)
void Cut_Effects(float frame)
{
	int count = sti(PdmCut.(cutScene).fx.count);
	for (int e = 0; e < count; e++)
	{
		string ename = "f" + e;
		if (stf(PdmCut.(cutScene).fx.(ename).frame) > frame || CheckAttribute(&PdmCut, cutScene + ".fx." + ename + ".played")) { continue; }
		PdmCut.(cutScene).fx.(ename).played = 1;
		float px = stf(PdmCut.(cutScene).fx.(ename).x);
		float py = stf(PdmCut.(cutScene).fx.(ename).y) + cutCamLift;
		float pz = stf(PdmCut.(cutScene).fx.(ename).z);
		// a hit throws the pieces out of the hull towards the shooter (to the left of the frame), not straight up
		float tilt = 0.0;
		if (PdmCut.(cutScene).fx.(ename).kind == "shothit") { tilt = CUT_HIT_TILT; }
		SendMessage(&CutParticles, "lsffffffl", CUT_PS_CREATE, PdmCut.(cutScene).fx.(ename).kind, px, py, pz, 0.0, 0.0, tilt, 0);
	}
}

// the flags: of the shapes of the cloth only one stands in the scene (the rest are hidden far below), the shape follows the time
void Cut_Flip()
{
	if (cutFlipCount == 0) { return; }
	int shape = makeint(cutTime / CUT_FLIP_MS) % cutFlipCount;
	float level = cutLift;
	if (cutSea) { level = cutWaveM; }
	if (shape != cutFlipShown || cutSea)
	{
		for (int f = 0; f < cutFlipCount; f++)
		{
			float y = level;
			if (f != shape) { y = level - 1000.0; }
			SendMessage(&CutModel[cutFlipFirst + f], "lffffffffffff", MSG_MODEL_SET_POSITION, 0.0, y, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0);
		}
		cutFlipShown = shape;
	}
}

// the hulls ride the waves of the engine: the keys hold the models still on the waterline, so the models follow
// the height of the sea under the origin of the scene (the camera stays on its keys)
void Cut_Ride()
{
	if (!cutSea) { return; }
	SendMessage(&Sea, "lff", MSG_SEA_GET_HEIGHT, 0.0, 0.0);
	float wave = stf(Sea.Probe.Y) + cutDraft;
	// the camera stays over the swell under it (the keys of the original hold it a hand over a calm sea)
	SendMessage(&Sea, "lff", MSG_SEA_GET_HEIGHT, stf(CutCamera.position.x), stf(CutCamera.position.z));
	float camWave = stf(Sea.Probe.Y);
	if (camWave < wave) { camWave = wave; }
	// the surface of the sea has small quick ripples that a rigid hull and a camera on a tripod do not follow:
	// a low-pass filter (about a third of a second) leaves the long swell and drops the twitching
	if (!cutWaveInit) { cutWaveInit = true; cutWaveM = wave; cutWaveC = camWave; cutWaveM1 = wave; cutWaveC1 = camWave; }
	// two stages in a row (about 2 s each) give a smooth curve without kinks
	float k = cutDt / (cutDt + 2000.0);
	cutWaveM1 = cutWaveM1 + (wave - cutWaveM1) * k;
	cutWaveC1 = cutWaveC1 + (camWave - cutWaveC1) * k;
	cutWaveM = cutWaveM + (cutWaveM1 - cutWaveM) * k;
	cutWaveC = cutWaveC + (cutWaveC1 - cutWaveC) * k;
	CutCamera.position.y = stf(CutCamera.position.y) - cutCamLift + cutWaveC;
	cutCamLift = cutWaveC;
	for (int i = 0; i < cutModelCount; i++)
	{
		if (cutFlipCount > 0 && i >= cutFlipFirst && i < cutFlipFirst + cutFlipCount) { continue; }
		float fx = 0.0;
		float fz = 0.0;
		float fy = cutWaveM;
		// the ships far away stand higher on the water: the sea of the spyglass is calm and the hulls show over it
		if (i == cutFar) { fx = cutFarX; fz = cutFarZ; fy = cutWaveM - cutDraft + CUT_FAR_RAISE; }
		if (i == cutFar) { SendMessage(&CutModel[i], "lffffffffffff", MSG_MODEL_SET_POSITION, fx, fy, fz, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0); }
		else { SendMessage(&CutModel[i], "lffffffffffff", MSG_MODEL_SET_POSITION, fx, fy, fz, cos(cutTilt), sin(cutTilt), 0.0, -sin(cutTilt), cos(cutTilt), 0.0, 0.0, 0.0, 1.0); }
	}
}

// a cut of the movie (the camera jumps between two keys): hold the old shot, do not sweep through the space between
// (a move of the camera is under half a unit and 0.15 radian a key, a cut is over 2 units or 0.7 radian)
bool Cut_IsJump(string a, string b)
{
	float turn = Cut_AngleDiff(stf(PdmCut.(cutScene).cam.(a).rx), stf(PdmCut.(cutScene).cam.(b).rx));
	float turnY = Cut_AngleDiff(stf(PdmCut.(cutScene).cam.(a).ry), stf(PdmCut.(cutScene).cam.(b).ry));
	if (turnY > turn) { turn = turnY; }
	float move = Cut_Abs(stf(PdmCut.(cutScene).cam.(b).x) - stf(PdmCut.(cutScene).cam.(a).x)) + Cut_Abs(stf(PdmCut.(cutScene).cam.(b).y) - stf(PdmCut.(cutScene).cam.(a).y)) + Cut_Abs(stf(PdmCut.(cutScene).cam.(b).z) - stf(PdmCut.(cutScene).cam.(a).z));
	if (move > 1.0 || turn > 0.5) { return true; }
	return false;
}

// the keys are a frame apart (15 a second): a line between them kinks at every key and the picture twitches,
// so the camera goes along a smooth curve (Catmull-Rom) through the keys, and stays a line over a cut
void Cut_Camera(float frame)
{
	int count = sti(PdmCut.(cutScene).cam.count);
	if (count == 0) { return; }
	int key = makeint(frame);
	float t = frame - key;
	if (key >= count - 1) { key = count - 1; t = 0.0; }
	int next = key + 1;
	if (t == 0.0) { next = key; }
	int before = key - 1;
	if (before < 0) { before = 0; }
	int after = next + 1;
	if (after > count - 1) { after = count - 1; }
	string a = "k" + key;
	string b = "k" + next;
	string pa = "k" + before;
	string pb = "k" + after;
	if (Cut_IsJump(a, b)) { t = 0.0; next = key; b = a; }
	if (Cut_IsJump(pa, a)) { pa = a; }
	if (Cut_IsJump(b, pb)) { pb = b; }
	CutCamera.position.x = Cut_Spline(stf(PdmCut.(cutScene).cam.(pa).x), stf(PdmCut.(cutScene).cam.(a).x), stf(PdmCut.(cutScene).cam.(b).x), stf(PdmCut.(cutScene).cam.(pb).x), t);
	CutCamera.position.y = Cut_Spline(stf(PdmCut.(cutScene).cam.(pa).y), stf(PdmCut.(cutScene).cam.(a).y), stf(PdmCut.(cutScene).cam.(b).y), stf(PdmCut.(cutScene).cam.(pb).y), t) + cutCamLift;
	CutCamera.position.z = Cut_Spline(stf(PdmCut.(cutScene).cam.(pa).z), stf(PdmCut.(cutScene).cam.(a).z), stf(PdmCut.(cutScene).cam.(b).z), stf(PdmCut.(cutScene).cam.(pb).z), t);
	CutCamera.angle.x = Cut_SplineAngle(stf(PdmCut.(cutScene).cam.(pa).rx), stf(PdmCut.(cutScene).cam.(a).rx), stf(PdmCut.(cutScene).cam.(b).rx), stf(PdmCut.(cutScene).cam.(pb).rx), t);
	CutCamera.angle.y = Cut_SplineAngle(stf(PdmCut.(cutScene).cam.(pa).ry), stf(PdmCut.(cutScene).cam.(a).ry), stf(PdmCut.(cutScene).cam.(b).ry), stf(PdmCut.(cutScene).cam.(pb).ry), t);
	CutCamera.angle.z = Cut_SplineAngle(stf(PdmCut.(cutScene).cam.(pa).rz), stf(PdmCut.(cutScene).cam.(a).rz), stf(PdmCut.(cutScene).cam.(b).rz), stf(PdmCut.(cutScene).cam.(pb).rz), t);
	// a cut between the keys: the filter takes the new shot at once
	if (key != cutLastKey)
	{
		if (key > 0 && Cut_IsJump("k" + (key - 1), a)) { cutSmoothInit = false; }
		cutLastKey = key;
	}
	Cut_Smooth();
}

// a low-pass (about 0.5 s) over the camera: the keys of a hand-held shot twitch a little, the filter leaves the sweep;
// a cut of the movie is taken at once (Cut_Camera drops the filter on the keys that jump); the lag of a fast sweep is not a cut
void Cut_Smooth()
{
	float v[6];
	v[0] = stf(CutCamera.position.x); v[1] = stf(CutCamera.position.z);
	v[2] = stf(CutCamera.angle.x); v[3] = stf(CutCamera.angle.y); v[4] = stf(CutCamera.angle.z);
	if (!cutSmoothInit) { cutSmoothInit = true; for (int i = 0; i < 5; i++) { cutSm[i] = v[i]; } }
	float step = cutDt;
	if (step > 100.0) { step = 100.0; } // a hitch of a frame (loading) must not throw the camera ahead
	float k = step / (step + 500.0);
	cutSm[0] = cutSm[0] + (v[0] - cutSm[0]) * k;
	cutSm[1] = cutSm[1] + (v[1] - cutSm[1]) * k;
	cutSm[2] = cutSm[2] + Cut_Wrap(v[2] - cutSm[2]) * k;
	cutSm[3] = cutSm[3] + Cut_Wrap(v[3] - cutSm[3]) * k;
	cutSm[4] = cutSm[4] + Cut_Wrap(v[4] - cutSm[4]) * k;
	CutCamera.position.x = cutSm[0]; CutCamera.position.z = cutSm[1];
	CutCamera.angle.x = cutSm[2]; CutCamera.angle.y = cutSm[3]; CutCamera.angle.z = cutSm[4];
}

float Cut_Spline(float p0, float p1, float p2, float p3, float t)
{
	float t2 = t * t;
	float t3 = t2 * t;
	return 0.5 * (2.0 * p1 + (p2 - p0) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2 + (3.0 * p1 - p0 - 3.0 * p2 + p3) * t3);
}

// the same on angles: every neighbour turned the short way from the key before it
float Cut_SplineAngle(float p0, float p1, float p2, float p3, float t)
{
	float b = p1 + Cut_Wrap(p2 - p1);
	return Cut_Spline(p1 + Cut_Wrap(p0 - p1), p1, b, b + Cut_Wrap(p3 - p2), t);
}

float Cut_Wrap(float d)
{
	while (d > CUT_PI) { d = d - 2.0 * CUT_PI; }
	while (d < -CUT_PI) { d = d + 2.0 * CUT_PI; }
	return d;
}

float Cut_AngleDiff(float a, float b)
{
	float d = b - a;
	while (d > CUT_PI) { d = d - 2.0 * CUT_PI; }
	while (d < -CUT_PI) { d = d + 2.0 * CUT_PI; }
	return Cut_Abs(d);
}

// the angles of the keys go round the circle: turn the short way, not through the whole turn
float Cut_LerpAngle(float a, float b, float t)
{
	float d = b - a;
	while (d > CUT_PI) { d = d - 2.0 * CUT_PI; }
	while (d < -CUT_PI) { d = d + 2.0 * CUT_PI; }
	return a + d * t;
}

float Cut_Abs(float v)
{
	if (v < 0.0) { return -v; }
	return v;
}

float Cut_Lerp(float a, float b, float t)
{
	return a + (b - a) * t;
}

void Cut_Control()
{
	string control = GetEventData();
	if (!cutRunning || control != "Cut_Skip") { return; }
	Trace("PDM cutscene: skipped");
	Cut_End();
}

void Cut_End()
{
	if (!cutRunning) { return; }
	cutRunning = false;
	Cut_Unload();
	DeleteClass(&CutCamera);
	if (cutFading) { DeleteClass(&CutFader); cutFading = false; }
	DelEventHandler("frame", "Cut_Frame");
	DelEventHandler("Control Activation", "Cut_Control");
	Trace("PDM cutscene: " + cutPlaylist + " done");
	if (cutAfter == "exit") { ExitProgram(); return; }
	if (cutAfter == "menu") { if (TownAuto == 43) { ExitProgram(); } else { Menu_Start(); } return; }
	Pdm_NewGame();
	string island = PlayerCard.address.island;
	Town_Start(PdmIslands.(island).town, "sea");
}
