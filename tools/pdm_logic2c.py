#!/usr/bin/env python3
"""Compiles the story logic of the original Sea Dogs (the JSON of pdm2storm.py) into Storm scripts.

The logic of the original is data run by CORE.dll: 715 ACTIONS/*.a files of 30 kinds of commands,
76 QUESTS/*.ql story lines (a quest = a condition of 5 kinds + the .a run when it is met) and 554
DIALOGS/*.d trees whose links run .a files. The pattern is closed, so it converts as a whole:

- every .a becomes a script function PdmA_<name>() calling the primitives of program/story.c
  (Pdm_SetDialog, Pdm_SetQuest, Pdm_AddItem ...), one call per command, the line as a comment;
- every .ql becomes the attributes PdmLines.<line>.q<i> (name, the action on entering it, condition,
  its object, the action when the condition is met);
- every .d becomes PdmD_<name>(), which fills PdmDialogs.<dialog>.<node>.<link> (text, target,
  on/off, action);
- WORLDS/story_lines.idf (the lines open at a new game) becomes PdmLogic_NewGame().

Every name in the data (a character, an item, a dialog, a line, a quest, an action) is resolved here
to the key of its object, so the script does no string search. What does not resolve is a comment in
the code and a line in the report: CORE.dll ignored those commands too.

usage: pdm_logic2c.py <data_dir from pdm2storm.py> <program_dir>
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdm_data2c import key, load, table, value  # noqa: E402


# the fields of an attribute are identifiers too
def field(name: str) -> str:
    k = re.sub(r"[^A-Za-z0-9_]", "_", str(name).strip()) or "x"
    return k if k[0].isalpha() else "n" + k


def same(name) -> str:
    """Names are compared without case, and "_" is a space: story_lines.idf opens the quest
    "add_medallion" of Start.ql, which is called "add medallion" there."""
    return " ".join((name or "").replace("_", " ").lower().split())


class Names:
    """name -> key of its object, built in the order pdm_data2c.py builds the keys."""

    def __init__(self, names):
        used, self.keys = set(), {}
        for n in names:
            self.keys.setdefault(same(n), key(n, used))

    def get(self, name):
        return self.keys.get(same(name))


class Logic:
    def __init__(self, data: Path):
        self.data = data
        chars = [load(f) for f in sorted((data / "characters" / "CHARACTERS").glob("*.json"))]
        self.chars = Names(c["id"] for c in chars)
        self.items = Names(dict(t)["name"] for t in table(data, "Items"))
        self.goods = Names(dict(t)["name"] for t in table(data, "Goods"))
        # a nation is its index in nations.idf, as the .nation of a character card
        self.nations = {same(dict(t)["name"]): i for i, t in enumerate(table(data, "nations"))}
        self.ships = Names(Path(f).stem for f in sorted((data / "ships" / "SHIPS").glob("*.json")))
        self.actions = {p.stem.lower(): load(p) for p in sorted((data / "actions").rglob("*.json"))}
        self.action_keys = Names(Path(a["source"]).stem for a in self.actions.values())
        # RESOURCE/INI/DIALOGS is a copy of RESOURCE/DIALOGS (one file differs); CORE.dll reads DIALOGS
        self.dialogs = {p.stem.lower(): load(p) for p in sorted((data / "dialogs" / "DIALOGS").glob("*.json"))}
        self.dialog_keys = Names(Path(d["source"]).stem for d in self.dialogs.values())
        self.lines = {p.stem.lower(): load(p) for p in sorted((data / "quests").rglob("*.json"))}
        self.line_keys = Names(Path(q["source"]).stem for q in self.lines.values())
        self.unresolved = Counter()

    def action_fn(self, name):
        k = self.action_keys.get(name)
        return f"PdmA_{k}" if k else None

    def quest_index(self, line, quest):
        q = self.lines.get(same(line).replace(" ", "_")) or next(
            (v for k, v in self.lines.items() if same(k) == same(line)), None)
        names = [same(x["name"]) for x in q["quests"]] if q else []
        return names.index(same(quest)) if same(quest) in names else None

    def miss(self, what, name):
        self.unresolved[what] += 1
        return f"// skipped: no {what} {name!r}"

    # ---------- .a ----------

    def command(self, cmd):
        """One command of an .a file as a call of a primitive of story.c (or a comment)."""
        obj = cmd["objects"]
        t = tuple(o["type"] for o in obj[:2])
        v = [o["value"] for o in obj]
        num = lambda o: int(re.sub(r"[^\d-]", "", o.get("count") or o["value"]) or 0)  # noqa: E731
        c = cmd["cmd"]
        if c is None:
            return "// ignored by CORE.dll: unknown command"

        def person(name):
            return self.chars.get(name)

        if c == "SET" and t == ("State", "DLink"):
            dialog, node, link = (v[1].split(":") + ["", ""])[:3]
            d = self.dialog_keys.get(dialog)
            return (f"Pdm_SetDLink({value(d)}, {value(field(node))}, {value(field(link))}, {num(obj[0])});"
                    if d else self.miss("dialog", dialog))
        if c == "SET_FOR" and t[0] == "Story_line":
            line, idx = self.line_keys.get(v[0]), self.quest_index(v[0], v[1])
            if line is None:
                return self.miss("story line", v[0])
            return f"Pdm_SetQuest({value(line)}, {idx});" if idx is not None else self.miss("quest", f"{v[0]}:{v[1]}")
        if c == "SET_FOR" and t[0] == "Location" and t[1:] == ("Playside",):
            n = self.nations.get(same(v[1]))
            return (f"Pdm_SetLocationNation({value(field(v[0]))}, {value(v[0])}, {n});" if n is not None
                    else self.miss("nation", v[1]))
        if c == "SET_FOR" and t[0] == "Person":
            p = person(v[0])
            if p is None:
                return self.miss("character", v[0])
            kind = t[1] if len(t) > 1 else None
            if kind == "Dialog":
                d = self.dialog_keys.get(f"{v[0]}_{v[1]}")
                return f"Pdm_SetDialog({value(p)}, {value(d)});" if d else self.miss("dialog", f"{v[0]}_{v[1]}")
            if kind == "Location":
                return f"Pdm_SetLocation({value(p)}, {value(v[1])});"
            if kind == "Playside":
                n = self.nations.get(same(v[1]))
                return f"Pdm_SetNation({value(p)}, {n});" if n is not None else self.miss("nation", v[1])
            if kind == "Model":
                return f"Pdm_SetModel({value(p)}, {value(v[1])});"
            if kind == "Ship":
                s = self.ships.get(v[1])
                return f"Pdm_SetShip({value(p)}, {value(s)});" if s else self.miss("ship", v[1])
            if kind == "Item":
                i = self.items.get(v[1])
                # SET_FOR sets the count (Add_officer_money sets the officers' pay to -700, 0 ...)
                return f"Pdm_SetItem({value(p)}, {value(i)}, {num(obj[1])});" if i else self.miss("item", v[1])
        if c in ("ADD", "DELETE"):
            sign = 1 if c == "ADD" else -1
            kind = t[0] if t else None
            if kind == "Item":
                if v[0].lower() == "money":
                    return f"Pdm_AddMoney({sign * num(obj[0])});"
                i = self.items.get(v[0])
                return f"Pdm_AddItem({value(i)}, {sign * num(obj[0])});" if i else self.miss("item", v[0])
            if kind == "Goods":
                g = self.goods.get(v[0])
                return f"Pdm_AddGoods({value(g)}, {sign * num(obj[0])});" if g else self.miss("goods", v[0])
            if kind == "Expirience":
                return f"Pdm_AddExperience({sign * num(obj[0])});"
            if kind == "Reputation":
                return f"Pdm_AddReputation({sign * num(obj[0])});"
            if kind == "Record" and c == "ADD":
                return f"Pdm_AddRecord({value(v[0])});"
            if kind in ("Person", "Officer"):
                p = person(v[0])
                fn = ("Pdm_JoinSquadron" if kind == "Person" else "Pdm_HireOfficer") if c == "ADD" else \
                     ("Pdm_LeaveSquadron" if kind == "Person" else "Pdm_DismissOfficer")
                return f"{fn}({value(p)});" if p else self.miss("character", v[0])
        if c == "LAUNCH" and t[:1] == ("Story_line",):
            line = self.line_keys.get(v[0])
            return f"Pdm_LaunchLine({value(line)});" if line else self.miss("story line", v[0])
        if c == "LAUNCH" and t[:1] == ("Interface",):
            return f"Pdm_LaunchInterface({value(v[0])}, {value(v[1] if len(v) > 1 else '')});"
        if c == "OPEN" and t == ("Location",):
            return f"Pdm_OpenLocation({value(v[0])});"
        if c == "PLAY" and t == ("Engine_movie",):
            return f"Pdm_PlayMovie({value(v[0])});"
        if c == "CLOSE" and t == ("Game",):
            return f"Pdm_CloseGame({value(v[0])});"
        return self.miss("command form", cmd["line"])

    def action(self, a):
        body = []
        for cmd in a["commands"]:
            body.append(f"\t// {cmd['line'].replace(chr(10), ' ')}")
            body.append("\t" + self.command(cmd))
            # CORE.dll takes the first object of ADD/DELETE; a glued second command is lost
            if cmd["cmd"] in ("ADD", "DELETE") and len(cmd["objects"]) > 1 and cmd["objects"][0]["type"] not in ("Item", "Goods"):
                body.append("\t// ignored by CORE.dll: the rest of the line")
        name = Path(a["source"]).stem
        return [f"// ACTIONS/{a['source']}", f"void {self.action_fn(name)}()", "{"] + body + ["}", ""]

    # ---------- .ql ----------

    def story_lines(self):
        out = []
        for q in self.lines.values():
            lk = self.line_keys.get(Path(q["source"]).stem)
            base = f"PdmLines.{lk}"
            out += [f"\t{base}.id = {value(q['story_line'])};", f"\t{base}.launched = 0;",
                    f"\t{base}.current = -1;", f"\t{base}.count = {len(q['quests'])};"]
            for i, quest in enumerate(q["quests"]):
                qb = f"{base}.q{i}"
                out.append(f"\t{qb}.name = {value(quest['name'])};")
                fn = self.action_fn(quest["action"]) if quest["action"] else None
                if quest["action"] and fn is None:
                    out.append("\t" + self.miss("action", quest["action"]))
                out.append(f"\t{qb}.action = {value(fn or '')};")
                # the first action field runs as soon as the line is put on the quest (Start: add medallion)
                enter = self.action_fn(quest["action_alt"]) if quest["action_alt"] else None
                if quest["action_alt"] and enter is None:
                    out.append("\t" + self.miss("action", quest["action_alt"]))
                out.append(f"\t{qb}.enter = {value(enter or '')};")
                cond = quest["condition"] or {}
                out.append(f"\t{qb}.cond = {value(cond.get('type', 'NONE'))};")
                if not cond:
                    continue
                out.append(f"\t{qb}.kind = {value(cond['object'])};")
                name = cond.get("name")
                names = {"Item": (self.items, "item"), "Goods": (self.goods, "goods"),
                         "Person": (self.chars, "character")}.get(cond["object"])
                target = name
                if (name or "").lower() == "money":
                    target = "money"
                elif names:
                    target = names[0].get(name)
                    if target is None:
                        out.append("\t" + self.miss(names[1], name))
                out.append(f"\t{qb}.target = {value(target or '')};")
                out.append(f"\t{qb}.value = {int(cond.get('value') or 0)};")
                if cond.get("to"):
                    out.append(f"\t{qb}.to = {value(cond['to']['name'])};")
        return out

    # ---------- .d ----------

    def dialog(self, d):
        dk = self.dialog_keys.get(Path(d["source"]).stem)
        base = f"PdmDialogs.{dk}"
        body = [f"\t{base}.id = {value(Path(d['source']).stem)};"]
        for node in d["nodes"]:
            nb = f"{base}.{field(node['id'])}"
            body.append(f"\t{nb}.text = {value(node['text'] or '')};")
            for link in node["links"]:
                lb = f"{nb}.{field(link['id'])}"
                fn = self.action_fn(link["action"]) if link["action"] else None
                if link["action"] and fn is None:
                    body.append("\t" + self.miss("action", link["action"]))
                body += [f"\t{lb}.text = {value(link['text'] or '')};", f"\t{lb}.to = {value(field(link['to']))};",
                         f"\t{lb}.on = {link['flags'][0] if link['flags'] else 1};", f"\t{lb}.action = {value(fn or '')};"]
        return [f"// DIALOGS/{d['source']}", f"void PdmD_{dk}()", "{"] + body + ["}", ""]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    data, program = Path(sys.argv[1]), Path(sys.argv[2])
    lg = Logic(data)
    actions = [line for a in lg.actions.values() for line in lg.action(a)]
    dialogs = [lg.dialog(d) for d in lg.dialogs.values()]
    lines = lg.story_lines()
    new_game = []
    for t in table(data, "story_lines"):
        t = dict(t)
        line, idx = lg.line_keys.get(t["name"]), lg.quest_index(t["name"], t["class"])
        if line is None or idx is None:
            new_game.append("\t" + lg.miss("story line", f"{t['name']}:{t['class']}"))
            continue
        new_game += [f"\tPdm_LaunchLine({value(line)});", f"\tPdm_SetQuest({value(line)}, {idx});"]

    commands = sum(len(a["commands"]) for a in lg.actions.values())
    links = sum(len(n["links"]) for d in lg.dialogs.values() for n in d["nodes"])
    summary = (f"{len(lg.actions)} actions ({commands} commands), {len(lg.lines)} story lines, "
               f"{len(lg.dialogs)} dialogs ({links} links), {sum(lg.unresolved.values())} skipped")
    head = ["// Generated by tools/pdm_logic2c.py from ACTIONS, QUESTS and DIALOGS of the original Sea Dogs.",
            "// Do not edit: the primitives the actions call are in program/story.c.", "",
            "object PdmLines;", "object PdmDialogs;", "// the function of every action, by its key",
            "object PdmActions;", "",
            "void PdmLogic_Init()", "{"] + lines + [
        f"\tPdmActions.{lg.action_keys.get(Path(a['source']).stem)} = {value(lg.action_fn(Path(a['source']).stem))};"
        for a in lg.actions.values()] + [f"\tPdmD_{lg.dialog_keys.get(Path(d['source']).stem)}();"
                                                     for d in lg.dialogs.values()]
    head += [f'\tTrace("PDM logic: {summary}");', "}", "",
             "// WORLDS/story_lines.idf: the story lines open at a new game and their first quests",
             "void PdmLogic_NewGame()", "{"] + new_game + ["}", ""]
    dst = program / "data" / "pdm_logic.c"
    dst.write_text("\n".join(head + actions + [x for d in dialogs for x in d]), encoding="utf-8")
    print(f"{dst}: {summary}")
    for what, n in lg.unresolved.most_common():
        print(f"  skipped {n}: no {what}")


if __name__ == "__main__":
    main()
