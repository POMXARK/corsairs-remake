#include "menu_auto.c"
int step = 0;
void Main()
{
	Menu_Main();
	SetEventHandler("T_Step", "T_Step", 0);
	PostEvent("T_Step", 3500);
}
void OnLoad() { Menu_OnLoad(); }
// random deals in the three ports, the map clock moved on by 0..4 days between the visits
void T_Step()
{
	int k, n, r;
	if (step == 0) { Game_New(); step = 1; PostEvent("T_Step", 3500); return; }
	if (step == 1)
	{
		Dialog_Open();
		gold = 3000;
		for (k = 0; k < 300; k++)
		{
			if (rand(5) == 0)
			{
				r = rand(2);
				if (r == 0) { portIsland = "gull"; }
				if (r == 1) { portIsland = "crag"; }
				if (r == 2) { portIsland = "palm"; }
				worldMap.date.day = sti(worldMap.date.day) + rand(4);
				if (sti(worldMap.date.day) > 28) { worldMap.date.day = 1; worldMap.date.month = sti(worldMap.date.month) + 1; }
				Trade_Arrive();
			}
			tradeGood = rand(3);
			n = rand(2);
			if (n == 0 && cargo[tradeGood] > 0) { Trade_Sell(); }
			else
			{
				if (Cargo_Total() >= CARGO_MAX) { Trade_Sell(); } else { Trade_Buy(); }
			}
			if (gold < 300) { gold = 3000; }
		}
		Trace("TEST: mark done gold " + gold);
		step = 2;
		PostEvent("T_Step", 1000);
		return;
	}
	Menu_Quit();
}
