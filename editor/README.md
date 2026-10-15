# Corsairs editor windows

A module of Storm Engine with the game's editor windows (ImGui). The engine builds it with
`-DSTORM_EXTRA_MODULES=<path to this directory>`; the windows register themselves when the module is
linked and open from Developer Tools → Tools in `engine --editor`.

| Window | File | What it does |
|---|---|---|
| Market | `src/market_tool.cpp` | the tables of `game/program/market.c` live, the prices of `trade.c`, save back to `market.c` |
| Dialog | `src/dialog_tool.cpp`, `src/dialog_graph.cpp` | the dialog of `port.c`/`trade.c` as a graph: nodes, texts, links to no node, unreached nodes; opens a node in the game, writes the texts back |
| Map | `src/map_tool.cpp` | the world map from above: islands, ports, start, the brig, the ships and storms live; moves the brig, writes the start into `map.c`, brings «Ворон» and storms now |

The window reads the script variables by name (`goodBase`, `marketPrice`, `marketNorm`, `marketStock`,
`gold`, `cargo`, `portIsland`) and the `#define` numbers from `program/market.c` in the working
directory (the engine runs from `game/`). Opened windows are kept in `game/imgui.ini`.

The window Dialog parses the scripts (`program/port.c`, `program/trade.c`) and sends the event
`Editor_DialogNode` with a node name; `port.c` handles it (`Dialog_EditorNode`). It marks the node of the
script variable `dialogNode` and shows the attributes of the object `Dialog`.

The window Map reads the islands from `../engine/demos/worldmap/make_worldmap.py` (without it, the label
points of the WORLDMAP entity), the start from `program/map.c`, and the live points from the attributes of
`worldMap`: the brig is moved with `playerShipTeleport`, the storms and the ships are read with
`storm.cur`/`encounter.cur`. The timers are the script variables `ravenTimer` and `stormTimer`.
