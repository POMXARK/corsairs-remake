// First scene: the ship deck with cargo, a free camera and a moving sun.
// The scene lives in layers SCENE_EXECUTE/SCENE_REALIZE. Going to the menu only freezes them,
// so every entity keeps its state (camera, sun, spinning barrel) until the player continues.

#define SCENE_EXECUTE 0
#define SCENE_REALIZE 1

#define MSG_MODEL_LOAD_GEO 20500
#define MSG_MODEL_SET_POSITION 20506
#define MSG_MODEL_SET_TECHNIQUE 20510

// the renderer reads Render.BackColor every frame
object Render;
object Scene;
object Camera;
object Weather;
object Deck;
object Barrel1;
object Barrel2;
object Crate1;
object Crate2;

int sceneCreated = 0;
float sunAngle = 0.0;
float spinAngle = 0.0;

void Scene_MapControls()
{
	// key codes are Windows virtual keys, 256/257 are the mouse axes
	MapKey("FreeCamera_Turn_H", 256, 0);
	MapKey("FreeCamera_Turn_V", 257, 0);
	MapKey("FreeCamera_Forward", 87, 0);
	MapKey("FreeCamera_Backward", 83, 0);
	MapKey("Scene_Menu", 27, 0);
}

// a new game: builds the scene once, later only puts everything back to the start
void Scene_Start()
{
	if (sceneCreated == 0)
	{
		Scene_Create();
		sceneCreated = 1;
	}
	else
	{
		// FREE_CAMERA takes its position only in Init, so a new one is created
		DeleteClass(&Camera);
		Scene_CreateCamera();
	}
	sunAngle = 0.0;
	spinAngle = 0.0;
	Scene_Update(0.0);
	Trace("SCENE: start");
}

void Scene_Create()
{
	Render.BackColor = argb(255, 120, 160, 200);

	// cameras are not run by layers: the Scene entity executes the active one
	CreateEntity(&Scene, "Scene");
	LayerAddObject(SCENE_EXECUTE, &Scene, 0);
	Scene_CreateCamera();

	// WEATHER owns the sun: a directional D3D light plus the ambient colour, applied on isDone
	CreateEntity(&Weather, "weather");
	// exponential fog in the sky colour hides the edge of the deck
	Weather.Fog.Enable = 1;
	Weather.Fog.Density = 0.025;
	Weather.Fog.Color = argb(0, 120, 160, 200);
	Weather.Sun.Color = argb(0, 255, 236, 200);
	Weather.Sun.Ambient = argb(0, 90, 100, 120);
	Weather.Sun.HeightAngle = 0.7;

	Scene_LoadModel(&Deck, "ship\deck");
	Scene_LoadModel(&Barrel1, "ship\barrel");
	Scene_LoadModel(&Barrel2, "ship\barrel");
	Scene_LoadModel(&Crate1, "ship\crate");
	Scene_LoadModel(&Crate2, "ship\crate");
	Scene_PlaceModel(&Deck, 0.0, 0.0, 0.0, 0.0);
	Scene_PlaceModel(&Barrel2, 1.3, 0.0, 0.8, 0.0);
	Scene_PlaceModel(&Crate1, -1.4, 0.0, 0.4, 0.3);
	Scene_PlaceModel(&Crate2, -1.3, 0.8, 0.4, 0.9);
}

void Scene_CreateCamera()
{
	// the camera starts at the given point looking along +z
	Camera.position.x = 0.0;
	Camera.position.y = 1.6;
	Camera.position.z = -4.5;
	CreateEntity(&Camera, "FREE_CAMERA");
	SendMessage(&Scene, "si", "SetActiveCamera", &Camera);
}

void Scene_LoadModel(ref model, string name)
{
	CreateEntity(&model, "modelr");
	SendMessage(&model, "ls", MSG_MODEL_LOAD_GEO, name);
	// fixed-function lighting by the D3D lights; without a technique vertex colours are drawn as is
	SendMessage(&model, "ls", MSG_MODEL_SET_TECHNIQUE, "DLightModel");
	LayerAddObject(SCENE_EXECUTE, &model, 10);
	LayerAddObject(SCENE_REALIZE, &model, 10);
}

// position and rotation around the vertical axis
void Scene_PlaceModel(ref model, float x, float y, float z, float angle)
{
	float c = cos(angle);
	float s = sin(angle);
	SendMessage(&model, "lffffffffffff", MSG_MODEL_SET_POSITION, x, y, z, c, 0.0, 0.0 - s, 0.0, 1.0, 0.0, s, 0.0, c);
}

void Scene_Freeze(int freeze)
{
	LayerFreeze(SCENE_EXECUTE, freeze);
	LayerFreeze(SCENE_REALIZE, freeze);
}

// called every frame while the scene is active; dt in seconds
void Scene_Update(float dt)
{
	spinAngle = spinAngle + dt * 0.8;
	Scene_PlaceModel(&Barrel1, 0.0, 0.0, 0.0, spinAngle);

	// the sun circles the scene, so the shading visibly follows it
	sunAngle = sunAngle + dt * 0.4;
	Weather.Sun.AzimuthAngle = sunAngle;
	Weather.isDone = "";
}
