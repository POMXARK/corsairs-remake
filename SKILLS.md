# Skills для Claude Code в этом репозитории

Папа с «skills» в形式ате Claude Code: each skill lives in its own folder
`.claude/skills/<name>/SKILL.md` with YAML front matter (`name`, `description`).
This file is the index: for every research task we actually perform during the work on the
remake it names the file that carries the instructions, the method it prescribes and the
purpose it serves. Add a row here when a skill is added; delete the row when the skill stops
applying. The skills below were written and used during the vegetation fix, so the commands in
them are the ones that were verified on this machine.

## Skills of the repository

| Skill (file) | Method it prescribes | For what purpose |
| --- | --- | --- |
| `storm-land-scenario-control` — `.claude/skills/storm-land-scenario-control/SKILL.md` | The script VM of the engine: which `MSG_*` messages move the hero, turn the camera, change the location; their format strings and the engine code that reads them; the tables of point types and links of a location | To drive the game in a test scenario without simulated key presses: walk the hero through the streets, look at a chosen place, go through a door into another location, all from `PostEvent` chains in `autotest`-style script code |
| `storm-menu-control` — `.claude/skills/storm-menu-control/SKILL.md` | `MSG_INTERFACE_MENU_ACTION` `"lss"` and the command names of `xutil.cpp`, the ini `command = <cmd>,select:<node>` lines, how `CINODE::DoAction` / `FrameProcess` resolve the chain and move the current node, `MSG_INTERFACE_GET_CURRENT_NODE` `"le"` and the `"ievnt_command"` event as the read-back of the menu, the `PostEvent`/`SetEventHandler` harness of the autotest and its script-VM traps | To select a main-menu item and to move the selection up and down the list from a script, with the checks of both the navigation and the selection, the no-ops on the edges of the list and the frames that show the highlighted item |
| `storm-capture-crop` — `.claude/skills/storm-capture-crop/SKILL.md` | `gdigrab` of the game window and of the desktop with ffmpeg, the frame extraction at the timestamps the script printed into `compile.log`, the crop of the game area, the contact sheet and the before/after collage | To evaluate the finished work visually: get the frames of the exact moments of the scenario, crop them, compare the frames before and after the fix |

The recipes below are research steps we repeat often. They are documented here so the next agent
does not re-derive them; they do not have their own skill folder because each is a single lookup,
not a procedure with its own commands.

## Recipe: where does the black geometry get its colour from

- Files: `engine\src\techniques\<technique>.fx`, `engine\src\libs\model\src\model.cpp`,
  `engine\src\libs\geometry\src\geom_static.cpp`, `engine\src\libs\renderer\src\s_device.cpp`.
- Method: follow the chain object → material → texture. `GEOM::Draw()` takes
  `material[object[o].material]` (`geom_static.cpp`), `GEOM_SERVICE_R::SetMaterial` calls
  `RenderService->TextureSet(0, mt.texture[0])` (`geometry.cpp`), which in the fixed-function
  services does `d3d9->SetTexture(stage, ...)` (`s_device.cpp`). An `.fx` technique with an HLSL
  sampler is NOT fed by that call: the sampler must be bound through the effect API
  (`ID3DXEffect::SetTexture` on the handle of `GetParameterByName(nullptr, "Texture0")`), the
  accessors are `DX9RENDER::GetBaseTexture(iTexture)` and the per-material hook
  `GEOS::MATERIAL_FUNC` (the argument of `GEOM::Draw`, invoked once per object).
- Purpose: find why a model renders as a black silhouette. An unbound effect sampler and a black
  vertex colour look the same on the frame and are fixed differently; the alpha cutouts in the
  silhouette tell that the texture itself is fine.

## Recipe: read a `.gm` geometry file without the engine

- Files: `engine\src\libs\geometry\src\rdf.h` (the format), the model itself, for instance
  `pdm-game\resource\models\locations\city_highrock_veg.gm`.
- Method: `RDF_HEAD` is 72 bytes: eleven `int32` (`version, flags, name_size, names, ntextures,
  nmaterials, nlights, nlabels, nobjects, ntriangles, nvrtbuffs`) and then seven floats — the
  bounding box `size`, `center` and `radius` at offset 44. The section order is header, names
  (`name_size` bytes each), textures, materials, lights, labels, objects, triangles, vertex
  buffers, vertices, and the BSP block when `flags` has `FLAGS_BSP_PRESENT`. `CVECTOR` is three
  floats, `#pragma pack(1)`, so the records have the exact sizes: material 56, object 104,
  triangle 6, vertex buffer 8.
- Purpose: get the extent, the number of objects and the names of materials and textures of a
  converted model before loading it — for instance to know how big the vegetation field is and
  which materials and textures it expects (`tree3`, `tree2`, `pdm_bark.tga`, `leaves.tga` in the
  city vegetation of High Rock), and to check that the conversion produced the expected geometry.

## Recipe: what the camera actually accepts

- Files: `engine\src\libs\location\src\location_camera.cpp`, `engine\src\libs\shared_headers\include\shared\messages.h`.
- Method: read `LocationCamera::ProcessMessage` for the `case` of each message and take the
  argument types from the code, not from the header comment (the comment of `MSG_CAMERA_MOVE`
  says `"lffff"` while the land camera reads one float). The camera is an orbit:
  `ax = 0.4f` is the default pitch that looks steeply down, clamped to `[-1.0, 0.75]`, `radius = 3.0f`
  is the distance; `MSG_CAMERA_TOPOS` takes the position of the camera and keeps it looking at the
  followed character, so standing the camera at the hand of the hero turns the view to that side.
- Purpose: control the camera in a test scenario: a level eye-level view instead of the fixed top-down
  one, the view turned to the right or to the left of the hero, a chosen distance.

## Recipe: pick the places of a scenario from the data, not from literals

- Files: `pdm-game\program\data\pdm_world.c` (the location blocks), `pdm-game\program\town.c`
  (`Town_ExitAt`, `Town_Tick`, `Town_ExitGo`, `Town_CanGo`), the engine side `location.cpp`.
- Method: take the block of the location id, for example `PdmLocations.City_HighRock`, and read
  its points: `type = 1` is the box of an exit with a `link` ("sea", "tavern", "store", "shipyard",
  "townhall"), `type = 3` is a walking point of the street, `type = 4` is the marker just outside a
  door. The box of an exit is `bx0, bz0, bx1, bz1`, and `Town_ExitAt` counts the hero inside it with
  the reach `TOWN_EXIT_REACH` added. A walk target must be a node of the AI patch, so the marker of
  the door is used, not the centre of the box.
- Purpose: make the test walk the real streets and enter a real location (the tavern, the shop, the
  farm) instead of invented coordinates, and make the change of the location verifiable.

## Recipe: prove that the scenario reached its moments

- Files: `C:\Users\User\Documents\My Games\Sea Dogs\Logs\compile.log`, `error.log`, `system.log`.
- Method: the script's `Trace(...)` lands in `compile.log` with the wall-clock timestamp; the
  loader prints the byte sizes and the triangle counts in `system.log`; a script that does not
  compile leaves its `COMPILE ERROR in <file>(<line>)` lines in `error.log`, and an empty
  `error.log` is the evidence that the script code is valid. Read the traces with their times and
  match them against the recording, see the `storm-capture-crop` skill for that.
- Purpose: tell a passing test from a run that silently did nothing: the frames of a run whose
  traces never appeared are not evidence.

## Rules that bound all of the above

- One action per turn; after a fix or a test stop and ask whether to go to the next step
  (`AGENTS.md` of the repository root).
- Never invent engine behaviour: cite `file.cpp:function`; the engine guide in `docs\ru\*`
  (`01-architecture`, `02-game-layout`, `03-scripting`, `04-formats`, `05-modules`,
  `06-recipes`, `07-debugging`, `08-linux-build`, `09-editor`, `10-editor-roadmap`) holds the
  same facts in the prose form and must be updated when a format or a behaviour changes.
- Never drive the game with simulated key presses; the scenarios are scripted (`PostEvent` with
  delays), see the `storm-land-scenario-control` skill.
- Captures do not go into the repository: keep the footage and the frames in `C:\temp\shots`.
- The engine submodule commits in English with the template in `engine\AGENTS.md`, on the branch
  `miniaudio-sound`, pushed only to the remote `fork`.
