# Corsairs editor windows

A module of Storm Engine with the game's editor windows (ImGui). The engine builds it with
`-DSTORM_EXTRA_MODULES=<path to this directory>`; the windows register themselves when the module is
linked and open from Developer Tools → Tools in `engine --editor`.

| Window | File | What it does |
|---|---|---|
| Market | `src/market_tool.cpp` | the tables of `game/program/market.c` live, the prices of `trade.c`, save back to `market.c` |

The window reads the script variables by name (`goodBase`, `marketPrice`, `marketNorm`, `marketStock`,
`gold`, `cargo`, `portIsland`) and the `#define` numbers from `program/market.c` in the working
directory (the engine runs from `game/`). Opened windows are kept in `game/imgui.ini`.
