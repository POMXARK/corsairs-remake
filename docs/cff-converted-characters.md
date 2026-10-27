# Characters: how the original game rendered them, what the port fixed, and how lighting works in both engines

Investigation and diagnostic analysis, rewritten after the conversion round. The screenshots that
drove this work show the **original** *Sea Dogs / Corsairs* (PDM 1.061) look: Venta/Kalix town
streets with soft warm lighting and smooth shading gradients on the hero and NPCs — no facets, no
hard shading angles. That is the look the converted port must reproduce. An intermediate build of
the port showed two defects — sharp facets and characters painted in unnatural rainbow hues — and
this document records the cause of each and what was changed.

## 1. How the original rendered these characters

The originals are `.cff` files of Cyclone's Storm 1 format:

- A CFF vertex is a quantized position, a quantized UV, and 3 trailing bytes
  (`docs/cff-format/README.md:58-66`; `seadogs-file-formats/ksy/cyclone.ksy:cff_mesh_vertex`).
  There is **no normal field**: the file carries no shading data at all.
- The 3 trailing bytes are **padding, not colour**. A byte dump of `RESOURCE/MODELS/CHARACTERS/*.cff`
  (hero, soldier_eng, devka, citizen1, traktir_man) shows all three bytes statistically uniform
  over 0..255 (means ≈124/127/106, min 0, max 255) with **zero near-grey triples** across all four
  sampled characters. Authored vertex tints would cluster near grey (a renderer multiplies them);
  uniform noise is unfilled structure. The old format spec calls this slot `vertex_color`, but the
  shipped files leave it uninitialized.
- The face winding in a CFF is inconsistent — mirrored parts keep the winding of the source and
  face inwards — and the original drew them **without back-face culling**
  (`docs/pdm-formats.md:156`), so a mis-wound part was hidden by its front copy rather than
  culled away.

Consequently every pixel shade of an original character was **generated at draw time** by the
original renderer. What the original frames show — smooth gradients across low-poly faces, no
facets, warm even light — means the original renderer averaged vertex normals across faces at load
time (a triangle soup welded by position) and lit the mesh with a soft warm key light. This is an
inference from the format (which cannot contain anything else) and from the observed frames; the
closed-source renderer itself was not read.

## 2. What the conversion got wrong and how each defect was fixed

| Defect in the port | Root cause | Fix applied |
|---|---|---|
| Characters painted in unnatural rainbow hues | The CFF padding bytes were baked into the `.gm` vertex colour. The engine multiplies that colour against the texture, so per-vertex noise becomes per-vertex hue | Padding is not colour: the vertex colour stays at the neutral grey of `engine/demos/common/storm_formats.py:VERTEX_COLOR` (`0xFF808080`). `cff2gm.py:cff_to_meshes` no longer builds a per-mesh colour list |
| Sharp facets on characters (unlike the smooth original) | The CFF is a **triangle soup**: every face owns its three vertex records, so `cff2gm.py:compute_normals` had nothing to average and returned per-face normals — flat shading | `cff2gm.py:cff_to_meshes` now welds records whose quantized `(x,y,z)` is identical and averages normals over the weld, the same construction the original renderer must have used. The vertex array keeps one record per face corner (UVs differ per corner), so the weld drives normal averaging only |
| An intermediate build exploded into shards of triangles | The weld ids were used as triangle indices while the vertex array still emitted one record per corner — indices and geometry disagreed | Faces keep the raw corner order; `posweld`/`weldpos` feed `compute_normals` alone. Geometry is byte-identical to the intact build; only normals change |
| Character generation tangled into the world converter | `tools/pdm_world.py:World.characters()` carried its own copy of the model loop and the parallel job list | Generation lives in `tools/pdm_character.py:convert_all` (indexes `MODELS/CHARACTERS` + `WORLDS/CHARACTERS`, walks `WORLDS/anim_types.idf`, runs a 4-worker pool, returns per-name report); `pdm_world.py` delegates to it; the same code runs standalone as `python tools/pdm_character.py "<PDM>" <out-resource> all` |

Verified at the byte level on the rebuilt `resource/models/characters/*.gm`: every vertex colour
stamp is `0xFF808080` (`hero` 1388 vertices, `soldier_eng` 1202, `devka` 1188, `citizen3` 1040 —
zero non-neutral stamps), and every sampled face is smooth-shaded (corner normals differ from the
geometric face normal: `hero` 220/220, `soldier_eng` 187/187, `devka` 170/170, `citizen3` 163/163
smooth, 0 flat). The picture itself was checked by the town-scenario frames of the port run.

## 3. Lighting: original renderer versus this engine

### Original game (inferred from format + frames, code not read)

- No normals and no usable vertex colour in the data → shading is computed by the renderer each
  frame: welded averaged normals, then one soft warm key light over the town (the original ran on
  a fixed-function palette pipeline — Direct3D 6/7-era terrain and models share the same tint).
- No culling: both facings of every triangle are drawn, so inconsistent winding never holes the
  model.

### New engine (all facts cited from `engine/src/...`)

- The Storm `.gm` (RDF) format stores **normal and colour per vertex**
  (`engine/src/libs/geometry/src/rdf.h:RDF_VERTEX0` line 212; `RDF_AVERTEX0` line 251 with
  pos/weight/boneid/norm/colour/uv). Unlike CFF, this format *can* carry shading — so the
  converter, not the renderer, must supply the original's welded averaged normals.
- The `RDF_VERTEXBUFF` descriptor counts **bytes, not vertices**
  (`rdf.h:203-207`), and `storm_formats.py:write_gm` writes it that way (line 283).
- A skinned character passes through `engine/src/libs/model/src/model.cpp:VBTransform` (line 62):
  position and normal are skinned, the colour is copied untouched (`model.cpp:154`).
- Characters are drawn with the `Animation` technique (`engine/src/techniques/animation.fx:Animation`):
  `Lighting = true` (fixed-function per-vertex Gouraud over dxvk-native), `ColorOp[0] = modulate2x`
  — the lit vertex colour is doubled against the texture. A neutral `0x80` channel is the
  multiplier 1.0; the `0xFF808080` stamp therefore means "texture only, no tint".
- Characters get **live lights**: `engine/src/libs/location/src/character.cpp:352` calls
  `Lights::SetLightsAt(character->curPos)` before drawing (`engine/src/libs/location/src/lights.cpp:491-517`
  enables only the lights around the character; the sun is D3D light 0, toggled by
  `engine/src/libs/weather/src/weather.cpp:187` / `331`; device default is all lights off,
  `engine/src/libs/renderer/src/s_device.cpp:955-959`).
- Static location geometry does **not** get live lights: its per-vertex colours are baked offline
  by the Lighter (`engine/src/libs/lighter/src/lighter.cpp:PreparingData` lines 116-150 — ambient
  from `D3DRS_AMBIENT` plus sun; `l_geometry.cpp:213` reads the colour slot; `light_processor.cpp:560`
  multiplies attenuation and shadow) and it is drawn with `Lighting = true` and
  `ADDSIGNED(diffuse, texture)` (`engine/src/techniques/location/maineffects.fx:DLightModel`;
  `s_device.cpp:942-943`).

### Net effect

The original's soft look = renderer-side welding + one warm light. The port reproduces it with the
same two ingredients moved to where the new format demands them: converter-side welded normals
(`cff2gm.py`) and neutral vertex colour (`storm_formats.py`), drawn under the engine's live sun +
Gouraud path. The known structural difference is the engine's split of live-lit characters against
baked-lit locations; it is design, not a bug, and reads as matching in the town frames because the
Lighter bakes the same sun direction into the walls.

## 5. Reproducing the picture: convert, launch, record, stop

Convert only the sea content — the converters are split by part in `pdm-game\run.ps1` and nothing
else is rewritten:

```powershell
$env:PDM   = 'C:\Program Files\1C\Корсары'     # the installed original
$env:PARTS = 'ships,islands,sea'               # parts: sea, ships, islands, cities
cd C:\corsairs-remake\pdm-game; .\run.ps1     # converts the selected parts, then starts the engine
```

`PARTS` unset = the original guarded flow; `RECONVERT=1` wipes and converts everything. A partial
run never touches the cities or the characters.

Launch the sea scene from the launcher menu (`sea` is menu item 3 of `game.ps1`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\corsairs-remake\pdm-game\game.ps1 run Debug sea
```

Trigger the video: record the desktop while the scene runs, the recorder stops itself after `-t`
seconds; the comparison frames come out of the same file, cropped to the game area:

```powershell
$rec = Start-Process C:\temp\ffmpeg.exe -ArgumentList '-f','gdigrab','-framerate','30','-i','desktop',
                     '-t','150','-y','C:\temp\shots\sea_after.mp4' -PassThru
powershell -NoProfile -ExecutionPolicy Bypass -File C:\corsairs-remake\pdm-game\game.ps1 run Debug sea
Stop-Process -Id $rec.Id                        # stop the recorder if the scene finished earlier
# ffmpeg -ss <t> -i C:\temp\shots\sea_after.mp4 -frames:v 1 -vf "crop=950:1080:155:130" sea_fNc.png
```

Captures live in `C:\temp\shots`, never in the repository. To stop the engine when it is already
running: kill `engine.exe` (`Stop-Process -Name engine.exe`) or close the window — the scene run
is over when its process returns. The window-title capture (`-f gdigrab -title=...`) fails on this
build ("Can't find window"), so the desktop capture with the crop above is the reliable recipe.

## 6. Evidence index

| Fact | File | Function / line |
|---|---|---|
| CFF vertex has no normal; 3 trailing bytes | `docs/cff-format/README.md`; `seadogs-file-formats/ksy/cyclone.ksy` | 58-66; `cff_mesh_vertex` |
| those bytes are padding in shipped files | byte dump of `RESOURCE/MODELS/CHARACTERS/*.cff` | uniform over 0..255, no near-grey triples |
| original drew without culling, winding inconsistent | `docs/pdm-formats.md` | line 156 |
| weld for normal averaging added; geometry stays per-corner | `tools/cff2gm.py` | `cff_to_meshes` |
| smooth normals computed over the weld | `tools/cff2gm.py` | `compute_normals` |
| character generation + parallel `all` mode | `tools/pdm_character.py` | `convert_all`, `main` |
| world converter delegates character pass | `tools/pdm_world.py` | `World.characters()` |
| vertex colour stamp / neutral grey | `engine/demos/common/storm_formats.py` | `VERTEX_COLOR` 31; `write_gm` 218-229, 283 |
| `.gm` stores normal + colour per vertex, buffer size in bytes | `engine/src/libs/geometry/src/rdf.h` | 203-207, 212, 251 |
| colour survives skinning | `engine/src/libs/model/src/model.cpp` | `VBTransform` 62, 154 |
| character technique: Gouraud + `modulate2x` | `engine/src/techniques/animation.fx` | `Animation` |
| characters lit live at their position | `engine/src/libs/location/src/character.cpp`, `lights.cpp` | 352; `SetLightsAt` 491-517 |
| location colours baked by Lighter, `ADDSIGNED` stage | `engine/src/libs/lighter/...`, `maineffects.fx`, `s_device.cpp` | `PreparingData` 116-150; 560; `DLightModel`; 942-943 |
