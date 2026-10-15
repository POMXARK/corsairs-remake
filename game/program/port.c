// The port: a quay with a pier (make_port.py), the player's sailor walking on it, the «Ласточка» at
// the pier and the old boatswain Tom at its end. Built from the engine demos location and dialog:
// the "location" entity loads the model and the floor the characters walk on, "player" walks on it
// driven by the controls, "locationcamera" follows him, "dialog" draws the conversation with Tom.
// Talking to Tom takes the player out to sea (sea.c) and pays for the «Ворон» sunk there.
// W/S walk, A/D or the mouse turn, Shift walks instead of running, E talks to Tom; in the dialog
// Up/Down pick an answer, Enter or Space says it, Escape leaves.

#define MSG_LOCATION_ADD_MODEL 30100
#define MSG_LOCATION_SET_CHRS_PATCH 30120
#define MSG_LOCATION_MODELSPATH 30140
#define MSG_LOCATION_TEXTURESPATH 30141
#define MSG_CHARACTER_SETMODEL 30200
#define MSG_CHARACTER_GETPOS 30202
#define MSG_CHARACTER_GETAY 30203
#define MSG_CHARACTER_TELEPORT_AY 30211
#define MSG_CAMERA_SETTARGET 30500
#define MSG_CAMERA_FOLLOW 30510

#define MSG_MODEL_LOAD_GEO 20500
#define MSG_MODEL_LOAD_ANI 20501
#define MSG_MODEL_SET_POSITION 20506
#define MSG_MODEL_SET_TECHNIQUE 20510
#define MSG_MODEL_PLAY_ACTION 20601

// make_port.py: the deck of the quay and the pier over the sea, Tom's cell at the end of the pier
#define PORT_DECK 1.5
#define TOM_X 0.0
#define TOM_Z 4.5
// E works this close to Tom
#define TALK_DISTANCE 2.5
// how often the port checks whether the player has come up to Tom, ms
#define TICK_MS 250

object PortLocation;
object PortGroups;
object Hero;
object PortCamera;
object Tom;
object PortBrig;
object Dialog;

// head and foot colours of the characters' shadows, answered to the shadow entity
int shadowDensity[2];
int inPort = 0;
// every visit has its own chain of ticks: an old one ends when it sees another number
int portVisit = 0;
int nearTom = 0;
int dialogOpen = 0;
// "Отдать швартовы!": the port is left when the dialog has closed
int castOff = 0;
// "save": the hero comes back where he was saved
string portSpawn = "";
float heroX = 0.0;
float heroY = 0.0;
float heroZ = 0.0;
float heroAY = 0.0;

void Port_MapControls()
{
	// read by the player character and the location camera
	MapKey("ChrForward", 87, 0);
	MapKey("ChrBackward", 83, 0);
	MapKey("ChrTurnHL", 65, 0);
	MapKey("ChrTurnHR", 68, 0);
	// running is the default, the key switches to walking
	MapKey("ChrRun", 16, 0);
	MapKey("ChrTurnH", 256, 0);
	MapKey("ChrCamTurnV", 257, 0);
	MapKey("Port_Talk", 69, 0);
	// F5 saves (menu.c)
	// polled by the dialog entity every frame while it is open
	MapKey("DlgUp", 38, 0);
	MapKey("DlgDown", 40, 0);
	MapKey("DlgAction", 32, 0);
	MapKey("DlgAction1", 1, 0);
	MapKey("DlgAction2", 13, 0);
	MapKey("DlgScrollUp", 33, 0);
	MapKey("DlgScrollDown", 34, 0);
	MapKey("DlgCancel", 27, 0);
}

// The location runs the characters in it: it is made before them. The first visit starts on the
// quay by the warehouse, a return from the sea on the pier by the brig.
void Port_Enter()
{
	World_Waves(0.4, 0.2, 0.6);
	World_Ambient(1);
	World_Music("music\calm.wav");

	PortLocation.id = "port";
	CreateEntity(&PortLocation, "location");
	// models and the patch come from resource\models\port\, textures from resource\textures\port\
	SendMessage(&PortLocation, "ls", MSG_LOCATION_MODELSPATH, "port");
	SendMessage(&PortLocation, "ls", MSG_LOCATION_TEXTURESPATH, "port");
	if (!SendMessage(&PortLocation, "lssl", MSG_LOCATION_ADD_MODEL, "port", "DLightModel", 10))
	{
		Trace("PORT: model not loaded");
	}
	if (!SendMessage(&PortLocation, "ls", MSG_LOCATION_SET_CHRS_PATCH, "port_patch"))
	{
		Trace("PORT: character patch not loaded");
	}
	CreateEntity(&PortGroups, "CharactersGroups");

	Hero.id = "hero";
	CreateEntity(&Hero, "player");
	// resource\models\characters\sailor.gm with resource\animation\sailor.ani
	if (!SendMessage(&Hero, "lss", MSG_CHARACTER_SETMODEL, "sailor", "sailor"))
	{
		Trace("PORT: hero not loaded");
	}
	// one standing action instead of the default idle_1..idle_11; changing "actions" makes the
	// character read the action names again
	Hero.actions.idle.i1 = "idle_1";
	Hero.actions = "";
	if (portSpawn == "save") { SendMessage(&Hero, "lffff", MSG_CHARACTER_TELEPORT_AY, heroX, heroY, heroZ, heroAY); }
	else
	{
		if (lastBattle == "") { SendMessage(&Hero, "lffff", MSG_CHARACTER_TELEPORT_AY, 0.0, PORT_DECK, -24.0, 0.0); }
		else { SendMessage(&Hero, "lffff", MSG_CHARACTER_TELEPORT_AY, 0.0, PORT_DECK, 1.0, 0.0); }
	}

	CreateEntity(&PortCamera, "locationcamera");
	SendMessage(&PortCamera, "li", MSG_CAMERA_SETTARGET, &Hero);
	SendMessage(&PortCamera, "l", MSG_CAMERA_FOLLOW);
	SendMessage(&Scene, "si", "SetActiveCamera", &PortCamera);

	// Tom at the end of the pier, facing the quay; the window shows "name lastname" of the speaker
	LoadModel(&Tom, "demo\sailor");
	SendMessage(&Tom, "ls", MSG_MODEL_LOAD_ANI, "demo\sailor");
	SendMessage(&Tom, "lls", MSG_MODEL_PLAY_ACTION, 0, "idle");
	PlaceModel(&Tom, TOM_X, PORT_DECK, TOM_Z, PI);
	Tom.name = "Том";
	Tom.lastname = "Бакстер";
	// the brig moored along the pier, its bow to the sea
	LoadModel(&PortBrig, "ships\Brig\Brig");
	PlaceModel(&PortBrig, 6.5, 0.0, -2.0, 0.0);
	LayerAddObject(SEA_REFLECTION2, &PortBrig, 10);

	shadowDensity[0] = argb(255, 96, 96, 96);
	shadowDensity[1] = argb(255, 96, 96, 64);
	SetEventHandler("EWhr_GetShadowDensity", "Port_ShadowDensity", 0);
	SetEventHandler("EWhr_GetFogDensity", "Port_FogDensity", 0);
	SetEventHandler("DialogEvent", "Dialog_Event", 0);
	SetEventHandler("DialogCancel", "Dialog_Cancel", 0);
	SetEventHandler("EmergencyDialogExit", "Dialog_Cancel", 0);
	SetEventHandler("Port_DialogClose", "Dialog_Close", 0);
	SetEventHandler("Port_Tick", "Port_Tick", 0);

	inPort = 1;
	nearTom = 0;
	castOff = 0;
	portVisit++;
	PostEvent("Port_Tick", TICK_MS, "l", portVisit);
	if (portSpawn == "save") { Log("Игра загружена: " + gold + " песо, побед: " + wins); }
	else
	{
		if (lastBattle == "") { Log("Порт. Том ждёт на краю пирса. W/S — идти, A/D — поворот, F5 — сохранить"); }
		else { Log("Снова в порту. Том ждёт на пирсе"); }
	}
	portSpawn = "";
	Trace("PORT: scene loaded");
}

// The entities go at the end of the frame: the map is made in the next one (menu.c, Game_GoTo).
void Port_Leave()
{
	if (dialogOpen) { Dialog_Close(); }
	DeleteClass(&PortBrig);
	DeleteClass(&Tom);
	DeleteClass(&PortCamera);
	DeleteClass(&Hero);
	DeleteClass(&PortGroups);
	DeleteClass(&PortLocation);
	inPort = 0;
	Trace("PORT: left");
}

void LoadModel(ref model, string name)
{
	CreateEntity(model, "modelr");
	SendMessage(model, "ls", MSG_MODEL_LOAD_GEO, name);
	SendMessage(model, "ls", MSG_MODEL_SET_TECHNIQUE, "DLightModel");
	LayerAddObject(EXECUTE, model, 10);
	LayerAddObject(REALIZE, model, 10);
}

// position and rotation around the vertical axis; the model faces +z at angle 0
void PlaceModel(ref model, float x, float y, float z, float angle)
{
	float c = cos(angle);
	float s = sin(angle);
	SendMessage(model, "lffffffffffff", MSG_MODEL_SET_POSITION, x, y, z, c, 0.0, 0.0 - s, 0.0, 1.0, 0.0, s, 0.0, c);
}

ref Port_ShadowDensity()
{
	return &shadowDensity;
}

float Port_FogDensity()
{
	return stf(Weather.Fog.Density);
}

// for the save: the hero entity keeps his position to itself
void Port_RememberHero()
{
	SendMessage(&Hero, "leee", MSG_CHARACTER_GETPOS, &heroX, &heroY, &heroZ);
	SendMessage(&Hero, "le", MSG_CHARACTER_GETAY, &heroAY);
}

float Port_TomDistance()
{
	float x, y, z;
	SendMessage(&Hero, "leee", MSG_CHARACTER_GETPOS, &x, &y, &z);
	float dx = x - TOM_X;
	float dz = z - TOM_Z;
	return sqrt(dx * dx + dz * dz);
}

// a hint when the player comes up to Tom
void Port_Tick()
{
	int visit = GetEventData();
	if (!inPort || visit != portVisit) { return; }
	int close = 0;
	if (Port_TomDistance() < TALK_DISTANCE) { close = 1; }
	if (close && !nearTom && !dialogOpen) { Log("E — поговорить с Томом"); }
	nearTom = close;
	PostEvent("Port_Tick", TICK_MS, "l", visit);
}

// called by menu.c for the controls pressed while the port is shown
void Port_Control(string control)
{
	// while the dialog is open its own controls work
	if (dialogOpen) { return; }
	if (control == "Port_Talk" && Port_TomDistance() < TALK_DISTANCE) { Dialog_Open(); }
}

// ---------------------------------------------------------------- the dialog entity

void Dialog_Open()
{
	if (dialogOpen) { return; }
	// the entity pauses the game (time scale 0) and lets it run again over a second
	CreateEntity(&Dialog, "dialog");
	lastGo = "";
	// message 1: the speaker, whose name/lastname the window shows, and his model
	SendMessage(&Dialog, "lii", 1, &Tom, &Tom);
	// drawn over everything else
	LayerAddObject(REALIZE, &Dialog, -256);
	dialogOpen = 1;
	if (unpaidWins > 0) { Dialog_Node("reward"); }
	else
	{
		if (lastBattle == "loss") { Dialog_Node("lost"); }
		else
		{
			if (metTom) { Dialog_Node("again"); }
			else { Dialog_Node("start"); }
		}
	}
	Trace("PORT: dialog opened");
}

// Closing the dialog from its own event would delete the entity while it is drawing, so the
// handlers post an event that closes it on the next frame.
void Dialog_Close()
{
	if (!dialogOpen) { return; }
	DeleteClass(&Dialog);
	dialogOpen = 0;
	Trace("PORT: dialog closed");
	if (castOff)
	{
		castOff = 0;
		Game_GoTo("map");
	}
}

void Dialog_Leave()
{
	PostEvent("Port_DialogClose", 1);
}

// an answer was chosen: its "go" is in Dialog.CurrentNode
void Dialog_Event()
{
	lastGo = Dialog.CurrentNode;
	Dialog_Node(Dialog.CurrentNode);
}

// Escape, or an answer without "go" / with the same "go" as the answer before (the entity treats
// that as a broken tree)
void Dialog_Cancel()
{
	Dialog_Leave();
}

void Say(string text)
{
	Dialog.Text = text;
	DeleteAttribute(&Dialog, "Links");
}

// The answers are shown in the order they are added; the text must be set before "go". The entity
// closes the dialog when an answer leads where the answer before it led (it takes that for a loop
// in the tree): an answer that may be chosen twice in a row, "buy more", gets a twin name ending
// in "2" while its name is the last one chosen.
string lastGo = "";

void Answer(string id, string text, string go)
{
	if (go == lastGo) { go = go + "2"; }
	Dialog.Links.(id) = text;
	Dialog.Links.(id).go = go;
}

// ---------------------------------------------------------------- Tom

void Dialog_Node(string node)
{
	Trace("PORT: node " + node);
	if (node == "start")
	{
		metTom = 1;
		Say("А, капитан! Я Том Бакстер, боцман «Ласточки». Бриг готов, команда на борту. Одна беда: у входа в бухту крутится «Ворон» и не выпускает ни одного судна.");
		Answer("l1", "Что за «Ворон»?", "raven");
		Answer("l2", "В море!", "sail");
		Answer("l3", "Корабль и припасы", "shop");
		Answer("l4", "Позже, Том.", "exit");
		return;
	}
	if (node == "again")
	{
		Say("Ну что, капитан? В кошельке " + gold + " песо, «Воронов» на дне: " + wins + ".");
		Answer("l1", "Что за «Ворон»?", "raven");
		Answer("l2", "В море!", "sail");
		Answer("l3", "Корабль и припасы", "shop");
		Answer("l4", "Позже, Том.", "exit");
		return;
	}
	if (node == "raven")
	{
		if (wins > 0) { Say("Опять «Ворон»! Пираты учатся: этот крепче сбит, команда больше, канониры злее, да и ходит быстрее. Губернатор поднял награду: " + Raven_Bounty() + " песо."); }
		else { Say("Пиратский бриг, как наш, только команда злее. Бьёт с обоих бортов, ядра летят на полкабельтова. Губернатор обещал " + Raven_Bounty() + " песо тому, кто пустит его на дно."); }
		Answer("l1", "В море!", "sail");
		Answer("l2", "Позже, Том.", "exit");
		return;
	}
	if (node == "sail")
	{
		Say("Есть, капитан! Ветер попутный. Отдаём швартовы?");
		Answer("l1", "Отдать швартовы!", "cast_off");
		Answer("l2", "Погоди.", "exit");
		return;
	}
	if (node == "cast_off")
	{
		castOff = 1;
		Dialog_Leave();
		return;
	}
	if (node == "reward")
	{
		int reward = unpaidGold;
		gold = gold + reward;
		wins = wins + unpaidWins;
		unpaidWins = 0;
		unpaidGold = 0;
		lastBattle = "";
		metTom = 1;
		if (unpaidPrizes > 0) { Say("Привёл «Ворона» на буксире! Губернатор взял его в казну и заплатил и награду, и призовые: вот " + reward + " песо. Теперь у тебя " + gold + "."); }
		else { Say("Видал я с пирса, как «Ворон» пошёл ко дну! Губернатор слово держит: вот " + reward + " песо. Теперь у тебя " + gold + "."); }
		unpaidPrizes = 0;
		lastBoarding = "";
		Answer("l1", "Ещё в море!", "sail");
		Answer("l2", "Корабль и припасы", "shop");
		Answer("l3", "Отдохну пока.", "exit");
		return;
	}
	if (node == "lost")
	{
		lastBattle = "";
		metTom = 1;
		if (lastBoarding == "lost") { Say("Живой, капитан! Пираты отбили абордаж, ребята еле вынесли тебя. Команды осталось " + shipCrew + ", корпус " + shipHull + "%. Сначала бы людей набрать..."); }
		else { Say("Ничего, капитан. Бриг подняли и кое-как залатали: корпус " + shipHull + "%, команды " + shipCrew + ". «Ворон» никуда не делся. Сначала бы в док..."); }
		lastBoarding = "";
		Answer("l1", "Корабль и припасы", "shop");
		Answer("l2", "В море!", "sail");
		Answer("l3", "Позже, Том.", "exit");
		return;
	}
	if (node == "exit")
	{
		Dialog_Leave();
		return;
	}
	// a twin of an answer chosen twice in a row (Answer)
	if (node == "shop") { Shop_Show("Что нужно, капитан?"); return; }
	if (node == "repair" || node == "repair2") { Shop_Repair(); return; }
	if (node == "hire" || node == "hire2") { Shop_Hire(); return; }
	if (node == "balls" || node == "balls2") { Shop_Charge(CHARGE_BALLS); return; }
	if (node == "knippels" || node == "knippels2") { Shop_Charge(CHARGE_KNIPPELS); return; }
	if (node == "grapes" || node == "grapes2") { Shop_Charge(CHARGE_GRAPES); return; }
	Trace("PORT: unknown node " + node);
	Dialog_Leave();
}

// ---------------------------------------------------------------- Tom's shop

// the prices in pesos: a percent of the hull, a sailor, a lot of each charge; the hold takes
// MAX_CHARGES of all of them
#define REPAIR_PRICE 4
#define SAILOR_PRICE 5
#define CHARGE_LOT 30
#define BALLS_PRICE 60
#define KNIPPELS_PRICE 75
#define GRAPES_PRICE 45
#define MAX_CHARGES 240

// what the shop can still sell: a missing hull percent or sailor costs its price, the lot is whole
int Shop_RepairCost() { return (SHIP_HULL - shipHull) * REPAIR_PRICE; }
int Shop_HireCost() { return (SHIP_CREW - shipCrew) * SAILOR_PRICE; }

void Shop_Show(string reply)
{
	Say(reply + " Корпус " + shipHull + "%, команды " + shipCrew + " из " + SHIP_CREW + ". В трюме ядра " + shipBalls + ", книппели " + shipKnippels + ", картечь " + shipGrapes + ". В кошельке " + gold + " песо.");
	if (shipHull < SHIP_HULL) { Answer("l1", "Залатать корпус (" + Shop_RepairCost() + " песо)", "repair"); }
	if (shipCrew < SHIP_CREW) { Answer("l2", "Нанять матросов (" + Shop_HireCost() + " песо)", "hire"); }
	if (Shop_HoldFree())
	{
		Answer("l3", CHARGE_LOT + " ядер — корпус (" + BALLS_PRICE + " песо)", "balls");
		Answer("l4", CHARGE_LOT + " книппелей — паруса (" + KNIPPELS_PRICE + " песо)", "knippels");
		Answer("l5", CHARGE_LOT + " картечи — команда (" + GRAPES_PRICE + " песо)", "grapes");
	}
	Answer("l6", "Хватит.", "again");
}

int Shop_HoldFree() { return shipBalls + shipKnippels + shipGrapes + CHARGE_LOT <= MAX_CHARGES; }

int Shop_ChargePrice(int charge)
{
	if (charge == CHARGE_KNIPPELS) { return KNIPPELS_PRICE; }
	if (charge == CHARGE_GRAPES) { return GRAPES_PRICE; }
	return BALLS_PRICE;
}

// as much as the gold pays for: a part of the work is better than none
void Shop_Repair()
{
	int points = SHIP_HULL - shipHull;
	if (points * REPAIR_PRICE > gold) { points = gold / REPAIR_PRICE; }
	if (points <= 0) { Shop_Show("Без денег плотники не работают."); return; }
	gold = gold - points * REPAIR_PRICE;
	shipHull = shipHull + points;
	Trace("PORT: repair " + points + ", gold " + gold);
	if (shipHull < SHIP_HULL) { Shop_Show("На все пробоины не хватило, залатали " + points + "%."); return; }
	Shop_Show("Плотники справились, корпус как новый.");
}

void Shop_Hire()
{
	int sailors = SHIP_CREW - shipCrew;
	if (sailors * SAILOR_PRICE > gold) { sailors = gold / SAILOR_PRICE; }
	if (sailors <= 0) { Shop_Show("Задаром в таверне никто не нанимается."); return; }
	gold = gold - sailors * SAILOR_PRICE;
	shipCrew = shipCrew + sailors;
	Trace("PORT: hire " + sailors + ", gold " + gold);
	Shop_Show("Нанял " + sailors + " человек в таверне.");
}

void Shop_Charge(int charge)
{
	int price = Shop_ChargePrice(charge);
	if (gold < price) { Shop_Show("Не хватает, капитан: " + Charge_Name(charge) + " стоят " + price + " песо."); return; }
	if (!Shop_HoldFree()) { Shop_Show("Трюм полон."); return; }
	gold = gold - price;
	Charge_Add(charge, CHARGE_LOT);
	Trace("PORT: " + Charge_Type(charge) + " " + Charge_Count(charge) + ", gold " + gold);
	Shop_Show("Погрузили: " + Charge_Name(charge) + ".");
}
