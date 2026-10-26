# Resolution in the settings menu and the switch to full screen

Investigated: the in-game settings page (`pdm-game\program\options.c`) offers a resolution, the
player clicks it, and the picture does not change. Below is the full path from the click to the
engine, what the engine really does, and where the path stops working.

**The state of the tree changed since:** the diagnosis stayed as written (sections 1–8, their line
numbers are of the untouched tree), the fix is section 9. The renderer part is verified by runs on Windows
(`engine\build\default\Debug\engine.exe`, 2026-10-26); the interface part is in the code and gets
its visual check next.
Tested on Windows with `engine\build\default\Debug\engine.exe`.

## 1. What the click does (the script side)

`pdm-game\program\options.c` is the page of the settings; it is opened by `screens.c`
(`[Options] of MENU.dll`).

- `OPTIONS_SIZES` — the list given to the player: `1280x720, 1366x768, 1600x900, 1920x1080, 2560x1440`.
- `Options_Current()` reads `Render.screen_x + "x" + Render.screen_y`: these script variables are
  written by the engine with the window it actually has (see §2).
- `Options_Apply()` does nothing if the size did not change; otherwise it writes the request into
  the global structure `Render` (`Render.SetScreen.x`, `Render.SetScreen.y`,
  `Render.SetScreen.full_screen`), clears `Render.restart` and reopens the page after
  `OPTIONS_REOPEN_MS` (200 ms).
- `Options_Reopen()` adds `" (после перезапуска)"` to the label `LB_RESOLUTION` when
  `sti(Render.restart) != 0` — the engine says that the size will appear only with the next start.

So the script only ASKS for a size. Everything else is the work of the engine.

## 2. What the engine does with this request (the renderer)

`engine\src\libs\renderer\src\s_device.cpp`, the service `DX9RENDER` (`VDX9RENDER`):

- `DX9RENDER::RunStart()` (line ~2914) at the start of the frame reads the attribute class
  `Render.SetScreen` (`pARender->GetAttributeClass("SetScreen")`, line 2919), takes `x`, `y`,
  `full_screen`, deletes the class and calls `DX9RENDER::SetScreen(width, height, fullscreen)`.
- `DX9RENDER::SetScreen()` (line 2855, declared in `engine\src\libs\renderer\inc\s_device.h:417`):
  resizes the window (`window->Resize`, `SetFullscreen`), forces the windowed D3DPP state and
  calls `ResizeBackBuffer(width, height)`.
  - if the back buffer got resized: sets the script variables `Render.screen_x`, `Render.screen_y`,
    `Render.full_screen`, `Render.restart = 0`, rewrites the keys `full_screen`, `screen_x`,
    `screen_y` of `engine.ini` (lines 2900–2904) and traces `"Render: the screen {}x{}{}"`.
  - if `ResetDevice()` cannot make a new back buffer: restores the OLD window size, sets
    `Render.restart = 1`, traces `"Render: the back buffer is not resized to %dx%d"` and
    `"Render: the screen {}x{} comes with the next launch"`, and writes the old size back to
    `engine.ini`, so the next start uses it.
- `DX9RENDER::RunStart()` also, for a windowed mode, when the size of the window differs from
  `screen_size`, calls `ResizeBackBuffer(size.width, size.height)` (lines 2929–2936).

The important thing about `SetScreen()`: it never touches the state of the interface library.
The renderer knows the new size, the interface (the menu, the panels, the zones of the mouse)
does not follow it.

## 3. Why the picture and the panels keep the old size

All the layout of the interface is computed ONCE, at the start:

- `XINTERFACE::Init()` (`engine\src\libs\xinterface\src\xinterface.cpp:170–176`) calls `SetDevice()`
  — this is the only call site of `SetDevice()`.
- `XINTERFACE::SetDevice()` (line 178): calls `LoadIni()` at line 199 — the only call site of
  `LoadIni()`; at line 207 `pPictureService->Init(pRenderService, dwScreenWidth, dwScreenHeight)`
  bakes the size into the service of pictures and strings; at lines 234–236 publishes the script
  attributes `ScreenWidth`, `ScreenLeft`, `ScreenTop` on the interface (the comment at 232–233 says:
  "with bDynamicScaling a script can spread a screen over a wide window").
- `XINTERFACE::LoadIni()` (lines ~1069–1169): at line 1078 `auto windowSize = core.GetWindow()->GetWindowSize()`
  — the ONLY place in `engine\src` where the size of the window is read live; at 1082/1083 the size
  of the screen `dwScreenWidth/Height`, at 1086–1089 the widening and the clamp, at 1091–1094
  `GlobalScreenRect` (the centering of the rect 800x600 in it); the branch at 1125
  `if (ini->GetInt(platform, "bDynamicScaling", 0) == 0)` overrides `fScale` and
  `wScreenWidth/Height`, `wScreenLeft/Top/Right/Down`; at 1150–1159 the matrices are built:
  `matp.m[0][0] = 2.f / dwScreenWidth * fScale`, `matp.m[1][1] = -2.f / dwScreenHeight * fScale`,
  `matv.m[3][0] = -(GlobalScreenRect.left + GlobalScreenRect.right) / 2.f`.
- `XINTERFACE::Realize()` (line ~330) every frame re-applies these matrices UNCHANGED:
  lines 351–353 `SetTransform(D3DTS_WORLD, matw)`, `(D3DTS_VIEW, matv)`, `(D3DTS_PROJECTION, matp)`.

Nothing calls `LoadIni()` or `SetDevice()` after `DX9RENDER::SetScreen()`. So after a change of
size made during a play the interface still maps its coordinates through the old `matp`/`matv`
and keeps the old `ScreenWidth`, `ScreenLeft`, `ScreenTop` — the panels stay where they were
for the size of the start.

Grep over `engine\src`: the string `GetWindowSize` is at one place only, line 1078, inside `LoadIni()`
— there is no code at all that could recompute the layout after a resize.

## 4. What `bDynamicScaling` is for

- The ini key `bDynamicScaling` of `[PC_SCREEN]` in `interfaces.ini`; the branch of it is at
  `XINTERFACE::LoadIni`, line 1125. `tools\pdm_ui.py:835–837` writes
  `"[PC_SCREEN]\nbDynamicScaling = 1\n"` for our screens; `docs\port-plan.md:166` and
  `docs\pdm-formats.md:326` note that without `[PC_SCREEN]` the rect of the screen is inverted
  and nothing draws.
- The whole effect of the flag is the branch at 1125 and the attributes at 234–236: it only lets
  the layout of the size of the start spread over a wide window. It does not create a change of
  size during a play.
- The scripts that were supposed to use these attributes: `pdm-game\program\map.c`,
  `Map_Layout()` (line 152) reads `GameInterface.ScreenLeft`, `ScreenTop` at lines 156/157 with
  `CheckAttribute` and `sti(...)`.

## 5. The evidence of the autotest and the crash

The autotest `TOWN_AUTO=14` (`options.c`, the hook in `main.c`, `#define OPTIONSAUTO_ID 14`,
`SCENE=sea`): opens the menu over the game, clicks `LB_OPTIONS` not with a synthetic mouse but
through the same message a click sends (`ievnt_command` → `Screen_Command` → `Options_Click`,
`screens.c:385` and `screens.c:402`), reads the attributes of the interface, then clicks
`LB_APPLY` for the next size of the list.

The run 2026-10-25 17:29, `compile.log`:

```
17:29:33.730 PDM options: autotest, the window 1920x1080, the interface of 0, restart 0
17:29:34.505 PDM screen: the menu over the game
17:29:36.422 PDM screen: mainmenu
17:29:37.265 PDM options: autotest, mainmenu LB_OPTIONS
17:29:37.281 PDM screen: mainmenu LB_OPTIONS -> options
17:29:39.078 PDM screen: options
```

After the last line the engine died: the exit code `-1073741819` = `0xC0000005` (access
violation); `error.log` is empty. `engine\build\default\Debug\crash_stack.txt` (written by
`crash_dump_handler`, `engine\src\apps\engine\src\main.cpp:91`, installed at line 206):
`exception_addr=00007FF69649A70F`, `module_base=00007FF6960E0000` (the offset `0x3BA70F` inside
`engine.exe`), `frames=41`, frames 7–23 inside the engine. There is no symbolizer on this
machine (`llvm-symbolizer`, `llvm-nm`, `addr2line` are missing), so the function of the crash
is not named yet.

Separating what is proven and what is not:

- PROVEN: after a change of size made during a play the interface does not recompute its layout —
  statically, because `GetWindowSize()` is at one place, `xinterface.cpp:1078` inside `LoadIni()`,
  whose only call is `SetDevice()` (line 199), whose only call is `Init()` (line 173).
- PROVEN: for the size of the start the layout of the interface is right (the menu draws fine at
  1920x1080, the size comes through `--size`, `main.cpp:215`, and `--windowed`, `main.cpp:219`).
- PROVEN: when the page of the settings is opened in a scene of the sea, the access violation
  happens. The same crash appears in the older autotest `TOWN_AUTO=13` (`save.c`, the steps 8–11
  open the same page), so the crash is in the page itself, not in the new code of the test.
- NOT PROVEN: which of two modes the change of size takes (A — the resize works, but the interface
  keeps the old matrices; B — `ResetDevice()` fails and `Render.restart = 1`, the size appears only
  with the next start). The test did not reach the trace of the click `LB_APPLY`, it died in the
  page before that.
- A mistake in the test, to fix it before it can prove anything: `Opt_AutoWidth()` printed 0 for
  `GameInterface.ScreenWidth`. `options.c` has no own object `GameInterface`; the entity is made in
  `menu.c:44`, `map.c:97`, `screens.c:83` (`CreateEntity(&GameInterface, "xinterface")`), so the
  read in `options.c` goes to another object. The read has to go through that very entity (as at
  `map.c:156–157`) or through `SendMessage`/`GetMessage` to the interface.

## 6. The transition to full screen

- At the start: `pdm-game\run.ps1` adds the engine options `--fullscreen` / `--windowed` /
  `--size <WxH>` (`main.cpp:215–219`; the flags are declared at 215, 217, 219), the variables
  `SCREEN`, `FULLSCREEN` of `run.ps1`; `pdm-game\game.ps1` zeroes `SCENE`, `TOWN`, `TOWN_AUTO`.
- During a play: `Options_Apply()` sets `Render.SetScreen.full_screen` → `DX9RENDER::SetScreen()`
  calls `SetFullscreen` and stores `Render.full_screen`; on success the keys `full_screen`,
  `screen_x`, `screen_y` of `engine.ini` are rewritten for the next start.
- The engine reads those keys of `engine.ini` at the start, after `fio->OpenIniFile`
  (`main.cpp:274`), before the interface measures the window.

## 7. What was to do (the plan; what got done is section 9)

1. Make the interface measure the window again after a resize: call `XINTERFACE::SetDevice()` /
   `LoadIni()` (or a new lighter function of recomputing) after a success of
   `DX9RENDER::SetScreen()`, so that `matp`, `matv`, `GlobalScreenRect`, `dwScreenWidth/Height`,
   `pPictureService` and the attributes at `xinterface.cpp:234–236` correspond to the new window.
   If the behaviour or the format of these attributes changes, `docs/ru/04-formats.md:122,124`
   must be updated in the same commit (nothing is changed there yet).
2. Find the access violation of the opening of the page of the settings in a scene of the sea
   (a PDB tool or a bisection of the autotest) — until that the test cannot prove the modes A and B.
3. Fix the read of the attribute in the autotest (the entity from `screens.c`), run
   `TOWN_AUTO=14` and read the modes A or B from `system.log`
   (`Render: the screen ...`, `Render: the back buffer is not resized ...`) and from the numbers
   of the trace.
4. Visual check by rule 10 with `storm-capture-crop`: the frames of the exact moments of the
   trace, cut to the area of the game, before and after the change of size; the captures in
   `C:\temp\shots`, never in the repository.
5. After any change of the engine: `tools/smoke-test/run.sh build/Debug/engine` must print
   `smoke test passed`; commit to the branch `miniaudio-sound`, push to the remote `fork` only,
   the message in English, no game content in the repository of the engine.

## 8. The commands that were run

```powershell
# from pdm-game/, the original game needed for the converted data
. "C:\corsairs-remake\pdm-game\local.ps1"      # $env:PDM = 'C:\Program Files\1C\Корсары'
$env:SCENE='sea'; $env:TOWN_AUTO='14'
& powershell -NoProfile -ExecutionPolicy Bypass -File "C:\corsairs-remake\pdm-game\run.ps1"
# the logs: C:\Users\User\Documents\My Games\Sea Dogs\Logs (compile.log, system.log, error.log)
```

The result: `engine exited with -1073741819 (0xC0000005)`. The runs `SCENE=menu` and `SCENE=sea`
with `TOWN_AUTO=0` did not crash; the runs `TOWN_AUTO=13` and `TOWN_AUTO=14` crash at the page of
the settings.

## 9. What the fix does (the resolved state)

Two places of the code were wrong: the renderer refused the new size, and the interface never
measured the window again. Both are changed in `engine\src\libs`; the renderer part is proven by
runs of 2026-10-26 with `engine\build\default\Debug\engine.exe`.

### 9.1 The renderer: the refused Reset of a new size

`DX9RENDER::ResizeBackBuffer()` (`s_device.cpp:2778`) reaches `DX9RENDER::ResetDevice()`
(`s_device.cpp:2821`) with a `d3dpp` that is already right: the client area of the window equals
the requested size, the format is the desktop one, `MultiSampleType` is NONE,
`D3DPRESENT_INTERVAL_IMMEDIATE`, `Flags = 0`. The device is always windowed — `InitDevice` forces
`d3dpp.Windowed = TRUE` (`s_device.cpp:757`), "full screen" is a window covering the desktop. For a
windowed device the FIRST `d3d9->Reset(&d3dpp)` that changes the back buffer size answers
`D3DERR_INVALIDCALL` (`0x887E7804`). It is not the parameters of the present: swap effect COPY,
`D3DPRESENT_INTERVAL_ONE` and `D3DPRESENTFLAG_LOCKABLE_BACKBUFFER` were each tried with the same
size and all answered `0x887E7804`.

After the refusal the device is not dead but waiting: `d3d9->TestCooperativeLevel()` returns
`D3DERR_DEVICENOTRESET` (`0x887E7801`), and the SECOND `d3d9->Reset(&d3dpp)` with the very same
parameters returns `SUCCEEDED` and the back buffer comes to the requested size. The frame loop
already uses this rule for a device lost from outside — `LostDeviceSentinel` (`s_device.cpp:109`)
asks `TestCooperativeLevel()` and only then Resets. So `DX9RENDER::ResetDevice()` retries the
Reset once when the cooperative level says `DEVICENOTRESET`; `LostRender()` (`2614`) before it and
`RestoreRender()` (`2654`) after it stay as they are — all resources of `D3DPOOL_DEFAULT` are still
released before the Reset, as `docs/ru/07-debugging.md:76` requires.

The proof of a run (`engine\tools\smoke-test\program\smoke.c`: 800x600 at the start, a request for
1280x720 at frame 60, for 960x540 at frame 110) — `system.log`:

```
Render: back buffer 1280x720
Render: the screen 1280x720
Render: back buffer 960x540
Render: the screen 960x540
```

with the traces of the two Reset attempts (the first `hr -2005530516`, the cooperative level
`-2005530519`, the second `hr 0`), and `compile.log` reaching `SMOKE: OK, 180 frames rendered`:
the frames after every resize are drawn and the run exits normally, no `0xC0000005`, no new
`crash_stack.txt`. The access violation of §5 is a different path (the page of the settings in a
scene of the sea) and stays open.

### 9.2 The interface: the layout measured again

`XINTERFACE::Realize()` (`xinterface.cpp:337`) compares every frame the size the device renders
into with the window `LoadIni()` measured (`dwWindowWidth/Height`, `xinterface.h:46–48`), and when
they differ it calls `LoadIni()` again (`xinterface.cpp:353`): `matp`, `matv`, `GlobalScreenRect`,
`dwScreenWidth/Height` and the script attributes `ScreenWidth`, `ScreenLeft`, `ScreenTop`
(`xinterface.cpp:1261–1263`) come to the new window. The block was dead code before
(`if (false && ...)`). The texture of the mouse cursor is made in `LoadIni()`, so a repeated
`LoadIni()` releases the handle of the previous one (`xinterface.cpp:1225`) before it makes the
new texture, and `~XINTERFACE()` (`xinterface.cpp:158–161`) releases the last one.

The layout of a size comes from `interfaces.ini`: the section `PC_SCREEN_W_H` is picked by the
aspect ratio within 3%, so a demo that resizes needs a section for the new size
(`demos\menu-control\resource\ini\interfaces\interfaces.ini` has `PC_SCREEN_1280_720` now). The
success branch of `DX9RENDER::SetScreen()` (`s_device.cpp:2891`) sets `Render.restart = 0`, so the
page of the settings no longer promises "(после перезапуска)" for a size the desktop hosts. The
visual check of the panels, the fonts and the cursor for a mid-run resize is 9.4 of this section.

### 9.3 The window stays inside the desktop when the size changes

`SDLWindow::Resize(int,int)` (`engine\src\libs\window\src\sdl_window.cpp:88`) asked for a size
bigger than the monitor used to be trusted as is, and SDL changes only the size of a window: it
keeps the left upper corner, so the right and the lower edges of a bigger window hang over the
desktop. The function now clamps the requested size to `SDL_GetDisplayBounds` of the display the
window stands on (`SDL_GetWindowDisplayIndex`) and puts the window into the center of that display
with `SDL_WINDOWPOS_CENTERED_DISPLAY`, the same macros the constructor of `SDLWindow` uses to make
the window centered at the start (`sdl_window.cpp:20`). `DX9RENDER::SetScreen()` (`s_device.cpp:2891`)
re-reads the real size with `window->GetWindowSize()` after it, so the back buffer gets the size the
window really has, not the one the script asked for.

Measured from the desktop frames of the run of `demos\menu-control` on a 2560x1440 desktop
(captures in `C:\temp\shots`, the client area matched pixel for pixel against the window capture):

```
before the resize  client area 800x600  at 880,420  margins 880/880 and 420/420
after the resize   client area 1280x720 at 640,360  margins 640/640 and 360/360
                   right edge 1920 <= 2560, lower edge 1080 <= 1440
```

### 9.4 The visual check of the interface (rule 10)

Frames of the exact `Trace` moments of the run, the client area captured with gdigrab
(`-f gdigrab -i title="Storm menu control autotest"`) before the resize (800x600) and right after
it (1280x720), put side by side in `C:\temp\shots\burst\pre-vs-post.png`:

- the title block of the menu takes 0.368 of the screen height in both frames, so the layout is
  measured again for the new window and not stretched;
- the glyphs of the item list go from about 34 px to about 55 px high, the ratio 1.6 equals
  1280/800, the fonts follow the window;
- the cursor arrow and the boxes of the buttons are bigger in the second frame too. The boxes
  differ also because the mouse hovered over another item in the two frames, that is the state of
  the run, not the layout.

### 9.5 What stays open

- The traces marked TEMP in `s_device.cpp` (the dump of `d3dpp`, the lines of the two Reset attempts
  and of `TestCooperativeLevel`, `TEMP resize` in `ResizeBackBuffer`, `TEMP restore` in
  `RestoreRender`) and the TEMP markers of the diagnosis of section 10 went away before the commit;
  the retry itself stays, with a comment that is not marked TEMP.
- `engine.ini` of `tools\smoke-test` and of `demos\menu-control` is rewritten by `SetScreen` at the
  end of a run (`WriteEngineIniKey`, `s_device.cpp:2864`), both files must read `screen_x = 800`,
  `screen_y = 600` before the commit, as in the tree before the fix.
- Whether the centering is also right for a window that covers the desktop
  (`full_screen = 1`, `SDL_WINDOW_FULLSCREEN_DESKTOP`) stays untested: SDL already pins such a
  window to the whole display, and its size cannot go over the edges.
- Whether a bordered window (`window_borders = 1`) leaves its title bar outside the desktop after
  the centering stays untested; the demos run with the borders of SDL only.

## 10. The crash of the resize inside a live scene (the resolved state)

The crash of §5 (`0xC0000005`, exit `-1073741819`) came back once the resize itself started to
succeed, in `pdm-game` runs that change the size on the page «Настройки» over a loaded scene:

```
# from pdm-game/, the autotest of the options page over a town (TOWN_AUTO = OPTIONSAUTO_ID = 14)
. C:\corsairs-remake\pdm-game\local.ps1
$env:SCENE = 'town';  $env:TOWN = 'City_HighRock';  $env:TOWN_AUTO = '14';  $env:SCREEN = '1366x768'
& C:\corsairs-remake\pdm-game\run.ps1 C:\corsairs-remake\engine\build\default\Debug\engine.exe
```

No key presses: `pdm-game\program\main.c` calls `Opt_AutoStart()` for `TownAuto == OPTIONSAUTO_ID`
(`main.c:21`), and `pdm-game\program\options.c:192` drives the resolution of the page over the game.
The whole `0xC0000005` was two owners of state that a device Reset leaves dead.

**10.1 The handler of a model whose geometry never loaded.** The town run dies in
`MODELR::LostRender()` (`model.cpp`) with `this` valid and `root == nullptr`: a `modelr` entity of a
model the loader refused keeps `root` null (`model.cpp:MSG_MODEL_LOAD_GEO`), in the run
`system.log` shows the loader line `resource\models\ships\pink\pink.gm: can't open geometry file`
and `SHIP::Mount: failed to load model 'ships\pink\pink'` before the resize. `root->ReleaseGeometry()`
then enters `NODER::ReleaseGeometry` (`node.cpp`) with a null `this` and faults on the first member
read. `MODELR::LostRender()` and `MODELR::RestoreRender()` guard `root` with `if (root)` — the same
guard `MSG_MODEL_RELEASE` and `MSG_MODEL_RESTORE` make for the same entity (`modelr.h:97` declares
both stage handlers). Fixed in `engine\src\libs\model\src\model.cpp`, committed here.

**10.2 The handles of a D3DX effect cached across the Reset.** After 10.1 the town run still dies,
and with `STORM_LOG_FLUSH=1` (`diagnostics\src\logging.cpp:36`, the switch that makes every message
reach the file at once) the tail of `system.log` pins the fault: the last line is the marker before
the block of constants of the `windleaf` effect of `MODELR::Realize` (`model.cpp`), so the
instruction that faults is inside that block, `eff->SetMatrix(hWVP, &m)`, and `crash_stack.txt`
puts `exception_addr` into `d3d9.dll`. The owner of the stale state is the cache of `D3DXHANDLE`s
resolved once and kept across the Reset: `DX9RENDER::RestoreRender()` calls
`DX9RENDER::RecompileEffects()` (`s_device.cpp:2765`), which does `effects_.release()`
(`effects.cpp:Effects::release` — `fx->Release()` for every effect, `effects_.clear()`) and compiles
every `.fx` again, while `DX9RENDER::GetEffectPointer()` (`s_device.cpp:4175`) hands the NEW object
out. A handle taken before the Reset points into the freed effect object. The rule the committed
code already follows: `Grass::RestoreRender()` (`grass.cpp:726`) calls
`CreateVertexDeclaration()` (1032–1060) again, which re-takes `fx_` and re-resolves `hgVP_`. The
`windleaf` handles of `model.cpp` follow the same rule — the nine handles moved to file scope and
nulled in `MODELR::RestoreRender()`, resolved again on the next frame.

**10.3 What the runs show now.** All three scenarios exit `0`, `error.log` is `0` bytes and there is
no `crash_stack.txt`; `system.log` reaches the resize and keeps drawing after it:

```
Render: back buffer 1600x900
Render: the screen 1600x900
Interface: the window is 1600x900 instead of 1366x768, the screens are laid out again
Using PC_SCREEN parameters
```

- `SCENE=menu-newgame TOWN_AUTO=14 SCREEN=1366x768` (the page «Настройки» over the new game):
  `compile.log` shows `PDM options: the screen 1600x900, full screen 0`, then the four lines above,
  exit 0.
- `SCENE=town TOWN=City_HighRock TOWN_AUTO=14` (the location that crashed): exit 0, and after the
  resize lines the town geometry and the vegetation geometry (3 objects, 115472 triangles of
  `resource\models\locations\city_highrock_veg.gm`, the model with `useWind`) draw again.
- `SCENE=sea TOWN_AUTO=14`: exit 0, same lines (this is the scenario of §5).

**10.4 What stays open.** The fix of 10.2 sits in the wind feature of the working tree
(`src\techniques\windleaf.fx`, `demos\wind-vegetation`, `MSG_MODEL_SET_WIND` in
`shared_headers\include\shared\messages.h`), which is in progress and not part of this commit; the
committed tree has no `windleaf` effect at all, so it cannot show this crash. The rule itself —
handles of a recompiled effect must be re-resolved in the `restore_render` handler — is written into
`docs/ru/07-debugging.md`. Whether an entity that caches effect handles of its own (`Grass` does it
through `CreateVertexDeclaration`, `BmFont` keeps `fx_` from `InitShader`) draws the same after
every resize in every location was not checked frame by frame.

## 11. The world drawn in clip units after the resize (the resolved state)

After the crashes were fixed, the full game showed the wrong picture once the size was changed
without a restart: near objects filled the screen, everything further away was cut away and only the
flat sky-blue of the background remained — the reported "draw distance" and "clipping" symptom
(`C:\Users\User\Documents\My Games\Sea Dogs\Screenshots\2026-10-26_11-49-44.mp4`).

**11.1 What is stale.** `d3d9->Reset` puts the three transforms of the device — WORLD, VIEW and
PROJECTION — back to identity. `DX9RENDER::RestoreRender()` (`s_device.cpp`) restores the render
targets, the vertex/index buffers of the registry, the sampler and stage states and the lights
(`SetCommonStates()`), but no transform. Two of the three are set on every frame anyway: VIEW by the
camera (`DX9RENDER::SetCamera`, `s_device.cpp:2085` two-argument and `s_device.cpp:2135` look-at)
and WORLD by every module that draws. The third, the projection, is asked for rarely:
`LocationCamera::Init()` sets it once per location (`location_camera.cpp:104`), a script message
sets it (`location_camera.cpp:414` `MSG_CAMERA_SET_PERSPECTIVE`), a dynamic fog event re-sets it
(`location_camera.cpp:669` `ProcessDynamicFov`), the sea cameras set it every frame
(`ship_camera.cpp:183`, `deck_camera.cpp:284`, `free_camera.cpp:97`). A land location with its static
camera does none of these on an ordinary frame, so after the resize the device keeps the identity
projection.

The proof of the run (`SCENE=menu-newgame` / `SCENE=town`, probes around `DX9RENDER::ResetDevice`
removed after): `GetTransform(D3DTS_PROJECTION)` reads `1.3361179 2.3764803 1.000025 1` before the
Reset and `1 1 1 0` after it, and no `SetPerspective` line follows the resize. With an identity
projection the coordinates of the world ARE the coordinates of clip: the objects one unit around the
camera fill the screen and everything beyond one unit is clipped away — which is what the frames show.

**11.2 The fix.** `DX9RENDER::RestoreRender()` (`s_device.cpp`) makes the projection again right
after the states are restored: `SetPerspectiveMatrix(Fov, -1.0f)`. `DX9RENDER::SetPerspective`
(`s_device.cpp:2185`) cannot be called a second time — it multiplies the angle by `FovMultiplier`
and stores the product into `Fov` (`s_device.cpp:2213`), so calling it on the kept `Fov` would
multiply the multiplier twice; the body without that line is the new private
`DX9RENDER::SetPerspectiveMatrix` (declared in `engine\src\libs\renderer\src\s_device.h`). The
aspect ratio is passed as the default `-1.0f`, which makes the helper take it from the new
`screen_size` (`s_device.cpp:2194`) rather than from the old window. The field of view itself is kept
by the renderer (`float Fov`, `s_device.h:471`) and needs no help from the modules.

**11.3 What the runs show.** The scenarios of §10 exit `0`, `error.log` is `0` bytes, and the frames
before and after the resize (captured with `storm-capture-crop`, cropped to the game area) show the
town of `City_HighRock` drawn the same way after the resize as before it — the ground, the houses and
the vegetation at their normal size, no blue field, no magnified hero; the interface is laid out for
the new window, as §9 already showed. The same rule is written into
`engine\docs\ru\07-debugging.md` next to the other Reset-after-resize pitfalls.
