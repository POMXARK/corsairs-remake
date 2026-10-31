// The story machine of the original: what CORE.dll does with ACTIONS, QUESTS and DIALOGS.
// tools/pdm_logic2c.py compiles the data into data\pdm_logic.c: every .a is a function PdmA_*() calling
// the primitives below, the .ql story lines are PdmLines.<line>.q<i>, the .d trees PdmDialogs.
//
// A story line is open (launched) and stands on a quest (current). Entering a quest runs its first
// action field (3 quests use it: the medallion at the start, the officers' pay). A quest waits for its condition
// (NONE, OBTAIN Item/Goods/Reputation/Rank, KILL Person, ESCORT Person to an island); when it is met,
// the quest's action runs. The action mostly moves the line itself (SET_FOR Story_line … Quest …);
// if it does not, the line goes to the next quest, as message 9001 of CORE.dll does. Quests without
// an action ("void") are the idle states of a line. Pdm_StoryCheck repeats until nothing moves,
// at most PDM_STORY_CASCADE steps, as CORE.dll does.
//
// Pdm_StoryCheck runs after a dialog link and is called by the scenes whenever the player gets
// something, kills someone or arrives (the conditions of the quests).
//
// The state is kept in the attributes of the data objects: PlayerCard (money, items, experience,
// reputation, records), PlayerShipCard.cargo, PdmCharacters.<key> (dialog, location, nation,
// squadron, officer, dead). The later stages (sea, towns, dialogs, interface) read and change it.

#define PDM_STORY_CASCADE 5000

object PdmLocationNations;
int pdmRecords = 0;

int Pdm_Count(aref obj, string name)
{
	if (!CheckAttribute(obj, name)) { return 0; }
	return sti(obj.(name));
}

void Pdm_Add(aref obj, string name, int n)
{
	obj.(name) = Pdm_Count(obj, name) + n;
}

// ---------- the primitives of the actions ----------

void Pdm_AddMoney(int n) { Pdm_Add(PlayerCard, "money", n); }

void Pdm_AddItem(string item, int n)
{
	aref items;
	makearef(items, PlayerCard.items);
	Pdm_Add(items, item, n);
}

void Pdm_AddGoods(string goods, int n)
{
	aref cargo;
	makearef(cargo, PlayerShipCard.cargo);
	Pdm_Add(cargo, goods, n);
}

void Pdm_AddExperience(int n) { Pdm_Add(PlayerCard, "experience", n); }
void Pdm_AddReputation(int n) { Pdm_Add(PlayerCard, "reputation", n); }

void Pdm_AddRecord(string record)
{
	// TEXTS\RECORDS\<record>.rcd, the journal (P9)
	string at = "r" + pdmRecords;
	PlayerCard.records.(at) = record;
	PlayerCard.recdates.(at) = makeint(gameHours);
	pdmRecords++;
	Trace("PDM story: journal " + record);
}

void Pdm_SetItem(string person, string item, int n)
{
	PdmCharacters.(person).items.(item) = n;
}

void Pdm_JoinSquadron(string person) { aref card; makearef(card, PdmCharacters.(person)); card.squadron = 1; }
void Pdm_LeaveSquadron(string person) { aref card; makearef(card, PdmCharacters.(person)); card.squadron = 0; }
void Pdm_HireOfficer(string person) { aref card; makearef(card, PdmCharacters.(person)); card.officer = 1; }
void Pdm_DismissOfficer(string person) { aref card; makearef(card, PdmCharacters.(person)); card.officer = 0; }
void Pdm_SetNation(string person, int nation) { aref card; makearef(card, PdmCharacters.(person)); card.nation = nation; }
void Pdm_SetModel(string person, string model) { aref card; makearef(card, PdmCharacters.(person)); card.model_name = model; }
void Pdm_SetShip(string person, string ship) { aref card; makearef(card, PdmCharacters.(person)); card.ship_key = ship; }

void Pdm_SetDialog(string person, string dialog)
{
	aref card; makearef(card, PdmCharacters.(person));
	card.dialog_key = dialog;
}

void Pdm_SetLocation(string person, string location)
{
	// "island.location"; "void" takes the character out of the world
	aref card; makearef(card, PdmCharacters.(person));
	card.location = location;
}

void Pdm_SetLocationNation(string key, string location, int nation)
{
	PdmLocationNations.(key).id = location;
	PdmLocationNations.(key).nation = nation;
}

void Pdm_SetDLink(string dialog, string node, string link, int on)
{
	aref d;
	makearef(d, PdmDialogs.(dialog));
	if (!CheckAttribute(d, node + "." + link))
	{
		Trace("PDM story: no link " + dialog + ":" + node + ":" + link);
		return;
	}
	d.(node).(link).on = on;
}

void Pdm_LaunchLine(string line)
{
	PdmLines.(line).launched = 1;
	Trace("PDM story: open line " + PdmLines.(line).id);
}

void Pdm_SetQuest(string line, int quest)
{
	PdmLines.(line).current = quest;
	string at = "q" + quest;
	Trace("PDM story: " + PdmLines.(line).id + " -> " + PdmLines.(line).(at).name);
	// the action of entering the quest (the first action field of .ql)
	string enter = PdmLines.(line).(at).enter;
	if (enter != "") { call enter(); }
}

// the scenes of the later stages listen to these events
void Pdm_OpenLocation(string location)
{
	PlayerCard.location = location;
	Event("PdmStory_OpenLocation", "s", location);
}

void Pdm_PlayMovie(string movie) { Event("PdmStory_Movie", "s", movie); }
void Pdm_LaunchInterface(string screen, string page) { Event("PdmStory_Interface", "ss", screen, page); }
void Pdm_CloseGame(string ending) { Trace("PDM story: the end " + ending); Event("PdmStory_End", "s", ending); }

// ---------- the conditions and the cascade ----------

bool Pdm_QuestMet(aref quest)
{
	string cond = quest.cond;
	if (cond == "NONE") { return true; }
	string kind = quest.kind;
	string target = quest.target;
	int need = sti(quest.value);
	aref card;
	if (cond == "OBTAIN")
	{
		if (kind == "Item" && target == "money") { return Pdm_Count(PlayerCard, "money") >= need; }
		if (kind == "Item") { makearef(card, PlayerCard.items); return Pdm_Count(card, target) >= need; }
		if (kind == "Goods") { makearef(card, PlayerShipCard.cargo); return Pdm_Count(card, target) >= need; }
		if (kind == "Reputation") { return Pdm_Count(PlayerCard, "reputation") >= need; }
		if (kind == "Rank") { return Pdm_Count(PlayerCard, "rank") >= need; }
		return false;
	}
	if (target == "") { return false; }
	makearef(card, PdmCharacters.(target));
	if (cond == "KILL") { return Pdm_Count(card, "dead") != 0; }
	if (cond == "ESCORT")
	{
		if (Pdm_Count(card, "squadron") == 0 || !CheckAttribute(PlayerCard, "island")) { return false; }
		return PlayerCard.island == quest.to;
	}
	return false;
}

void Pdm_StoryCheck()
{
	int steps = 0;
	bool moved = true;
	int n, i, current;
	aref line, quest;
	string at, action;
	while (moved && steps < PDM_STORY_CASCADE)
	{
		moved = false;
		n = GetAttributesNum(&PdmLines);
		for (i = 0; i < n; i++)
		{
			line = GetAttributeN(&PdmLines, i);
			current = sti(line.current);
			if (sti(line.launched) == 0 || current < 0) { continue; }
			at = "q" + current;
			makearef(quest, line.(at));
			action = quest.action;
			if (action == "" || !Pdm_QuestMet(quest)) { continue; }
			Trace("PDM story: " + line.id + ": " + quest.name + " done, " + action);
			call action();
			steps++;
			moved = true;
			// the action did not move the line: the next quest (message 9001 of CORE.dll)
			if (sti(line.current) == current)
			{
				current++;
				if (current >= sti(line.count)) { line.launched = 0; line.current = -1; }
				else { line.current = current; }
			}
		}
	}
}

// ---------- dialogs ----------

// The player picks a link: its action runs if it is on; returns the node to go to ("" if it is off).
string Pdm_DialogChoose(string dialog, string node, string link)
{
	aref l;
	makearef(l, PdmDialogs.(dialog).(node).(link));
	if (sti(l.on) == 0) { return ""; }
	string action = l.action;
	if (action != "")
	{
		call action();
		Pdm_StoryCheck();
	}
	return l.to;
}

void Pdm_NewGame()
{
	PlayerCard.money = 0;
	PlayerCard.rank = 1;
	PlayerCard.reputation = 0;
	DeleteAttribute(&PlayerCard, "relations");
	PlayerCard.experience = 0;
	PlayerCard.island = PlayerCard.address.island;
	PdmLogic_NewGame();
	Pdm_StoryCheck();
}

// ---------- the self-test, SCENE=story run.sh ----------

void Story_Check(bool ok, string what)
{
	if (ok) { Trace("PDM story test: ok " + what); }
	else { Trace("PDM story test: FAILED " + what); }
}

void Story_SelfTest()
{
	Pdm_NewGame();
	// story_lines.idf puts Start on "add medallion", whose entering action gives the medallion
	aref items;
	makearef(items, PlayerCard.items);
	Story_Check(Pdm_Count(items, "Medallion") == 1, "a new game gives the medallion");
	// the chain of the English letter of marque: the agent opens the line and sets its quest,
	// the quest waits for the letter, the letter runs Agent_check_E_ok, which puts the line to void
	// and turns the link of the agent's dialog off
	PdmA_Agent_start_E_check();
	Story_Check(sti(PdmLines.Agent_check_E_marque.current) == 1, "Agent_start_E_check sets Check_E_marque");
	Story_Check(sti(PdmDialogs.English_agent_common.node_2.link_2_1.on) == 1, "the agent's link is on");
	Pdm_StoryCheck();
	Story_Check(sti(PdmLines.Agent_check_E_marque.current) == 1, "the quest waits for the letter");
	Pdm_AddItem("English_Letter_of_Marque", 1);
	Pdm_StoryCheck();
	Story_Check(sti(PdmLines.Agent_check_E_marque.current) == 0, "the letter completes it, the line is void");
	Story_Check(sti(PdmDialogs.English_agent_common.node_2.link_2_1.on) == 0, "the agent's link is off");

	// every action of the original runs once
	int n = GetAttributesNum(&PdmActions);
	aref a;
	string action;
	for (int i = 0; i < n; i++)
	{
		a = GetAttributeN(&PdmActions, i);
		action = GetAttributeValue(a);
		call action();
	}
	Pdm_StoryCheck();
	Trace("PDM story test: " + n + " actions run, money " + PlayerCard.money + ", records " + pdmRecords);
}
