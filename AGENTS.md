# RULES: C++ / PS 5.1 GAME DEV

1. ACTION RULE: Execute strictly ONE task per turn. No multi-steps.
2. CHECKPOINT RULE: After fixing a bug or running a test, STOP generation immediately and ask the user: "Test passed/failed? Can I move to next step?"
3. CODE COERCION: Always cast float division to integer (use `//` or `int()`) for array/matrix indexing.
4. POWERSHELL 5.1 CONSTRAINTS:
   - Run conversion ONLY via: `powershell -NoProfile -ExecutionPolicy Bypass -File pdm-game\data\convert-locations.ps1`
   - Before dot-sourcing `demo.ps1`, explicitly set absolute path to `$DefaultEngine`.
   - Always verify files via `if (Test-Path $Path)` before running `Select-String`.
   - Save all .ps1 files strictly in ASCII encoding.
5. SKILLS INDEX: before a research step read `SKILLS.md` at this root; it names for every task the
   file that carries the instructions, the method it prescribes and the purpose it serves. Add a row
   there the same turn a new skill or recipe is written, delete the row when it stops applying.
6. SKILLS IN USE: `storm-land-scenario-control` (`.claude/skills/storm-land-scenario-control/SKILL.md`)
   drives the hero, the camera and the change of location from the script side; `storm-menu-control`
   (`.claude/skills/storm-menu-control/SKILL.md`) selects a main-menu item and moves the selection
   up and down the list from the script side (`MSG_INTERFACE_MENU_ACTION`, `engine\demos\menu-control`);
   `storm-capture-crop` (`.claude/skills/storm-capture-crop/SKILL.md`) makes the video, the frames and
   the collages used by rule 10.
7. DATA, NOT LITERALS: a place of a scenario comes from the location data of the game,
   `pdm-game\program\data\pdm_world.c` (the types of the points and their links), never from invented
   coordinates; the door of a location is the marker of type 4 that stands outside the box of type 1.
8. ENGINE FACTS: never invent engine behaviour, cite `file.cpp:function` from `engine\src\libs\...`;
   the same facts in the prose form live in `engine\docs\ru\*` and must be updated when a format or a
   behaviour changes.
9. LOG PROOF: the traces of the scenario land in `compile.log` with the wall-clock timestamp, the
   loader reports the sizes and the triangle counts in `system.log`, an empty `error.log` is the
   evidence that the script compiled at all; the frames of a run whose traces never appeared are not
   an evidence of anything.
10. VISUAL CHECK: any change to the picture (vegetation, lighting, the camera, an interface panel)
    must be evaluated by the frames made through `storm-capture-crop`: the frames of the exact
    `Trace` moments of the scenario, cropped to the game area, compared before and after. Never
    conclude from the log alone. Captures stay in `C:\temp\shots`, never in the repository.
11. GAME LAUNCH: Run from `pdm-game/` using `.\game.ps1 run Debug menu`.
