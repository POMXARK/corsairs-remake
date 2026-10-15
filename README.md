# Corsairs Remake

Game content for a remaster of *Corsairs* on [Storm Engine](https://github.com/POMXARK/storm-engine).
The engine lives in the `engine/` submodule; this repository holds only the game: scripts, interface
and text configs, and the assets built from free sources (see [CREDITS.md](CREDITS.md)). The built assets
are committed, so the game runs right after clone; `run.sh` rebuilds them (the output is the same).

```
engine/   Storm Engine fork (submodule, branch miniaudio-sound)
assets/   downloaded free assets: fonts, the menu background
game/     game folder the engine runs in: engine.ini, program/ (menu.c — the menu, sea.c — the sea battle),
          resource/ (ini, built textures, models, sounds)
tools/    fetch_assets.sh — downloads free assets; make_assets.py — converts them to .tx textures and fonts.ini.
          The sea battle assets come from the generators of the engine demos (engine/demos/*/make_*.py)
```

## Run (Linux)

```bash
git clone --recursive https://github.com/POMXARK/corsairs-remake.git
# build the engine from engine/ (Linux build notes are in the engine fork), then:
./run.sh <path to built engine executable>
```

Arrow keys / mouse select a menu item, Enter or a click activates it, Escape or «Выход» quits.

«Новая игра» starts a sea battle built from the engine demos: our brig «Ласточка» against the AI brig
«Ворон» near an island, with the HUD — navigator (compass, wind, speeds, the enemy on the minimap), the
ship panel (hull, sails, crew, cannon reload) and the battle log in Russian.

| Key | Action |
|---|---|
| W / S | raise / lower the sails |
| A / D | turn |
| mouse | look around |
| Space | broadside: the loaded side that faces the enemy fires |
| Z / X | zoom the minimap in / out |
| R | new battle |
| Escape | menu |

The menu does not lose the battle — the scene is only frozen, and «Продолжить» brings it back as it was;
«Новая игра» starts a new one.
