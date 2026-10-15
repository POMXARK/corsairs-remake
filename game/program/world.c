// The world the scenes share: the scene entity, weather, sky, sea, the on-screen log, particles and
// sound. It is made once, with the first new game, and stays while the port (port.c) and the sea
// battle (sea.c) are made and deleted around it. The scenes live in layers EXECUTE/REALIZE and the
// sea reflection ones; going to the menu only freezes them.

#define EXECUTE 0
#define REALIZE 1
// shared/layers.h: mirrored into the sea reflection (sky in the first, ships in the second)
#define SEA_REFLECTION 15
#define SEA_REFLECTION2 16
// shared/layers.h: what the cannon balls and cameras trace against
#define SAILS_TRACE 19

// "lsffffffl": name, position, angles, lifetime in ms (0 burns until the system ends itself)
#define PS_CREATE 10000

// "sllllll[fffff]": file or alias, type, volume type, only cache, looped, cached, fade in ms, then
// for 3D the position and the distances
#define MSG_SOUND_PLAY 77003
// "ll": id, fade out ms
#define MSG_SOUND_STOP 77004
#define MSG_SOUND_SCHEME_RESET 77013
#define MSG_SOUND_SCHEME_SET 77014
#define MSG_SOUND_SET_MASTER_VOLUME 77021
#define PCM_STEREO 0
#define PCM_3D 1
#define MP3_STEREO 2
#define VOLUME_FX 1
#define VOLUME_MUSIC 2

#define LOG_ADD_STRING 45020
#define LOG_AND_ACTIONS_INIT 45022

object Render;
object Scene;
object Weather;
object Sky;
object Sea;
object ScreenLog;
object Particles;
object Sound;

// the state of the game: the sea battle writes the result, Tom in the port pays for the wins
#define START_GOLD 100
#define RAVEN_REWARD 500
// every next «Ворон» is tougher and the governor pays this much more for him, up to RAVEN_MAX_LEVEL
#define RAVEN_LEVEL_REWARD 250
#define RAVEN_MAX_LEVEL 4
int gold = START_GOLD;
int wins = 0;
int unpaidWins = 0;
int unpaidGold = 0;
// "", "win" or "loss": how the last battle ended
string lastBattle = "";
int metTom = 0;
// the boarding (deck.c): the crew of «Ворон» when it starts, the prizes Tom has not paid for yet and
// how the last one ended ("", "won", "lost") for his words
int boardEnemyCrew = 0;
int unpaidPrizes = 0;
string lastBoarding = "";

// The brig between the battles: the hull in percent, the sailors and the balls in the hold. The sea
// battle starts from them and writes them back; Tom sells repairs, sailors and balls for gold.
#define SHIP_HULL 100
#define SHIP_CREW 96
#define START_BALLS 60
#define START_KNIPPELS 12
#define START_GRAPES 12
// the charges: round shot breaks the hull, chain shot tears the sails, grape shot kills the crew
#define CHARGE_BALLS 0
#define CHARGE_KNIPPELS 1
#define CHARGE_GRAPES 2
int shipHull = SHIP_HULL;
int shipCrew = SHIP_CREW;
int shipBalls = START_BALLS;
int shipKnippels = START_KNIPPELS;
int shipGrapes = START_GRAPES;
int shipCharge = CHARGE_BALLS;

void Game_ResetState()
{
	gold = START_GOLD;
	wins = 0;
	unpaidWins = 0;
	unpaidGold = 0;
	lastBattle = "";
	metTom = 0;
	boardEnemyCrew = 0;
	unpaidPrizes = 0;
	lastBoarding = "";
	shipHull = SHIP_HULL;
	shipCrew = SHIP_CREW;
	shipBalls = START_BALLS;
	shipKnippels = START_KNIPPELS;
	shipGrapes = START_GRAPES;
	shipCharge = CHARGE_BALLS;
}

// the charges in the hold by type, and their names as AIBalls knows them and as the log says them
int Charge_Count(int charge)
{
	if (charge == CHARGE_KNIPPELS) { return shipKnippels; }
	if (charge == CHARGE_GRAPES) { return shipGrapes; }
	return shipBalls;
}

void Charge_Add(int charge, int count)
{
	if (charge == CHARGE_KNIPPELS) { shipKnippels = shipKnippels + count; return; }
	if (charge == CHARGE_GRAPES) { shipGrapes = shipGrapes + count; return; }
	shipBalls = shipBalls + count;
}

string Charge_Type(int charge)
{
	if (charge == CHARGE_KNIPPELS) { return "Knippels"; }
	if (charge == CHARGE_GRAPES) { return "Grapes"; }
	return "Balls";
}

string Charge_Name(int charge)
{
	if (charge == CHARGE_KNIPPELS) { return "книппели"; }
	if (charge == CHARGE_GRAPES) { return "картечь"; }
	return "ядра";
}

// how many «Воронов» are sunk already: the next one is built and manned better
int Raven_Level()
{
	int level = wins + unpaidWins;
	if (level > RAVEN_MAX_LEVEL) { level = RAVEN_MAX_LEVEL; }
	return level;
}

int Raven_Bounty()
{
	int level = Raven_Level();
	return RAVEN_REWARD + level * RAVEN_LEVEL_REWARD;
}

int worldCreated = 0;
int wavesSound = 0;
float fogHeight = 150.0;

void World_Create()
{
	if (worldCreated) { return; }
	worldCreated = 1;
	Weather.Wind.Angle = 0.0;
	Weather.Wind.Speed = 12.0;

	Render.BackColor = argb(255, 0, 0, 0);
	CreateEntity(&Scene, "Scene");
	LayerAddObject(EXECUTE, &Scene, 0);
	CreateWeather();
	CreateLog();
	CreateEntity(&Particles, "particles");
	CreateEntity(&Sound, "Sound");
	SendMessage(&Sound, "lfff", MSG_SOUND_SET_MASTER_VOLUME, 1.0, 0.5, 1.0);
	Trace("WORLD: created");
}

void World_Freeze(int freeze)
{
	LayerFreeze(EXECUTE, freeze);
	LayerFreeze(REALIZE, freeze);
	LayerFreeze(SEA_REFLECTION, freeze);
	LayerFreeze(SEA_REFLECTION2, freeze);
}

// Music is streamed and has two slots: the new track fades in while the one playing fades out.
void World_Music(string track)
{
	// file, type, volume type, only cache, looped, cached, fade in ms, pause between loops, volume
	SendMessage(&Sound, "lslllllllf", MSG_SOUND_PLAY, track, MP3_STEREO, VOLUME_MUSIC, false, true, false, 3000, 0, 1.0);
}

// The surf and the gulls of the sea_day section of sound_scheme.ini, in the port. The surf is looped
// here: the service keeps no id of a looped scheme channel to stop it by.
void World_Ambient(int on)
{
	if (on)
	{
		SendMessage(&Sound, "ls", MSG_SOUND_SCHEME_SET, "sea_day");
		if (wavesSound == 0)
		{
			wavesSound = SendMessage(&Sound, "lsllllll", MSG_SOUND_PLAY, "demo\waves.wav", PCM_STEREO, VOLUME_FX,
				false, true, false, 2000);
		}
		return;
	}
	SendMessage(&Sound, "l", MSG_SOUND_SCHEME_RESET);
	if (wavesSound != 0)
	{
		SendMessage(&Sound, "lll", MSG_SOUND_STOP, wavesSound, 2000);
		wavesSound = 0;
	}
}

// The sea calms in the harbour, where the deck is 1.5 m over the water, and rises in the open sea.
// The entity applies Amp1/Amp2 only when MaxSeaHeight is written, scaling them down to fit it: a
// new amplitude alone keeps the old waves.
void World_Waves(float amp1, float amp2, float maxHeight)
{
	Sea.Sea2.Amp1 = amp1;
	Sea.Sea2.Amp2 = amp2;
	Sea.MaxSeaHeight = maxHeight;
}

// The world map (map.c) draws its own sea and sky: the world's leave the layers while it is shown.
void World_ShowSea(int show)
{
	if (show)
	{
		LayerAddObject(EXECUTE, &Sky, 2);
		LayerAddObject(REALIZE, &Sky, 3);
		LayerAddObject(SEA_REFLECTION, &Sky, 1);
		LayerAddObject(EXECUTE, &Sea, 4);
		LayerAddObject(REALIZE, &Sea, 65530);
		return;
	}
	LayerDelObject(EXECUTE, &Sky);
	LayerDelObject(REALIZE, &Sky);
	LayerDelObject(SEA_REFLECTION, &Sky);
	LayerDelObject(EXECUTE, &Sea);
	LayerDelObject(REALIZE, &Sea);
}

void CreateWeather()
{
	CreateEntity(&Weather, "weather");
	Weather.Fog.Enable = 1;
	Weather.Fog.Start = 0.0;
	Weather.Fog.Density = 0.002;
	Weather.Fog.Color = argb(0, 150, 185, 215);
	Weather.Sun.Color = argb(0, 230, 220, 205);
	Weather.Sun.Ambient = argb(0, 95, 100, 105);
	Weather.Sun.HeightAngle = 0.7;
	Weather.Sun.AzimuthAngle = 2.618;
	// the entity takes the wind only when it is assigned after its creation (AttributeChanged)
	Weather.Wind.Angle = stf(Weather.Wind.Angle);
	Weather.Wind.Speed = stf(Weather.Wind.Speed);
	Weather.isDone = "";

	SetEventHandler("WhrCalcFogColor", "World_FogColor", 0);
	CreateEntity(&Sky, "Sky");
	Sky.Size = 2048.0;
	Sky.Angle = 0.0;
	Sky.RotateSpeed = 0.0;
	Sky.techSky = "Sky";
	Sky.techSkyBlend = "SkyBlend";
	Sky.techSkyAlpha = "skyblend_alpha";
	Sky.techSkyFog = "SkyFog";
	LayerAddObject(EXECUTE, &Sky, 2);
	LayerAddObject(REALIZE, &Sky, 3);
	LayerAddObject(SEA_REFLECTION, &Sky, 1);
	Sky.Dir.d0 = "weather\skies\day\";
	Sky.Dir = "12";
	Sky.Color = argb(0, 255, 255, 255);
	Sky.isDone = "";

	CreateEntity(&Sea, "sea");
	LayerAddObject(EXECUTE, &Sea, 4);
	LayerAddObject(REALIZE, &Sea, 65530);
	Sea.Sea2.WaterColor = argb(0, 30, 90, 115);
	Sea.Sea2.SkyColor = argb(0, 205, 255, 255);
	Sea.Sea2.Amp1 = 1.8;
	Sea.Sea2.AnimSpeed1 = 1.5;
	Sea.Sea2.Scale1 = 0.6;
	Sea.Sea2.MoveSpeed1 = "2.0, 0.0, 0.0";
	Sea.Sea2.Amp2 = 0.6;
	Sea.Sea2.AnimSpeed2 = 15.0;
	Sea.Sea2.Scale2 = 3.8;
	Sea.Sea2.MoveSpeed2 = "1.0, 0.0, 1.0";
	Sea.Sea2.PosShift = 1.0;
	Sea.Sea2.BumpScale = 0.05;
	Sea.Sea2.Reflection = 0.6;
	Sea.Sea2.Transparency = 0.45;
	Sea.Sea2.Frenel = 0.45;
	Sea.Sea2.Attenuation = 0.3;
	Sea.Sea2.LodScale = 0.5;
	Sea.Sea2.GridStep = 0.1;
	Sea.Sea2.FoamEnable = 1;
	Sea.Sea2.FoamK = 0.2;
	Sea.Sea2.FoamV = 2.0;
	Sea.Sea2.FoamUV = 0.5;
	Sea.Sea2.FoamTexDisturb = 0.7;
	Sea.Sea2.SimpleSea = 0;
	Sea.Fog.Enable = 1;
	Sea.Fog.Start = 0.0;
	Sea.Fog.Color = argb(0, 150, 185, 215);
	Sea.Fog.SeaDensity = 0.001;
	Sea.MaxSeaHeight = 50.0;
	Sea.isDone = "";
}

void CreateLog()
{
	ScreenLog.Log.left = 16;
	ScreenLog.Log.up = 12;
	// narrower than the screen: the navigator takes the top right corner
	ScreenLog.Log.width = 540;
	ScreenLog.Log.height = 140;
	ScreenLog.Log.font = "interface_normal";
	ScreenLog.Log.fontscale = 1.0;
	ScreenLog.Log.color = argb(0, 255, 245, 215);
	ScreenLog.Log.offsetString = 26;
	ScreenLog.Log.speed = 0.1;
	ScreenLog.Log.color_speed = 0.03;
	CreateEntity(&ScreenLog, "ILogAndActions");
	LayerAddObject(EXECUTE, &ScreenLog, 100);
	LayerAddObject(REALIZE, &ScreenLog, 65535);
	SendMessage(&ScreenLog, "lll", LOG_AND_ACTIONS_INIT, 0, 1);
}

void Log(string text)
{
	SendMessage(&ScreenLog, "lls", LOG_ADD_STRING, 0, text);
}

// the fog thins out with the height: the sky above the horizon stays clear
int World_FogColor()
{
	float x = GetEventData();
	float y = GetEventData();
	float z = GetEventData();
	float k = y / fogHeight;
	if (k < 0.0) { k = 0.0; }
	if (k > 1.0) { k = 1.0; }
	int alpha = 255 - makeint(255.0 * k);
	return or(shl(alpha, 24), sti(Weather.Fog.Color));
}
