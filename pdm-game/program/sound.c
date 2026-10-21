// The music and the ambient sounds, as the original plays them (tools/pdm_sound.py converts its
// MUSIC/mmusic.ini, SOUNDS/msound.ini and WORLDS/locations/snd/*.snd into data\pdm_sound.c, the
// aliases of resource/ini/aliases/pdm.ini and the schemes of resource/ini/sound_scheme.ini).
// One piece of music plays at a time and crossfades into the next. A location has an ambient loop
// (the town by day) and a scheme of sounds now and then (dogs, a voice in the tavern); in a tavern
// full of people their voices loop too.

// shared/messages.h, the messages of the sound entity; a looped stereo sound takes "lslllllllf": file
// or alias, type, volume type, only cache, looped, cached, fade in ms, pause between loops ms, volume
#define MSG_SOUND_PLAY 77003
#define MSG_SOUND_STOP 77004
#define MSG_SOUND_SCHEME_RESET 77013
#define MSG_SOUND_SCHEME_SET 77014
#define MSG_SOUND_SET_MASTER_VOLUME 77021
// sound_service/include/sound_defines.h: eSoundType and eVolumeType
#define MP3_STEREO 2
#define PCM_STEREO 4
#define VOLUME_FX 1
#define VOLUME_MUSIC 2

#define SOUND_FADE_MS 1500

object Sound;
string soundMusic = "";
int soundMusicId = 0;
// the loops of the location: the ambient sound and the voices of many
int soundLoops[2];

void Sound_Init()
{
	CreateEntity(&Sound, "Sound");
	SendMessage(&Sound, "lfff", MSG_SOUND_SET_MASTER_VOLUME, 0.8, 0.5, 1.0);
	soundLoops[0] = 0;
	soundLoops[1] = 0;
}

// the music by its alias of mmusic.ini (Main, Freesailing, eTown ...: attribute names are not case
// sensitive); the same music goes on
void Sound_Music(string alias)
{
	if (alias == soundMusic) { return; }
	if (soundMusicId != 0) { SendMessage(&Sound, "lll", MSG_SOUND_STOP, soundMusicId, SOUND_FADE_MS); }
	soundMusic = alias;
	soundMusicId = 0;
	if (!CheckAttribute(&PdmMusic, alias))
	{
		Trace("PDM sound: no music " + alias);
		return;
	}
	soundMusicId = SendMessage(&Sound, "lslllllllf", MSG_SOUND_PLAY, PdmMusic.(alias), MP3_STEREO, VOLUME_MUSIC,
		false, true, false, SOUND_FADE_MS, 0, 1.0);
}

// the music of the towns of a nation (its index in nations.idf, as PdmIslands.<island>.nation)
void Sound_TownMusic(int nation)
{
	if (nation < 0 || nation >= GetAttributesNum(&PdmNations)) { return; }
	aref card;
	card = GetAttributeN(&PdmNations, nation);
	Sound_Music(card.town_music);
}

int Sound_Loop(string alias)
{
	if (alias == "") { return 0; }
	return SendMessage(&Sound, "lslllllllf", MSG_SOUND_PLAY, alias, PCM_STEREO, VOLUME_FX, false, true, false,
		SOUND_FADE_MS, 0, 1.0);
}

// the sounds of a kind of location (the sound line of a .loc: town, tavern, cave ...), by day;
// many: whether the location is full of people
void Sound_Location(string kind, bool many)
{
	Sound_StopLocation();
	if (!CheckAttribute(&PdmLocSounds, kind)) { return; }
	soundLoops[0] = Sound_Loop(PdmLocSounds.(kind).day);
	if (many) { soundLoops[1] = Sound_Loop(PdmLocSounds.(kind).many); }
	SendMessage(&Sound, "ls", MSG_SOUND_SCHEME_SET, PdmLocSounds.(kind).scheme);
}

void Sound_StopLocation()
{
	SendMessage(&Sound, "l", MSG_SOUND_SCHEME_RESET);
	for (int i = 0; i < 2; i++)
	{
		if (soundLoops[i] != 0) { SendMessage(&Sound, "lll", MSG_SOUND_STOP, soundLoops[i], SOUND_FADE_MS); }
		soundLoops[i] = 0;
	}
}
