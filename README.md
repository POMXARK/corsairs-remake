# Corsairs Remake

Game content for a remaster of *Corsairs* on [Storm Engine](https://github.com/POMXARK/storm-engine).
The engine lives in the `engine/` submodule; this repository holds only the game: scripts, interface
and text configs, and the assets built from free sources (see [CREDITS.md](CREDITS.md)). The built assets
are committed, so the game runs right after clone; `run.sh` rebuilds them (the output is the same).

```
engine/   Storm Engine fork (submodule, branch miniaudio-sound)
assets/   downloaded free assets: fonts, the menu background
game/     game folder the engine runs in: engine.ini, program/ (menu.c — the menu and the scene switch,
          world.c — the sea, sky, sound and game state, port.c — the port and Tom, sea.c — the sea battle),
          resource/ (ini, built textures, models, sounds)
tools/    fetch_assets.sh — downloads free assets; make_assets.py — converts them to .tx textures and fonts.ini;
          make_port.py — the port: quay, pier, sailors, dialog window.
          The other assets come from the generators of the engine demos (engine/demos/*/make_*.py)
```

## Video

[![The second slice: the port, Tom, the battle with «Ворон», the reward, saving and loading](media/second-slice.jpg)](media/second-slice.mp4)

A scripted run of the whole slice (130 s, with sound): «Новая игра» → the captain runs along the pier to
Tom → the conversation → out to sea → a fair battle, both brigs led by the AI, the camera on «Ворон» and
the aim zone on the water (shown 4× faster: three minutes of broadsides until «Ворон» sinks) → back in the
port Tom pays 500 pesos → F5 → the menu → «Загрузить» brings the game back with 600 pesos.

## Run (Linux)

```bash
git clone --recursive https://github.com/POMXARK/corsairs-remake.git
# build the engine from engine/ (Linux build notes are in the engine fork), then:
./run.sh <path to built engine executable>
```

Arrow keys / mouse select a menu item, Enter or a click activates it, Escape or «Выход» quits.

«Новая игра» starts in the port: the captain walks along the quay to the old boatswain Tom at the end of
the pier. Tom tells about the pirate brig «Ворон» guarding the bay, and «Отдать швартовы!» takes the
captain's brig «Ласточка» out to sea. The battle is built from the engine demos: the AI brig «Ворон» near
an island, with the HUD — navigator (compass, wind, speeds, the enemy on the minimap), the ship panel
(hull, sails, crew, cannon reload) and the battle log in Russian. After the battle Enter returns to the
port, where Tom pays 500 pesos for every «Ворон» sunk: two full broadsides that hit sink her.

The brig keeps her state between the battles: the hull, the crew and the balls in the hold (60 at the
start, a broadside takes 6; with no balls left the guns are silent). A short-handed crew loads slower:
half the sailors, twice the time. A sunk «Ласточка» is raised by the harbour with 30% of the hull and
at least 40 sailors. Tom's «Корабль и припасы» sells what is missing for gold: the hull at 4 pesos a
percent, sailors at 5 pesos each, 30 balls for 60 pesos (up to 180 in the hold); without enough gold
he repairs and hires as much as it pays for.

In the port:

| Key | Action |
|---|---|
| W / S | walk forward / back |
| A / D, mouse | turn |
| Shift | walk instead of running |
| E | talk to Tom (next to him) |
| F5 | save the game (out of a conversation) |
| Up / Down, Enter or Space | pick and say an answer; Escape leaves the conversation |
| Escape | menu |

At sea:

| Key | Action |
|---|---|
| W / S | raise / lower the sails |
| A / D | turn |
| mouse | look around |
| right mouse button, held | aim: the water the balls of the side past the ship reach (gold — the enemy is in it, red — still loading) |
| T | the camera keeps the enemy in view past our ship (on at the start) / turns freely |
| Space | broadside: the loaded side that faces the enemy fires |
| Z / X | zoom the minimap in / out |
| R | new battle |
| Enter | back to the port, when the battle is over |
| Escape | menu |

The menu does not lose the scene — it is only frozen, and «Продолжить» brings it back as it was;
«Новая игра» starts a new one.

F5 in the port saves the game to `game/save/game.sav` (gold, wins, the brig, the captain's place on the quay);
«Загрузить» in the menu, active when a save exists, brings it back. At sea the game is not saved.
