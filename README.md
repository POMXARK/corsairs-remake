# Corsairs Remake

Game content for a remaster of *Corsairs* on [Storm Engine](https://github.com/POMXARK/storm-engine).
The engine lives in the `engine/` submodule; this repository holds only the game: scripts, interface
and text configs, and tools that build textures and fonts from free assets (see [CREDITS.md](CREDITS.md)).

```
engine/   Storm Engine fork (submodule, branch miniaudio-sound)
game/     game folder the engine runs in: engine.ini, program/ (scripts), resource/ (ini, generated textures)
tools/    fetch_assets.sh — downloads free assets; make_assets.py — converts them to .tx textures and fonts.ini;
          make_scene.py — generates the deck scene (.gm models, wood textures)
```

## Run (Linux)

```bash
git clone --recursive https://github.com/POMXARK/corsairs-remake.git
# build the engine from engine/ (Linux build notes are in the engine fork), then:
./run.sh <path to built engine executable>
```

Arrow keys / mouse select a menu item, Enter or a click activates it, Escape or «Выход» quits.

«Новая игра» opens the first scene, a ship deck with cargo: the mouse looks around, W/S move
(Shift, Ctrl to speed up). Escape returns to the menu without losing anything — the scene is only
frozen, and «Продолжить» brings it back as it was; «Новая игра» starts it over.
