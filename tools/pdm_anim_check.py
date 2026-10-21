#!/usr/bin/env python3
"""Checks the converted character animations (resource/animation/*.an + *.ani) for jerks, without
running the game: how far the bones turn from frame to frame, compared with how the action moves.

For every action of an .ani:
  seam   a looped action: the turn from its last frame back to its first. A seam much bigger than
         the usual step of the action is a jump at every repeat (a cycle that does not close);
  spike  the biggest step inside the action against its median step: a frame that jumps;
  pose   how far the first and the last frame are from the first frame of idle_1, the pose the
         entity blends to and from: a big gap is a visible snap where there is no blend.
Angles are the largest over the bones, in degrees; a root jump is in units.

usage: pdm_anim_check.py <resource_dir> [model ...] [--all]   (--all also prints what is fine)
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdm_character import JUMP_DEG, JUMP_RATIO, pose_step as pose_gap  # noqa: E402

# a pose gap above this is a snap where the action starts or ends without a blend
POSE_DEG = 25.0


def read_an(path):
    data = Path(path).read_bytes()
    frames, bones, fps = struct.unpack_from("<iif", data, 0)
    at = 12 + 4 * bones + 12 * bones
    roots = [struct.unpack_from("<3f", data, at + 12 * f) for f in range(frames)]
    at += 12 * frames
    rotations = []
    for b in range(bones):
        rotations.append([struct.unpack_from("<4f", data, at + 16 * (b * frames + f)) for f in range(frames)])
    return fps, roots, rotations


def read_ani(path):
    actions, name = {}, None
    for line in Path(path).read_text(encoding="cp1251", errors="replace").splitlines():
        line = line.split(";")[0].strip()
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            actions[name] = {"loop": True}
        elif name and "=" in line:
            key, value = (s.strip() for s in line.split("=", 1))
            if key in ("start_time", "end_time"):
                actions[name][key] = int(value)
            elif key == "loop":
                actions[name]["loop"] = value == "true"
            elif key == "data" and "Blend time" in value:
                actions[name]["blend"] = True
        elif line.startswith("animation"):
            actions[None] = line.split("=", 1)[1].strip()
    an = actions.pop(None, None)
    return an, {n: a for n, a in actions.items() if "start_time" in a and not n.startswith("back ")}


def check(ani, show_all):
    an_name, actions = read_ani(ani)
    fps, roots, rotations = read_an(ani.parent / an_name)
    rest = actions.get("idle_1", {}).get("start_time")
    lines = []
    for name, a in actions.items():
        s, e = a["start_time"], a["end_time"]
        if e <= s:
            continue
        steps = [pose_gap(rotations, f, f + 1) for f in range(s, e)]
        median = sorted(steps)[len(steps) // 2]
        limit = max(JUMP_DEG, JUMP_RATIO * median)
        notes = []
        worst = max(range(len(steps)), key=steps.__getitem__)
        if steps[worst] > limit:
            notes.append(f"рывок на кадре {s + worst}: {steps[worst]:.0f}° (обычно {median:.1f}°)")
        if a["loop"]:
            seam = pose_gap(rotations, e, s)
            jump = math.dist(roots[e], roots[s])
            if seam > limit:
                notes.append(f"шов цикла {seam:.0f}° (обычно {median:.1f}°), корень {jump:.3f}")
        # walking, running and turning start from the stand through the blend of the Character entity
        moving = name in ("walk", "run", "turn left", "turn right", "dead")
        if rest is not None and name != "idle_1" and not a.get("blend") and not moving:
            gaps = pose_gap(rotations, rest, s), pose_gap(rotations, e, rest)
            if max(gaps) > POSE_DEG:
                notes.append(f"поза idle_1 → начало {gaps[0]:.0f}°, конец → idle_1 {gaps[1]:.0f}° без blend")
        if notes or show_all:
            lines.append(f"  {name:12} кадры {s}-{e}: " + ("; ".join(notes) if notes else "ok"))
    return lines


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    show_all = "--all" in sys.argv
    folder = Path(args[0]) / "animation"
    wanted = {m.lower() for m in args[1:]}
    bad = 0
    for ani in sorted(folder.glob("*.ani")):
        if wanted and ani.stem.lower() not in wanted:
            continue
        lines = check(ani, show_all)
        bad += any("ok" not in l for l in lines)
        if lines:
            print(ani.stem)
            print("\n".join(lines))
    print(f"моделей с рывками: {bad}")


if __name__ == "__main__":
    main()
