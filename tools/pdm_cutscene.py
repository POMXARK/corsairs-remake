#!/usr/bin/env python3
"""Converts the movies of the original Sea Dogs (PDM 1.061): RESOURCE/DESC/*.ani played by Cinema.dll.

A movie is a stream of records {type, frame, size, payload} after a 16-byte header (16, count,
offset of the keys, key count); the camera keys follow the records, 28 bytes each: position 3f,
angles 3f (Ry*Rx*Rz as the parts of the models), the frame. A record with frame 0 runs when the
movie loads, the others when the frame comes (Cinema.dll steps 66 ms a frame, 15 a second).
A movie is either a playlist (records 0x13: the child movies and their start time; 0x17 ends
the group before it) or a scene (the records below).

Scene records known (FUN_10003150 of Cinema.dll):
  0 model (.cff, a name ending in _a is the animated part)  1 field of view of the camera, degrees  4/0x1d fade
  (payload: seconds, negative from black, positive to black)  0xd sound (name[32], volume)
  0x11 the end of the movie (frame)  0x1a the sea and the sky (296 bytes of weather)  2/3 start  5 start  6/0xb/0xc/0x1b fire
  7/0x20/0x21 the sun in the shot  0x14 clouds  0x19 explosion  0x22 blood  0x23.. flags

Writes, in the units of the engine (metres, pdm_character.DEFAULT_SCALE):
  models/cinema/<scene>.gm            the still models of a scene, merged by texture
  textures/cinema/*.tga.tx            their textures
  sounds/cinema/<name>.wav            the sounds of the records 0xd
  program/data/pdm_cutscenes.c        PdmCut: the playlists, the scenes (frames, camera keys, fades,
                                      sounds), PdmCut_Init(), PdmCut_Load(<scene>)

usage: pdm_cutscene.py <Sea Dogs install dir with RESOURCE> <game_dir> [scene ...]
"""
import math
import shutil
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cff2gm  # noqa: E402
from cff2gm import frame_matrix, write_gm  # noqa: E402
from pdm2storm import convert_texture  # noqa: E402
from pdm_character import quaternion, read_keys  # noqa: E402
from pdm_ship import index_files  # noqa: E402
from pdm_world import K, merge_by_texture  # noqa: E402
from storm_formats import Mesh, write_an  # noqa: E402

# every movie of DESC: a playlist (records 0x13) plays its scenes, any other file is a movie of one scene.
# "Intro" is what "Новая игра" plays
FRAME_MS = 66
# the shapes of the records
REC_MODEL, REC_FADE_A, REC_SOUND, REC_END, REC_FADE_B = 0, 4, 0xD, 0x11, 0x1D
REC_CHILD, REC_BREAK = 0x13, 0x17
REC_VIEW, REC_SKY = 1, 0x1A
REC_FLAG = 6  # a flag: x y z of the pole, size, yaw, colour word, texture name[32]
FLAG_WIDTH = 3.5  # the width of a flag in the units of the keys per unit of its size
FLAG_ASPECT = 0.6
RIDE_GAP = 2.0  # a flag within this distance of a moving part (the units of the keys) belongs to it
RIDE_TRAVEL = 0.5  # ... when that part travels farther than this in the movie
RIDE_FLAG_SCALE = 0.3
FAR_FLAG_SCALE = 0.3  # the flags on the far ships are smaller in the original
FAR_UNITS = 150.0  # the ships farther than this from the origin of a movie are a model of their own
SUBSTEPS = 4  # sub-frames a key of the animated parts that hold over a cut
FLAG_SHAPES = 16  # the shapes of a waving cloth, 70 ms each (cutscene.c, CUT_FLIP_MS): a wave runs along it in 1.1 s
FLAG_SWAY = 0.07  # the sway of the cloth at its free edge, of its width
# the level of the hulls over the wave of the sea (minus: deeper in the water) per movie, the key is the scene name in
# lower case; the rest take DRAFT
DRAFT = 0.0
# (scene8: the floor of the prison stays over the water also where the turn of the room lowers it)
DRAFTS: dict = {"scene1": 0.2, "scene8": 1.0, "scene11": 1.0, "scene4": -0.6, "scene5": -0.6}
def dim(color, k):
    """A 0x00RRGGBB word with every channel times k."""
    return sum(int(((color >> s) & 255) * k) << s for s in (0, 8, 16))


# the sky of a movie when the record's texture does not tell its mood (the original hazes the last shot of Scene7)
# the swell of a movie when the record's sea_amplitude gives a bigger one than the picture of the original shows (Scene1: a flat harbour)
AMPS: dict = {"scene1": 0.001}
# the colour of the water (r, g, b of Sea2.WaterColor) when the render of the game colour differs from the original (Scene1: a greener, lighter harbour)
WATERS: dict = {"scene1": (42, 122, 118), "scene8": (15, 35, 95)}
# the movies in a cabin: no sea, nothing to ride the waves (the approach to the map ends the intro)
NO_SEA = {"scene6", "scene12"}
CABIN_LIFT = 0.6  # the lift of those movies: the actors stand where the keys put them, so the room stays near the zero
SKIES: dict = {"scene2": "clear", "scene3": "clear", "scene7": "haze", "scene8": "storm", "scene9": "clear", "scene11": "clear", "scene41": "clear"}
# the turn of the sun of a movie against its record (radians): the light of the prison falls from the other side
SUN_TURNS: dict = {"scene8": -1.5708}
# the strength of the direct light of a movie against its record (the wall of the prison is too bright with the full sun)
# the night of a movie darker than the record (the share of the light that is left; the sky is black, the clouds grey)
NIGHT_DARK: dict = {"scene10": 0.35}
SUN_DIM: dict = {"scene8": 0.15}
# the effects the keys do not hold, per movie: (second of the original shot, particle system, point x y of the screen 0..1, distance d).
# the effects of a movie are records of its own: type 20 = the smoke of a gun (Cinema.dll makes "canclouds": x y z and three angles),
# type 25 = an explosion ("explosion_x": x y z); the movies that play them (the guns of the Spanish ship end Scene7)
REC_GUN, REC_HIT = 20, 25
FX_KINDS: dict = {REC_GUN: "gunflash", REC_HIT: "shothit"}
FX_SCENES = {"scene7"}
REC_BINO = 0x1e  # "binokular": the view through a spyglass (black bars, dark edges) from the frame of the record on
# a movie that hands the camera over to the next one in the middle (Scene4 ends its first shot with a type 0x11 at 122 and the ships come back at 123;
# Scene5 hands over with a type 0x12 at 45): the playlist plays the pieces in turn, (name, first frame, last frame); the lengths of the
# pieces match the shots of the original (the officers 2.9 s, the three ships 2.3 s, the officers again 1.9 s)
SPLICES = {"intro": [("scene4", 0, 122), ("scene5", 0, 45), ("scene4", 122, 157), ("scene5", 45, 74)]}
SPLICES["intro_new"] = SPLICES["intro"]
# the turn of the room of a movie about the axis of its view (radians): the window of the prison stands higher against the horizon of the sea than the camera keys put it
TILTS: dict = {"scene8": 0.05}
# movies that carry no weather of their own (they were played over another shot): the sea and the sky of the movie named
WEATHER_OF: dict = {"scene11": "scene4", "scene41": "scene4", "scene9": "scene4"}
LIFT = 1.5  # models and camera over the zero of the sea of the game: the hulls stand on the waterline (the level of the sea is not in the record)


def read_ani(path: Path):
    """(header, records [(type, frame, payload)], camera keys [(x, y, z, rx, ry, rz, frame)])."""
    data = path.read_bytes()
    head = struct.unpack_from("<4i", data, 0)
    at, records = 16, []
    for _ in range(head[1]):
        kind, frame, size = struct.unpack_from("<3i", data, at)
        records.append((kind, frame, data[at + 12:at + 12 + max(size, 0)]))
        at += 12 + max(size, 0)
    keys = [struct.unpack_from("<7f", data, head[2] + 28 * i) for i in range(head[3])] if head[3] else []
    return head, records, keys


def text(payload: bytes) -> str:
    return payload.split(b"\0")[0].decode("cp1251")


def playlist(records):
    """The child movies of a playlist: [(start time, name)]."""
    out = []
    for kind, frame, payload in records:
        if kind in (0, REC_CHILD) and payload:
            out.append((frame, Path(text(payload)).stem if text(payload).lower().endswith(".ani") else text(payload)))
    return out


class Cinema:
    def __init__(self, res: Path, game: Path):
        self.res, self.out = res, game / "resource"
        self.ani = index_files(res / "DESC")
        self.models = index_files(res / "MODELS")
        # the sounds of a movie sit in a folder of its own (Intro, Bunt, Arest...) or in the root of SOUNDS
        root = res / "SOUNDS"
        self.sounds = {p.stem.lower(): p for p in root.glob("*.wav")}
        for folder in sorted(root.iterdir(), key=lambda d: d.name.lower() == "intro"):
            if folder.is_dir():
                self.sounds.update({p.stem.lower(): p for p in folder.glob("*.wav")})
        self.textures = index_files(res / "TEXTURES")
        self.used_textures = set()
        self.lines = []

    def texture(self, stem):
        self.used_textures.add(stem.lower())
        return f"cinema\\{stem.lower()}.tga"

    def model(self, name: str, scene: str):
        """A still model of a scene as one .gm; returns the name the script loads or None."""
        cff = self.models.get(Path(name).name.lower())
        if cff is None:
            print(f"  {scene}: missing model {name}")
            return None
        stem = cff.stem.lower()
        dst = self.out / "models" / "cinema" / f"{stem}.gm"
        meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * K for c in p), texture=self.texture)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            write_gm(merge_by_texture(meshes, stem), dst, bsp=False)
        return f"cinema\\{stem}"

    @staticmethod
    def scene_flags(records: list):
        return [struct.unpack_from("<5f", p, 0) + (Path(text(p[24:56])).stem.lower(),) for kind, _, p in records if kind == REC_FLAG and len(p) >= 56]

    def cloths(self, flags: list, shape: int, scale=1.0):
        """The meshes of the flags (x y z size yaw texture) in one shape of the wave."""
        meshes = []
        for n, (x, y, z, size, yaw, tex) in enumerate(flags):
            width = size * FLAG_WIDTH * K * scale
            height = width * FLAG_ASPECT
            ax, az = math.sin(yaw), math.cos(yaw)
            nx, nz = -az, ax
            cols, rows = 10, 3
            texture = self.texture(tex)
            for face in (1.0, -1.0):
                mesh = Mesh(f"flag{n}", texture)
                ids = {}
                for i in range(cols + 1):
                    u = i / cols
                    phase = 2.0 * math.pi * (shape / FLAG_SHAPES - u * 0.9 + n * 0.37)
                    wave = FLAG_SWAY * width * u * math.sin(phase)
                    for j in range(rows + 1):
                        v = j / rows
                        sag = -0.05 * height * u * u
                        pos = (x * K + ax * width * u + nx * wave, y * K + height * (0.5 - v) + sag, z * K + az * width * u + nz * wave)
                        ids[i, j] = mesh.vertex(pos, (nx * face, 0.0, nz * face), (u, v))
                for i in range(cols):
                    for j in range(rows):
                        mesh.triangle(ids[i, j], ids[i + 1, j], ids[i, j + 1])
                        mesh.triangle(ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1])
                meshes.append(mesh)
        return meshes

    def flags(self, scene: str, records: list, skip=()):
        """The flags of a scene (records 6), waving: FLAG_SHAPES models of the same cloths in the shapes of a wave that runs along them, the
        script shows one at a time (cutscene.c, Cut_Flip). A cloth is x y z of its pole, size, yaw (the cloth runs along sin, cos of it)
        and a texture; both faces. Returns the names of the models."""
        flags = [f for f in self.scene_flags(records) if f not in skip]
        models = []
        for shape in range(FLAG_SHAPES if flags else 0):
            meshes = self.cloths(flags, shape)
            stem = f"{scene.lower()}_flag{shape}"
            dst = self.out / "models" / "cinema" / f"{stem}.gm"
            dst.parent.mkdir(parents=True, exist_ok=True)
            write_gm(merge_by_texture(meshes, stem), dst, bsp=False)
            models.append(f"cinema\\{stem}")
        return models

    def moving(self, name: str, scene: str, groups: list):
        """The animated part of a scene (_a.cff, NPCs, ships under way): its parts that share one
        track of keys are one rigid object, collected into groups [(meshes, keys)]."""
        cff = self.models.get(Path(name).name.lower())
        if cff is None:
            print(f"  {scene}: missing model {name}")
            return
        keys = read_keys(cff)
        meshes = cff2gm.cff_to_meshes(cff, place=lambda p: tuple(c * K for c in p), texture=self.texture)
        # the animated parts are stored mirrored in x against the still ones (the engine mirrors them on the screen)
        for mesh in meshes:
            mesh.vertices = [((-p[0], p[1], p[2]), (-n[0], n[1], n[2]), uv, b) for p, n, uv, b in mesh.vertices]
            mesh.triangles = [(a, c, b) for a, b, c in mesh.triangles]
        keys = [[(-k[0], k[1], k[2], k[3], -k[4], -k[5], *k[6:]) for k in track] for track in keys]
        if len(meshes) != len(keys) or not all(keys):
            print(f"  {scene}: {name} keys do not match the parts, skipped")
            return
        sane = lambda track: all(abs(c) < 1e5 for key in track for c in key)  # a few movies keep garbage keys
        by_track = {}
        for mesh, track in zip(meshes, keys):
            if not sane(track):
                continue
            by_track.setdefault(tuple(track), ([], track))[0].append(mesh)
        groups += list(by_track.values())

    @staticmethod
    def extent(parts, track, lo, hi):
        """Grows the box lo..hi over the corners of the parts of a group in every frame of its track."""
        t0 = [c * K for c in track[0][:3]]
        r0t = [[frame_matrix(*track[0][3:])[j][i] for j in range(3)] for i in range(3)]
        points = [p for part in parts for p, *_ in part.vertices]
        box = [(min(p[i] for p in points), max(p[i] for p in points)) for i in range(3)]
        corners = [(x, y, z) for x in box[0] for y in box[1] for z in box[2]]
        local = [[sum(r0t[i][k] * (c[k] - t0[k]) for k in range(3)) for i in range(3)] for c in corners]
        for key in track:
            m = frame_matrix(*key[3:])
            for v in local:
                for i in range(3):
                    w = sum(m[i][k] * v[k] for k in range(3)) + key[i] * K
                    lo[i], hi[i] = min(lo[i], w), max(hi[i], w)

    @staticmethod
    def cuts(keys):
        """The intervals between two camera keys that are a cut of the movie (the thresholds of Cut_IsJump in cutscene.c)."""
        def diff(a, b):
            d = abs(b - a) % (2 * math.pi)
            return min(d, 2 * math.pi - d)
        out = set()
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]
            move = sum(abs(b[j] - a[j]) for j in range(3)) * K
            if move > 1.0 or max(diff(a[3], b[3]), diff(a[4], b[4])) > 0.5:
                out.add(i)
        return out

    def write_moving(self, scene: str, groups: list, cuts=frozenset(), origin=(0.0, 0.0), late=0):
        """One skinned .gm and .an per scene: bone 0 is an empty root, every group a bone of its own
        that moves by the keys (the .an with MOVING_JOINTS: positions of every bone)."""
        frames = max(len(track) for _, track in groups)
        # the engine blends the keys, the camera holds the old shot over a cut: the actors that move to their places of the next shot
        # during that key would fly across the old one, so over a cut the bones hold the old key until the next one (STEP sub-frames a key)
        step = SUBSTEPS if cuts else 1

        def spread(values, lerp):
            out = []
            for i, v in enumerate(values[:-1]):
                n = values[i + 1]
                out += [v if i in cuts else lerp(v, n, j / step) for j in range(step)]
            return out + [values[-1]]

        def lerp_pos(a, b, t):
            return tuple(x + (y - x) * t for x, y in zip(a, b))

        def lerp_rot(a, b, t):
            sign = -1.0 if sum(x * y for x, y in zip(a, b)) < 0 else 1.0
            q = [x + (sign * y - x) * t for x, y in zip(a, b)]
            norm = math.sqrt(sum(c * c for c in q)) or 1.0
            return tuple(c / norm for c in q)

        meshes = []
        lo, hi = [1e9] * 3, [-1e9] * 3
        parents, joints = [-1], [(0.0, 0.0, 0.0)]
        positions = [[(0.0, 0.0, 0.0)] * ((frames - 1) * step + 1)]
        rotations = [[(0.0, 0.0, 0.0, 1.0)] * ((frames - 1) * step + 1)]
        for bone, (parts, track) in enumerate(groups, 1):
            track = list(track) + [track[-1]] * (frames - len(track))
            parents.append(0)
            shift = lambda p: (p[0] * K - origin[0], p[1] * K, p[2] * K - origin[1])
            joints.append(shift(track[0]))
            positions.append(spread([shift(key) for key in track], lerp_pos))
            rotations.append(spread([quaternion(frame_matrix(*key[3:])) for key in track], lerp_rot))
            for part in parts:
                part.vertices = [(p, n, uv, bone) for p, n, uv, _ in part.vertices]
                meshes.append(part)
            self.extent(parts, track, lo, hi)
            for part in parts:
                part.vertices = [((p[0] - origin[0], p[1], p[2] - origin[1]), n, uv, b) for p, n, uv, b in part.vertices]
        lo[0], hi[0], lo[2], hi[2] = lo[0] - origin[0], hi[0] - origin[0], lo[2] - origin[1], hi[2] - origin[1]
        if meshes:
            # the engine culls a model by the box of its bind pose: a degenerate triangle stretches the box over
            # everything the bones travel through, or the parts that left their first place vanish
            pad = Mesh("pad", meshes[0].texture)
            a, b = pad.vertex(lo, (0, 1, 0), (0, 0)), pad.vertex(hi, (0, 1, 0), (0, 0))
            pad.triangles.append((a, b, b))
            meshes.append(pad)
        stem = f"cinema_{scene.lower()}"
        write_gm(merge_by_texture(meshes, stem), self.out / "models" / "cinema" / f"{stem}.gm", skinned=True)
        write_an(self.out / "animation" / f"{stem}.an", 1000.0 / FRAME_MS * step, parents, joints, positions, rotations,
                 moving=True)
        ani = self.out / "animation" / f"{stem}.ani"
        ani.write_text(f"; converted by tools/pdm_cutscene.py\nanimation = {stem}.an\n\n[play]\nstart_time = 0\n"
                       f"end_time = {(frames - 1) * step}\nloop = false\n"
                       + (f"\n[late]\nstart_time = {late * step}\nend_time = {(frames - 1) * step}\nloop = false\n" if late else ""))
        return stem

    def sound(self, name: str, scene: str):
        src = self.sounds.get(name.lower())
        if src is None:
            print(f"  {scene}: missing sound {name}")
            return None
        dst = self.out / "sounds" / "cinema" / f"{src.stem.lower()}.wav"
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        return f"cinema\\{src.stem.lower()}.wav"

    def scene(self, name: str):
        path = self.ani.get(f"{name.lower()}.ani")
        head, records, keys = read_ani(path)
        key = name.lower()
        at = f"PdmCut.{key}"
        frames = max([f for k, f, _ in records if k == REC_END] or [len(keys)])
        add = self.lines.append
        add(f"void PdmCut_{key}()")
        add("{")
        add(f"\t{at}.frames = {frames};")
        if key in WATERS:
            add(f"\t{at}.water.r = {WATERS[key][0]}; {at}.water.g = {WATERS[key][1]}; {at}.water.b = {WATERS[key][2]};")
        if key in WEATHER_OF and not any(k == REC_SKY for k, _, _ in records):
            records = list(records) + [r for r in read_ani(self.ani[f"{WEATHER_OF[key]}.ani"])[1] if r[0] == REC_SKY][:1]
        if key in NO_SEA:
            add(f"\t{at}.room = 1;")
        add(f"\t{at}.sea = {int(any(k == REC_SKY for k, _, _ in records) and key not in NO_SEA)};")
        for kind, _, payload in records:
            if kind == REC_SKY:
                # 26 words of the weather (the fields of weather.ini, see docs/pdm-cutscenes.md), then four names of 48 bytes: sun, moon, sky, sea;
                # the textures of the original are closed, the game has three free skies: the mood of the shot picks one of them
                if not any(payload[:104]):
                    # Scene6 keeps an empty weather (the original lit its room with the weather of the shot before): take the room of Scene12
                    payload = next(pl for k, _, pl in read_ani(self.ani["scene12.ani"])[1] if k == REC_SKY)
                w = struct.unpack_from("<26I", payload, 0)
                scale = lambda c, k: min(int((c >> 16 & 255) * k), 255) << 16 | min(int((c >> 8 & 255) * k), 255) << 8 | min(int((c & 255) * k), 255)  # colour x intensity
                num = lambda i: struct.unpack("<f", struct.pack("<I", w[i]))[0]
                sky, sea_tex = (payload[o:o + 48].split(b"\0")[0].decode("latin1").lower() for o in (200, 248))
                preset = "overcast" if "overcast" in sky else "storm" if "cloud" in sky else "sunset" if sky in ("sky_r.tf", "sky_d.tf") else "day"
                preset = SKIES.get(name.lower(), preset)
                add(f'\t{at}.sky = "{preset}";')
                night = "night" in sea_tex and "overcast" not in sky
                add(f"\t{at}.night = {int(night)};")
                if night and key in NIGHT_DARK:
                    add(f"\t{at}.dark = {NIGHT_DARK[key]:.2f};")
                # the height of a wave of the original sea is sea_amplitude * 125 (sea.dll, GetHeight: the sum of three octaves is scaled to the peak 125 * amplitude)
                # the models and the camera sit a little over the level of the sea
                add(f"\t{at}.amp = {AMPS.get(key, num(18) * 125):.3f};")
                add(f"\t{at}.draft = {DRAFTS.get(name.lower(), DRAFT)};")
                add(f"\t{at}.lift = {CABIN_LIFT if key in NO_SEA else LIFT + 1.0 if night else LIFT};")  # the harbour of the night: the quay stands higher
                if key in TILTS:
                    add(f"\t{at}.tilt = {TILTS[key]:.4f};")
                # the colours are 0x00RRGGBB words; the sun is the direct light, the fog is the glow of the sky (or the colour of the sky)
                fog = w[15] & 0xFFFFFF or w[13] & 0xFFFFFF
                add(f"\t{at}.sun = {dim(w[7] & 0xFFFFFF, SUN_DIM.get(key, 1.0))}; {at}.ambient = {scale(w[5], num(4))}; {at}.fog = {fog};")
                add(f"\t{at}.height = {num(0):.3f}; {at}.azimuth = {num(6) + SUN_TURNS.get(key, 0.0):.3f}; {at}.moon = {max(-num(22), 0):.1f};")
                break
        for kind, frame, _ in records:
            if kind == REC_BINO:
                add(f"\t{at}.bino = {frame};")
        for kind, _, payload in records:
            if kind == REC_VIEW:
                add(f"\t{at}.fov = {struct.unpack_from('<f', payload, 0)[0]:.3f};")
        m = s = f = 0
        groups = []
        for kind, frame, payload in records:
            if kind == 0 and payload:
                model = text(payload)
                if not model.lower().endswith(".cff"):
                    continue
                if model.lower().endswith("_a.cff"):
                    self.moving(model, name, groups)
                    continue
                stem = self.model(model, name)
                if stem:
                    add(f'\t{at}.models.m{m} = "{stem}";')
                    m += 1
            elif kind == REC_SOUND:
                snd = self.sound(text(payload), name)
                if snd:
                    add(f'\t{at}.sounds.s{s}.frame = {frame}; {at}.sounds.s{s}.file = "{snd}";')
                    s += 1
            elif kind in (REC_FADE_A, REC_FADE_B):
                seconds = struct.unpack_from("<i", payload, 0)[0]
                add(f"\t{at}.fades.f{f}.frame = {frame}; {at}.fades.f{f}.seconds = {seconds};")
                f += 1
        # the ships far from the origin (over 150 units) are a model of their own that stands at its own origin: the engine
        # does not draw the bones that travel hundreds of units from the box of the rest
        far = [g for g in groups if math.hypot(g[1][0][0], g[1][0][2]) * K > FAR_UNITS]
        groups = [g for g in groups if g not in far]
        # the flags of the far ships ride on their bones (the cloths do not wave there: they are a few pixels wide)
        far_flags = [f for f in self.scene_flags(records) if math.hypot(f[0], f[2]) * K > FAR_UNITS] if far else []
        for flag in far_flags:
            def gap(g):
                gx, _, gz = g[1][0][:3]
                return min(math.hypot(flag[0] - sx * gx, flag[2] - gz) for sx in (1, -1))
            nearest = min(far, key=gap)
            print(f"  {name}: flag at {flag[0]:.1f},{flag[2]:.1f} -> ship {nearest[1][0][0]:.1f},{nearest[1][0][2]:.1f} gap {gap(nearest):.2f}")
            nearest[0].extend(self.cloths([flag], 0, FAR_FLAG_SCALE))
        # the flags on a ship that is under way travel with it: they ride on the bones of the nearest moving part (a still cloth would stay behind)
        ride_flags = []
        for flag in self.scene_flags(records):
            if flag in far_flags or not groups:
                continue
            near = min(groups, key=lambda g: math.hypot(flag[0] - g[1][0][0], flag[2] - g[1][0][2]))
            travel = max(math.hypot(k[0] - near[1][0][0], k[2] - near[1][0][2]) for k in near[1])
            if math.hypot(flag[0] - near[1][0][0], flag[2] - near[1][0][2]) < RIDE_GAP and travel > RIDE_TRAVEL:
                near[0].extend(self.cloths([flag], 0, RIDE_FLAG_SCALE))
                ride_flags.append(flag)
        flag_models = self.flags(name, records, far_flags + ride_flags)
        if flag_models:
            add(f"\t{at}.flip.first = {m}; {at}.flip.count = {len(flag_models)};")
            for stem in flag_models:
                add(f'\t{at}.models.m{m} = "{stem}";')
                m += 1
        shots = [(frame, FX_KINDS[kind], struct.unpack_from("<3f", payload)) for kind, frame, payload in records
                 if kind in FX_KINDS and name.lower() in FX_SCENES]
        if shots:
            add(f"\t{at}.fx.count = {len(shots)};")
            for i, (frame, kind, (sx, sy, sz)) in enumerate(shots):
                add(f'\t{at}.fx.f{i}.frame = {frame}; {at}.fx.f{i}.kind = "{kind}"; {at}.fx.f{i}.x = {sx * K:.3f}; {at}.fx.f{i}.y = {sy * K:.3f}; {at}.fx.f{i}.z = {sz * K:.3f};')
        if groups:
            stem = self.write_moving(name, groups, self.cuts(keys), late=self.late.get(key, 0))
            add(f'\t{at}.actors = "cinema\\{stem}"; {at}.anim = "{stem}";')
        if far:
            origin = (sum(g[1][0][0] for g in far) / len(far) * K, sum(g[1][0][2] for g in far) / len(far) * K)
            stem = self.write_moving(name + "_far", far, self.cuts(keys), origin, late=self.late.get(key, 0))
            add(f'\t{at}.far.model = "cinema\\{stem}"; {at}.far.anim = "{stem}"; {at}.far.x = {origin[0]:.3f}; {at}.far.z = {origin[1]:.3f};')
        add(f"\t{at}.models.count = {m}; {at}.sounds.count = {s}; {at}.fades.count = {f};")
        for i, (x, y, z, rx, ry, rz, _) in enumerate(keys):
            add(f"\t{at}.cam.k{i}.x = {x * K:.3f}; {at}.cam.k{i}.y = {y * K:.3f}; {at}.cam.k{i}.z = {z * K:.3f}; "
                f"{at}.cam.k{i}.rx = {rx:.4f}; {at}.cam.k{i}.ry = {ry:.4f}; {at}.cam.k{i}.rz = {rz:.4f};")
        add(f"\t{at}.cam.count = {len(keys)};")
        add("}")
        add("")
        return key

    def write_textures(self):
        missing = []
        for stem in sorted(self.used_textures):
            src = self.textures.get(stem)
            if src is None:
                missing.append(stem)
                continue
            dst = self.out / "textures" / "cinema" / f"{stem}.tga.tx"
            dst.parent.mkdir(parents=True, exist_ok=True)
            convert_texture(src, dst)
        return missing


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    res, game = Path(sys.argv[1]), Path(sys.argv[2])
    res = res / "RESOURCE" if (res / "RESOURCE").is_dir() else res
    cinema = Cinema(res, game)
    scenes, lists = [], []
    for key in sorted(k for k in cinema.ani if k.endswith(".ani")):
        name = key[:-4]
        _, records, keys = read_ani(cinema.ani[key])
        if any(kind == REC_CHILD or (kind == 0 and text(payload).lower().endswith(".ani")) for kind, _, payload in records):
            children = playlist(records)
        else:
            children = [(0, name)]
        lists.append((name, children))
        scenes += [c.lower() for _, c in children if c.lower() not in scenes]
    scenes = [s.lower() for s in sys.argv[3:]] or scenes
    # the pieces of the movies that hand the camera over: the playlist plays them one after another
    for name, children in lists:
        if name.lower() in SPLICES:
            first = [i for i, (_, c) in enumerate(children) if c.lower() in {p[0] for p in SPLICES[name.lower()]}]
            if first:
                rest = [c for i, c in enumerate(children) if i not in first]
                children[:] = rest[:first[0]] + [(children[first[0]][0], n, a, b) for n, a, b in SPLICES[name.lower()]] + rest[first[0]:]
    cinema.late = {n: a for pieces in SPLICES.values() for n, a, _ in pieces if a}
    done = [cinema.scene(s) for s in scenes]
    init = ["void PdmCut_Init()", "{"]
    for name, children in lists:
        init.append(f"\tPdmCut.{name}.count = {len(children)};")
        for i, (frame, child, *piece) in enumerate(children):
            init.append(f'\tPdmCut.{name}.c{i}.start = {frame}; PdmCut.{name}.c{i}.scene = "{child.lower()}";'
                        + (f" PdmCut.{name}.c{i}.first = {piece[0]}; PdmCut.{name}.c{i}.last = {piece[1]};" if piece else ""))
    init.append("}")
    load = ["", "void PdmCut_Load(string scene)", "{"]
    load += [f'\tif (scene == "{k}") {{ PdmCut_{k}(); return; }}' for k in done]
    load += ["}", ""]
    path = game / "program" / "data" / "pdm_cutscenes.c"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// written by tools/pdm_cutscene.py from DESC/*.ani\nobject PdmCut;\n\n"
                    + "\n".join(cinema.lines) + "\n".join(init) + "\n" + "\n".join(load), encoding="cp1251")
    missing = cinema.write_textures()
    print(f"{len(done)} scenes" + (f", missing textures {' '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
