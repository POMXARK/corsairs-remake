#!/usr/bin/env python3
"""Converts a character of the original Sea Dogs (PDM 1.061) into a Storm 2 location character:
a skinned .gm, its skeleton animation .an and the actions .ani.

A PDM character (MODELS/CHARACTERS/*.cff) is a set of rigid parts, each with a key per frame:
translation and rotation (Ry*Rx*Rz) of the part, frames 0..N. There is no skeleton in the file,
but the parts move as one: a forearm's pivot stays at the same point of the upper arm in every
frame. So the skeleton is found from the keys: the parent of a part is the part in whose frame
its pivot does not move (the error is zero for 2/3 of the characters; some have loose parts, such
as a bottle thrown about in a hand, kept at their mean place). The root is the part that gives the
tree of the least error, the pelvis.

Storm moves only the root bone, the others turn around their joints, which is exactly such a
hierarchy: joint = the pivot in the parent's frame, rotation = R_parent^T * R_part per frame.

The actions are WORLDS/CHARACTERS/<anim>.idf (the file anim_types.idf gives the model): name, first
and last frame (reversed when first > last), speed; the seated ones (drink, salor, hubernator) have
only do_some1..8 and talk_1..12, with a weight instead of the speed. The speed is the walk
speed in hundredths of a unit per second: a foot on the ground moves 0.031 units a frame in the
hero's walk (speed 30) and 0.06 in his run (60), so the original plays 10 frames a second. The walk
and the run alone are played WALK_RATE and RUN_RATE times faster (ours), their walk speed with them,
so the feet do not slide.

Standing, the Character entity picks one of the idle actions at random each time the last one ends
(weighted by "Probability"), as zombi.dll does: stand_calm 4 times in 5, else one of do_some1..3.

usage: pdm_character.py <PDM_dir> <resource_out> <model.cff> <anim.idf> [--name N] [--scale K]
"""
import argparse
import math
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
from cff2gm import write_gm  # noqa: E402
from pdm2storm import convert_texture, parse_idf  # noqa: E402
from pdm_ship import index_files  # noqa: E402
from storm_formats import write_an  # noqa: E402

# the hero is 0.78 units tall: a unit is 2.3 m. The towns are in the same units
DEFAULT_SCALE = 2.3
FPS = 10.0
# ours: at 10 frames a second the walk of the original (a cycle of 20 frames, two steps) is 60 steps
# a minute at 0.7 m/s, half the pace of a man (120 steps, 1.4 m/s); the walk and the run alone are
# played twice as fast, the gestures stay at the frame rate of the original
WALK_RATE = 2.0
RUN_RATE = 2.0

# Storm action <- the PDM actions to take it from, the first one the character has
ACTIONS = {
    "idle_1": ["stand_calm", "do_some1", "simple_stand"],
    "idle_2": ["do_some1", "stand_calm", "simple_stand"],
    "idle_3": ["do_some2", "stand_calm", "simple_stand"],
    "idle_4": ["do_some3", "stand_calm", "simple_stand"],
    "walk": ["cyrcle_walk"],
    "run": ["circle_run", "cyrcle_walk"],
    "turn left": ["left_rot", "turn_left_calm", "stand_calm"],
    "turn right": ["right_rot", "turn_right_calm", "stand_calm"],
    "dead": ["death_1"],
    "talk": ["talk_1", "stand_calm"],
}

# the fight of the boarding (Boarding.dll, brd_anim.idf): Storm action <- PDM action, looped, its events.
# The original has no flinch: a hit is taken with block_4 (ours). The blow lands at the middle of a hit.
FIGHT_ACTIONS = {
    "fight stand": ("stand_atack", True, ()),
    "attack_fast_1": ("hit_1", False, (("Attack", "50%"),)),
    "attack_fast_2": ("hit_3", False, (("Attack", "50%"),)),
    "attack_force_1": ("hit_2", False, (("Attack", "50%"),)),
    "attack_force_2": ("hit_4", False, (("Attack", "50%"),)),
    "block": ("block_1", True, ()),
    "block_hit": ("block_2", False, ()),
    "parry_1": ("block_3", False, (("Parry start", "10%"), ("Parry end", "60%"))),
    "hit_attack_1": ("block_4", False, ()),
    "hit_parry": ("block_2", False, ()),
    "death_1": ("death_1", False, ()),
    "death_2": ("death_2", False, ()),
    "Normal to fight": ("to_atack_pos", False, ()),
    "Fight to normal": ("to_stand_pos", False, ()),
}

# the blades of the original: a fighter holds his twice, in the scabbard on the belt and drawn in the
# hand, and the game shows one of them; out of a fight the drawn one is left out
# zombi.dll, at the end of each action of a stand: rand % 5 == 0 -> do_some(rand % 3 + 1), else
# stand_calm; so each gesture weighs 1/15 against 12/15 of the calm stand (idle_1, 1)
IDLE_PROBABILITY = {"idle_2": 1 / 12, "idle_3": 1 / 12, "idle_4": 1 / 12}

BLADES = ("soldier_spa_palash", "pirat_sabel")


def drawn_blades(textures, parents):
    """The parts of the drawn blades: of the two parts of a blade, the one farther from the root."""
    def depth(part):
        n = 0
        while parents[part] >= 0:
            part, n = parents[part], n + 1
        return n
    out = set()
    for blade in BLADES:
        parts = [i for i, t in enumerate(textures) if Path(t).stem.lower() == blade]
        if len(parts) == 2 and depth(parts[0]) != depth(parts[1]):
            out.add(max(parts, key=depth))
    return out


def read_keys(path: Path):
    """The animation keys of every mesh of LOD 0: [(tx, ty, tz, rx, ry, rz)] per frame."""
    data = path.read_bytes()
    r = cff2gm.CFFReader(data)
    r.skip(24)
    textures, materials, lods = r.u32(), r.u32(), r.u32()
    r.skip(8)
    for _ in range(textures):
        r.skip(r.u8())
    for _ in range(materials):
        r.skip(36)
        r.skip(r.u32() * 20)
    vert_size = 13 if cff2gm._parse_meshes_at(data, r.off, lods, 13)[1] else 12
    count = r.u32()
    r.skip(4)
    parts = []
    for _ in range(count):
        r.skip(20)
        r.u32()
        vertices, faces = r.u32(), r.u32()
        r.u32()
        keys = r.u32()
        r.skip(4)
        r.skip(vertices * vert_size + faces * (6 if vertices > 256 else 3))
        parts.append([struct.unpack_from("<6f", data, r.off + 28 * i) for i in range(keys)])
        r.skip(keys * 28)
    return parts


def mat_t(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def quaternion(m):
    """(x, y, z, w) of a rotation matrix acting on column vectors."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def skeleton(keys):
    """Parents, joints and the fit error of the parts from their keys.

    Returns (order, parents, pivots, error): order lists the parts root first, every parent before
    its children; parents[i] is the parent part of part i (-1 for the root); pivots[i] the pivot
    of part i in its parent's frame (mean over the frames); error the worst mean distance of a
    pivot from its place, in units.
    """
    frames = min(len(k) for k in keys)
    rot = [[cff2gm.frame_matrix(*k[f][3:6]) for f in range(frames)] for k in keys]
    pos = [[k[f][0:3] for f in range(frames)] for k in keys]
    n = len(keys)
    # sample the frames for speed: a hierarchy is a hierarchy in every frame
    sample = range(0, frames, max(1, frames // 120))

    def fit(i, p):
        local = [mat_vec(mat_t(rot[p][f]), [pos[i][f][c] - pos[p][f][c] for c in range(3)]) for f in sample]
        mean = [sum(v[c] for v in local) / len(local) for c in range(3)]
        error = math.sqrt(sum(sum((v[c] - mean[c]) ** 2 for c in range(3)) for v in local) / len(local))
        return error, mean

    cost = {(i, p): fit(i, p) for i in range(n) for p in range(n) if i != p}

    def grow(root):
        """The tree from the root by the best fitting links (Prim): order, parents, total error."""
        parents, order, total = {root: -1}, [root], 0.0
        while len(order) < n:
            e, i, p = min((cost[i, p][0], i, p) for i in range(n) if i not in parents for p in order)
            parents[i] = p
            order.append(i)
            total += e
        return total, order, parents

    # the root is the part that gives the tree of the least error: a bottle or a saber thrown about
    # in a hand moves on its own and is no root, though it fits under no other part
    _, order, parents = min(grow(r) for r in range(n))
    pivots = {i: cost[i, p][1] if p >= 0 else None for i, p in parents.items()}
    error = max([cost[i, p][0] for i, p in parents.items() if p >= 0] or [0.0])
    return order, parents, pivots, error, rot, pos, frames


def quat_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


def check_pose(parents_b, joints, root_positions, rotations, rot, pos, order, k):
    """Replays the bones the way the engine builds them (Bone::BuildMatrix: local * parent, the
    joint in the parent's frame, start^-1 * bone for the skin) and returns the worst distance of a
    part's pivot and axis tips from where the keys of the original put them, in metres."""
    def world(f):
        mats = []
        for b, p in enumerate(parents_b):
            m = quat_matrix(rotations[b][f])
            t = root_positions[f] if p < 0 else joints[b]
            if p < 0:
                mats.append((m, list(t)))
            else:
                pm, pt = mats[p]
                mats.append((mat_mul(pm, m), [a + c for a, c in zip(mat_vec(pm, t), pt)]))
        return mats
    start = world(0)
    worst = 0.0
    frames = len(root_positions)
    for f in range(0, frames, max(1, frames // 40)):
        now = world(f)
        for b, part in enumerate(order):
            for tip in ((0, 0, 0), (0.1, 0, 0), (0, 0.1, 0), (0, 0, 0.1)):
                # a point of the part in the bind pose (frame 0) ...
                bind = [k * c for c in pos[part][0]]
                v = [a + c for a, c in zip(mat_vec(rot[part][0], tip), bind)]
                # ... skinned by the engine
                sm, st = start[b]
                local = mat_vec(mat_t(sm), [v[c] - st[c] for c in range(3)])
                nm, nt = now[b]
                engine = [a + c for a, c in zip(mat_vec(nm, local), nt)]
                # ... and where the original puts it
                want = [a + k * c for a, c in zip(mat_vec(rot[part][f], tip), pos[part][f])]
                worst = max(worst, math.dist(engine, want))
    return worst


def read_actions(idf: Path):
    actions = {}
    for obj in parse_idf(idf)["objects"]:
        fields = dict(obj)
        if fields.get("name", "0") == "0":
            continue
        actions[fields["name"]] = (int(fields["start_action"]), int(fields["end_action"]),
                                   float(fields.get("speed", "0") or 0))
    return actions


def step_frames(heights, start, end):
    """The two frames of a walk cycle where a foot comes down: the pelvis is lowest when both feet
    are on the ground, once a step, half a cycle apart."""
    cycle = list(range(start, end + 1))
    first = min(cycle, key=lambda f: heights[f])
    n = len(cycle)

    def apart(f):
        d = abs(f - first) % n
        return min(d, n - d)
    second = min((f for f in cycle if apart(f) >= n // 4), key=lambda f: heights[f], default=first)
    return first, second


# a step between two frames is a jump when it is this many times the median step of the action and
# above JUMP_DEG (degrees, the largest over the bones); tools/pdm_anim_check.py reports by the same
JUMP_RATIO = 3.0
JUMP_DEG = 6.0


def pose_step(rotations, f1, f2):
    """The largest turn of a bone between the frames f1 and f2, in degrees."""
    def angle(q1, q2):
        return math.degrees(2 * math.acos(min(1.0, abs(sum(a * b for a, b in zip(q1, q2))))))
    return max(angle(bone[f1], bone[f2]) for bone in rotations[1:])


def jump_frame(rotations, start, end):
    """The first frame after which the action start..end jumps, or None."""
    steps = [pose_step(rotations, f, f + 1) for f in range(start, end)]
    if not steps:
        return None
    limit = max(JUMP_DEG, JUMP_RATIO * sorted(steps)[len(steps) // 2])
    return next((start + i for i, step in enumerate(steps) if step > limit), None)


def write_ani(path: Path, an_name: str, actions, k: float, frames: int, heights, rotations, head=None):
    """The Storm actions the Character entity looks for, from the PDM ones (ACTIONS); heights: the
    height of the pelvis per frame, for the steps; head: the bone the engine turns to look at someone."""
    text = f"; converted by tools/pdm_character.py, {FPS:g} frames a second as in the original\n"
    text += f"animation = {an_name}.an\n"
    if head is not None:
        text += f'data = "Head bone index", "{head}"\n'
    found = []

    def section(name, start, end, speed, loop=True, data=(), rate=1.0, events=()):
        nonlocal text
        reverse = start > end
        start, end = min(start, end, frames - 1), min(max(start, end), frames - 1)
        text += f"\n[{name}]\nstart_time = {start}\nend_time = {end}\nloop = {'true' if loop else 'false'}\n"
        if reverse:
            text += "type = reverse\n"
        if rate != 1.0:
            text += f"speed = {rate:g}\n"
        for key, value in data:
            text += f'data = "{key}", "{value}"\n'
        for event, at in events:
            text += f'event = "{event}", {at}\n'
        if speed:
            text += f'data = "Walk speed", "{speed:.3f}"\n'
            # the Character entity plays a step sound (step_<material of the patch>) on these events
            left, right = step_frames(heights, start, end)
            text += f'event = "LStep", {left}, always\nevent = "RStep", {right}, always\n'

    for name, sources in ACTIONS.items():
        src = next((s for s in sources if s in actions), None)
        if src is None:
            continue
        start, end, speed = actions[src]
        found.append(name)
        if name in ("walk", "run"):
            # the speed of a cycle is the speed of the walk it is made of (a run made of the walk walks)
            rate = RUN_RATE if name == "run" else WALK_RATE
            speed = actions[src][2] / 100.0 * k * rate
            section(name, start, end, speed, rate=rate)
            # walking back plays the cycle the other way
            section("back " + name, end, start, -speed, rate=rate)
        elif name.startswith("idle"):
            # some gestures of the original run on into the next action of the file (do_some1 of
            # the hero, 85-125, into stap_back_calm from 120): played to the end they jump; cut there
            jump = jump_frame(rotations, start, end) if start < end else None
            if jump is not None and jump > (start + end) // 2:
                end = jump
            # not looped: at its end the entity picks the next idle action; blended, as a gesture
            # does not end in exactly the pose the stand begins with (ours, 0.2 s)
            data = [("Blend time", "0.2")]
            if name in IDLE_PROBABILITY:
                data.append(("Probability", f"{IDLE_PROBABILITY[name]:g}"))
            section(name, start, end, 0, loop=False, data=data)
        elif name == "talk":
            # the talk of the soldiers stands otherwise than their idle_1 (75-100 degrees): blended
            # as the gestures (ours)
            section(name, start, end, 0, data=[("Blend time", "0.2")])
        else:
            section(name, start, end, 0, loop=name != "dead")
    for name, (src, loop, events) in FIGHT_ACTIONS.items():
        if src not in actions:
            continue
        start, end, _ = actions[src]
        found.append(name)
        section(name, start, end, 0, loop=loop, events=events)
    # the steps of the fight at the walk speed of the idf (stap_forward_atack runs backwards, 405-395)
    if "stap_forward_atack" in actions and "stap_back_atack" in actions:
        start, end, speed = actions["stap_forward_atack"]
        speed = speed / 100.0 * k
        found.append("fight walk")
        for prefix in ("walk", "run"):
            section("fight " + prefix, start, end, speed)
            section("fight back " + prefix, *actions["stap_back_atack"][:2], -speed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")
    return found


def convert(res: Path, out: Path, model: str, anim: str, name: str = None, k: float = DEFAULT_SCALE,
            textures: dict = None, blade: str = "belt"):
    """Writes models/characters/<name>.gm, animation/<name>.{an,ani} and the textures to
    textures/characters/; returns a summary line. blade="hand" writes <name>_brd.gm instead, the
    fighter of the boarding: the drawn blade in the hand, none in the scabbard."""
    models = index_files(res / "MODELS" / "CHARACTERS")
    textures = textures or index_files(res / "TEXTURES")
    cff = models[Path(model).name.lower()]
    name = (name or Path(model).stem).lower()
    keys = read_keys(cff)
    if not keys or not all(keys):
        return f"{name}: static, skipped"
    order, parents, pivots, error, rot, pos, frames = skeleton(keys)
    bone = {part: b for b, part in enumerate(order)}

    used = set()

    def texture(stem):
        used.add(stem.lower())
        return f"{stem.lower()}.tga"

    meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * k for c in p), texture=texture)
    assert len(meshes) == len(keys), "a key list per mesh"
    for part, mesh in enumerate(meshes):
        mesh.vertices = [(p, n, uv, bone[part]) for p, n, uv, _ in mesh.vertices]
    drawn = drawn_blades([m.texture for m in meshes], parents)
    # the head: the first part painted with a head or a face (doc-Head, hub-spa-face); a chicken has none
    head = next((part for part, m in enumerate(meshes) if "head" in m.texture.lower() or "face" in m.texture.lower()), None)
    hidden = drawn
    gm_name = name
    if blade == "hand":
        blades = {part for part, m in enumerate(meshes) if Path(m.texture).stem.lower() in BLADES}
        if not drawn:
            return f"{name}: no blade to draw, skipped"
        hidden = blades - drawn
        gm_name = name + "_brd"
    meshes = [m for part, m in enumerate(meshes) if part not in hidden]

    bone_parents = [-1] + [bone[parents[part]] for part in order[1:]]
    joints = [tuple(c * k for c in pos[order[0]][0])] + [tuple(c * k for c in pivots[part]) for part in order[1:]]
    root_positions = [tuple(c * k for c in pos[order[0]][f]) for f in range(frames)]
    rotations = []
    for part in order:
        p = parents[part]
        if p < 0:
            rotations.append([quaternion(rot[part][f]) for f in range(frames)])
        else:
            rotations.append([quaternion(mat_mul(mat_t(rot[p][f]), rot[part][f])) for f in range(frames)])

    drift = check_pose(bone_parents, joints, root_positions, rotations, rot, pos, order, k)
    write_gm(meshes, out / "models" / "characters" / f"{gm_name}.gm", skinned=True)
    write_an(out / "animation" / f"{name}.an", FPS, bone_parents, joints, root_positions, rotations)
    # anim_types.idf names the files in either case (traktir_man.idf for Traktir_Man.idf)
    anims = index_files(res / "WORLDS" / "CHARACTERS")
    found = write_ani(out / "animation" / f"{name}.ani", name, read_actions(anims[anim.lower()]), k, frames,
                      [p[1] for p in root_positions], rotations,
                      head=order.index(head) if head is not None else None)
    missing = []
    for stem in sorted(used):
        src = textures.get(stem)
        dst = out / "textures" / "characters" / f"{stem}.tga.tx"
        if src is None:
            missing.append(stem)
            continue
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            convert_texture(src, dst)
    note = f", missing textures {' '.join(missing)}" if missing else ""
    return (f"{gm_name}: {len(order)} bones, {frames} frames, pose error {drift:.3f} m, "
            f"actions {' '.join(a.replace(' ', '_') for a in found)}{note}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdm")
    ap.add_argument("out")
    ap.add_argument("model")
    ap.add_argument("anim")
    ap.add_argument("--name")
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE)
    ap.add_argument("--blade", choices=("belt", "hand"), default="belt")
    a = ap.parse_args()
    res = Path(a.pdm)
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    print(convert(res, Path(a.out), a.model, a.anim, a.name, a.scale, blade=a.blade))


if __name__ == "__main__":
    main()
