---
name: storm-land-scenario-control
description: Use when the hero or the camera of a Storm engine location (a town, a tavern) must be driven from a script or an autotest, never by simulated key presses. Documents the MSG_CHARACTER_* messages (position, facing, turn to a point, teleport, walk task, head look) and the MSG_CAMERA_* messages (follow, observe from a point, pitch, radius) with their format strings and the engine code that reads them, the facing convention of the hero (sin ay, 0, cos ay), how to put the camera in front of the hero's face, and the verified pitfalls of the script harness (SetEventHandler for every PostEvent name, a MSG_* name must be #defined in town.c, the Turn animation delay).
---

# Driving the hero and the camera of a location from a script

The rule of the repository stays first: never fake key presses (`xdotool`, synthetic controls).
A scenario is a script that posts events with delays and sends messages to the hero (`TownHero`)
and to the camera (`TownCamera`) of `pdm-game/program/town.c`; the engine then runs the code a
player's input would run. The menu counterpart is the `storm-menu-control` skill.

## The facing of the hero

`Character::Turn(dx, dz)` (`storm-engine/src/libs/location/src/character.cpp:1318`) is
`ay = atan2(dx, dz)`. So the hero looks along **`(sin ay, 0, cos ay)`** and his right hand is
`(cos ay, 0, -sin ay)`; `town.c` (the wind check, `Town_WindWalk`) uses the same. A camera that
stands at `hero + (sin ay, 0, cos ay) * r` sees his face, at `hero - (sin ay, 0, cos ay) * r` his
back. Do not derive the direction from a frame of a camera whose mode you have not checked: the
default camera follows the hero from behind.

## Messages to the hero (`engine/src/libs/shared_headers/include/shared/messages.h`)

| Purpose | Message | Format | Engine code |
|---|---|---|---|
| position of the hero | `MSG_CHARACTER_GETPOS` 30202 | `"leee"` (x, y, z by reference) | `character.cpp` |
| facing of the hero | `MSG_CHARACTER_GETAY` 30203 | `"le"` | `character.cpp` |
| move to a point | `MSG_CHARACTER_TELEPORT` 30210 | `"lfff"` | |
| move and face | `MSG_CHARACTER_TELEPORT_AY` 30211 | `"lffff"` (x, y, z, ay) | `town.c:Town_Teleport` |
| turn to a point | `MSG_CHARACTER_TURNBYPOINT` 30342 | `"lfff"` (y is ignored) | `character.cpp:zTurnByPoint` (3572) |
| turn to a character | `MSG_CHARACTER_TURNBYCHR` 30341 | `"li"` with `&object` | `character.cpp:zTurnByChr` (3562) |
| turn to an angle | `MSG_CHARACTER_TURNAY` 30343 | `"lf"` (absolute ay) | `character.cpp:Turn(float)` (1333) |
| save / restore the facing | `MSG_CHARACTER_TURNPUSH` 30344 / `TURNPOP` 30345 | `"l"` | `character.cpp` |
| walk (NPCharacter hero of an autotest) | `MSG_NPCHARACTER_SETTASK` 30400 | `"lsfff"`, `"Goto point", x, y, z`; `"ls"`, `"Stay"` | `town.c` |
| the head follows a character | `MSG_CHARACTER_HEADLOOK_CHARACTER` 30382 | `"li"`; `HEADLOOK_DEFAULT` 30380 `"l"` | `town.c` |

`Turn` is animated: the hero needs about a second to finish a half turn, so wait (1.5 s) before
the camera goes in front of him. `TURNBYPOINT` is the easiest way to make him face a place:
choose the camera point first, turn the hero to it, then put the camera there.

## Messages to the camera (`location_camera.cpp:ProcessMessage`, line 360)

| Purpose | Message | Format | What it does |
|---|---|---|---|
| the target | `MSG_CAMERA_SETTARGET` 30500 | `"li"` with `&object` | the character the camera looks at; send it before `TOPOS` |
| chase mode (the default) | `MSG_CAMERA_FOLLOW` 30510 | `"l"` | goes back to following from behind |
| observe from a point | `MSG_CAMERA_TOPOS` 30512 | `"lfffl"` (x, y, z, no-morph) | `ExecuteTopos`: `camPos` = the point, `lookTo` = the target + eye height; the last argument 1 jumps there, 0 glides from the old place |
| pitch | `MSG_CAMERA_MOVE` 30513 | `"lf"` | the vertical angle of the follow camera |
| distance | `MSG_CAMERA_SET_RADIUS` 30521 | `"lf"` | the radius of the follow camera |
| field of view | `MSG_CAMERA_SET_PERSPECTIVE` 30530 | `"lf"` | |
| free flight / stop | `MSG_CAMERA_FREE` 30514 `"l"`, `MSG_CAMERA_SLEEP` 30520 `"ll"` | | |

A close-up of the face (the check of the eyelid blink): the camera 0.9 m in front of the hero at
y + 1.8 and `TOPOS` with the last argument 1. See `pdm-game/program/autotest/town_face.c`
(`TOWN_AUTO=40`, `pdm-game/autotest/scenarios.txt` line `town-face`).

## The harness: three traps found while writing `town_face.c`

1. **A MSG name must be `#define`d in `town.c`.** The scripts do not read `messages.h`; the block
   `#define MSG_... 30xxx` at the top of `town.c` is the list. An unknown name is a compile error
   `Invalid Expression` on the line of its use. Add the name there with the value of `messages.h`.
2. **Every `PostEvent` name needs `SetEventHandler("Name", "Name", 0)`.** Without it the event is
   dropped without any message (no error in `error.log`, the function never starts). The handlers
   of the town are registered in `town.c` next to `Town_WindWalk`; the sea ones in `sea.c`.
3. **The hook of a scenario is one `else if (TownAuto == N)` in `town.c` after the load** and its
   marker is a `Trace("PDM …")` line; `ExitProgram()` ends the run. A scenario without its marker
   in `compile.log` is a failed test (`autotests.sh`).

## Running and checking

* `pdm-game/autotests.sh <engine> town-face` runs the scenario headless and checks the marker
  `PDM face: autotest done` and an empty `error.log`.
* `SCENE=town TOWN=City_HighRock TOWN_AUTO=40 pdm-game/shots.sh <engine> <out dir> 32 <t> …`
  records it (the engine is `$W/build/Debug/engine`) and writes the frames at the given seconds;
  look at them (the view must be the hero's face, not his back). Run it in the background.
* The logs: `~/.local/share/Akella/Sea Dogs/Logs/{compile,error,system}.log`; the compile
  errors of the scripts go to `error.log` and name the file and the line.
* Looking for a process with `pgrep -f shots.sh` from a command that contains that text finds the
  command itself; match with a bracket (`[s]hots.sh`) or on `ps -eo args`.
