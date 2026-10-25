---
name: storm-menu-control
description: Use when a main-menu item of the Storm engine interface must be selected or moved between items from a script (never simulated key presses). Documents MSG_INTERFACE_MENU_ACTION and its format string, the command names of xutil.cpp, the ini "command =" lines with their select/com/event/delay/sound subparameters, how CINODE::DoAction and FrameProcess resolve the chain and move the current node, how to read the current node back and how to observe the command event in an autotest, plus the verified pitfalls (no-ops, the PostEvent handlers, the script VM quirks) and the capture alignment for the visual check.
---

# Driving the main menu of the Storm engine interface from a script

The rule of the repository stays first: never fake key presses (`xdotool`, synthetic
`ITurnV`/`IAction` controls). A menu test is a script that posts events with delays and sends
messages to the interface entity; the engine then runs the same code path a player's press runs.

## Injecting one menu action (the message added in this fork)

| What | Message | Format | Engine code |
|---|---|---|---|
| press a menu command on a node | `MSG_INTERFACE_MENU_ACTION` = `45062` | `"lss"`: the name of a command, then the name of a node (`""` = the current node) | `engine/src/libs/shared_headers/include/shared/interface/messages.h:MSG_INTERFACE_MENU_ACTION`, read by `engine/src/libs/xinterface/src/xinterface.cpp:XINTERFACE::ProcessMessage` (`case MSG_INTERFACE_MENU_ACTION:`, line 1078) |

```
SendMessage(&GameInterface, "lss", MSG_INTERFACE_MENU_ACTION, "downstep", "");   // move the current item down
SendMessage(&GameInterface, "lss", MSG_INTERFACE_MENU_ACTION, "activate", "B_OPTIONS"); // select a named item
```

The body does exactly one press of the keyboard branch of `XINTERFACE::DoControl`
(`xinterface.cpp:1992`, its `SetCurNode(pNewNod)` at line 2303): `xutil.cpp:FindCommand` turns the
name into the `ACTION_*` code, `CINODE::DoAction(code, bBreakPress, true)` (`inode.cpp:106`) runs
the command chain of the node, and a non-null return moves the current node
(`xinterface.cpp:1095 SetCurNode(pNewNod)`). `FindNode` for the node name comes from `inode.h:179`,
and an empty name keeps `m_pCurNode` — `FindNode("")` returns nothing, so a missing empty-name
check makes the action silently do nothing.

## The names of the commands

`xutil.cpp:FindCommand` matches the names of `pCommandsList` (`xdefines.h:22`, the list of
`COMMANDDESCR` built in `xutil.cpp`), returning `-1` for an unknown name (`xutil.cpp:29`, `xutil.cpp:40`)
— the message then breaks and nothing happens:

`activate, deactivate, select, rightstep, leftstep, upstep, downstep, speedleft, speedright,
speedup, speeddown, click, dblclick, rclick, dblrclick`

The same names are the ones written in the ini of a node (`docs/ru/04-formats.md:146`, the table
made from `xutil.cpp:12`), so a menu script uses the words of the ini, never the numeric codes.

## What the ini of a node says (`engine/demos/menu-control/resource/ini/interfaces/mainmenu.ini`)

```
[B_LOAD]
command = click
command = activate
command = upstep,select:B_NEWGAME      // upstep moves the menu to the item named after "select:"
command = downstep,select:B_OPTIONS
command = deactivate
position = 60,282,300,324
string = Load
```

- The part before `:` is the command, the part after it is the **ret control** — the node the
  current node jumps to when this command fires. `select:` is the subparameter name, `B_NEWGAME`
  is a node of the same interface (`docs/ru/04-formats.md:146`: `select:NODE`, `com:cmd:node`,
  `event:Name`, `delay:N`, `sound:N`).
- A command without a ret control (`activate`, `deactivate`, `click`) never moves the current
  node; it only fires its own effects.
- A node that does not have a command at all (the first item `B_NEWGAME` has no `upstep` line) is
  a no-op: `m_pCommands[i].bUse` is false (`inode.cpp:122`), so there is no event, no chain and no
  move. Pressing "up" on the top item of the list is a real edge case, not a wrap-around.

## How one press is resolved (`inode.cpp`)

1. `CINODE::DoAction` (`inode.cpp:106`) — for a `TEXTBUTTON` an unselected node returns
   `nullptr` (`inode.cpp:108`, `xi_text_button.cpp` constructor sets `m_bSelected` true).
2. The chain: `CommandExecute(code)` is asked in a loop (`inode.cpp:131`); for a text button it
   always answers `-1` (`xi_text_button.cpp:554`, `return -1` at line 570), so a `TEXTBUTTON`
   chain is a single command and the move happens in the next step.
3. `core.Event("ievnt_command","ss", command, node)` fires (`inode.cpp:142`, `inode.cpp:147`) and
   `m_nCurrentCommandNumber` is set (`inode.cpp:143`, `148`).
4. `FrameProcess(0)` is called synchronously (`inode.cpp:152`), and `CINODE::FrameProcess`
   (`inode.cpp:61`) applies the pending command: the sub-controls get `CommandExecute`
   (`inode.cpp:79`), the `event:` name posts `MSG_INTERFACE_SET_EVENT` (`inode.cpp:85`, format
   `"lssl"`), and the ret control node posts `MSG_INTERFACE_SET_CURRENT_NODE`
   (`inode.cpp:92`, format `"lp"`) to the interface entity; then `m_nCurrentCommandNumber = -1`
   (`inode.cpp:95`).
5. Only after that does `DoAction` return a node (`inode.cpp:155..159`,
   `ptrOwner->FindNode(sRetControl, nullptr)`), which is what moves the menu; otherwise it returns
   `nullptr` (`inode.cpp:161`) and the current node stays.

So: navigation = a chain command with a ret control; selection = `activate`, which has no ret
control and must be observed, not read from the current node.

## Reading the state back from a script

```
// where the menu is now (xinterface.cpp:762 case MSG_INTERFACE_GET_CURRENT_NODE, "le")
SendMessage(&GameInterface, "le", MSG_INTERFACE_GET_CURRENT_NODE, &currentNodeName);
// what the node itself reported (inode.cpp:142, "ievnt_command" "ss")
SetEventHandler("ievnt_command", "Menu_Command", 0);
void Menu_Command()
{
    lastCommand = GetEventData();      // the name of the command
    lastCommandNode = GetEventData();  // the node that reported it
}
```

A navigation command also fires `ievnt_command`, so after a step `lastCommand` is that command
name; a selection check must be made right after the `activate` step and compare both the command
and the node. The `MSG_INTERFACE_GET_CURRENT_NODE` idiom is the one `sd-teho-public/program/interface/utilite.c`
uses for the same purpose.

## The autotest harness (`engine/demos/menu-control/program/menu_autotest.c`)

A plan of the test is a chain of self-registered events posted with delays; every step must be
registered with `SetEventHandler` before it is posted, otherwise nothing runs at all (the idiom of
`engine/demos/island/program/island.c:Main`, lines 156, 229, 230):

```
SetEventHandler("Menu_Down1", "Menu_Down1", 0);
...
void Menu_Down1()
{
    ReadCurrentNode();
    CheckNode("down 1", "B_LOAD");
    MenuAction("downstep", "");
    PostEvent("Menu_Down2", STEP_MS);   // the step returns after posting the next one
}
```

`engine.ini` of the demo runs this program (`run = menu_autotest.c`, `full_screen = 0`, the window
title `Storm menu control autotest`). The traces of the run are the proof:

```
AUTOTEST: up to the top shows B_NEWGAME
AUTOTEST: up out of the list shows B_NEWGAME
AUTOTEST: activate of a named item, node B_OPTIONS reported activate
AUTOTEST: a named item does not move the menu shows B_NEWGAME
AUTOTEST: OK, 12 checks of navigation and selection passed
```

## Script VM traps found while writing this test

- `++checksDone` on a global integer compiles and dies at runtime with
  `RUNTIME ERROR in <file>(<line>): no Lvalue` (`error.log`); write `checksDone = checksDone + 1;`.
- `S SendMessage(...)` — the `S` prefix some older TEHO programs use — does not exist in this VM
  (`Undeclared identifier: S`); the engine demos call `SendMessage` plainly.
- A short format string drops the remaining arguments silently: `"lss"` is needed for
  `MSG_INTERFACE_MENU_ACTION`, `"ls"` would leave the node name away (`interface/messages.h`
  convention, the same trap as in the `storm-land-scenario-control` skill).
- `==` between two `string` values works (`expression.cpp:CompareAndSetResult`); string
  comparisons of variables with literals are used all over `game/program/*.c`.
- Local variables in the handlers of this VM are best avoided; the test keeps its state in
  globals and parameters.

## Checking the picture

The selected item is drawn with the "selected" art because the draw call is made against the
current node: `XINTERFACE::DrawNode` passes `nod == m_pCurNode` (`xinterface.cpp:1979`, `1984`) and
`CXI_TEXTBUTTON::Draw` (`xi_text_button.cpp:39`) switches the glyph, the border and the font
colour of the pressed item on that flag (`bSelected` at lines 46, 56, 73, 90, the colour
`fontColorSelected` read at line 253). So a visual check of a menu test is: the frame at the moment
a step printed its trace must show the highlight on the
expected button, and the frame after an `activate` of a named item must keep the highlight on the
unchanged current item. Record with `gdigrab -i desktop` (the `-i title=` source often fails with
`Failed to capture image (error 8)` for this window) and take the frames at
`trace time - recording start` as the `storm-capture-crop` skill prescribes; the game area of this
demo sits at `crop=1140:850:950:430` in the 2560x1440 desktop grab. Captures stay in `C:\temp\shots`.
