#!/usr/bin/env python3
"""Makes 3D models of the views of pdm_model_views.py through the HTTP API of ComfyUI (docs/ai-models.md, ours).

The workflow is the template "Pixal3D & TRELLIS.2: Image to Model" or "Pixal3D: Multi Views to 3D"
exported by Workflow -> Export (API) into tools/model3d/. The script finds its nodes by their titles:
  IMAGE        Load Image, the front view;
  IMAGE_RIGHT, IMAGE_BACK, IMAGE_LEFT   Load Image, the other views (optional, a multi-view workflow);
  SEED         a node with a seed input (optional; fixed, a run repeats);
  FACES        the number of faces the mesh is decimated to (optional);
  SAVE         Save 3D, the GLB.
The input each of them takes is --seed-input / --faces-input; a node with a single number input takes
the number there whatever its name.

For every model with a <name>_front.png in the views and no <name>.glb yet: the views are uploaded to
input/pdm_models, the graph is queued, the file it saves is fetched by /view (ComfyUI may run on another
machine, `--listen`) to data/ai_models/glb/<name>.glb. A file that exists is skipped, so a run stops and
goes on; --redo <name> makes it again with the next seed. Then pdm_glb2gm.py puts it into the game.

usage: comfy_model_batch.py <game dir> [--workflow tools/model3d/image_to_model_api.json]
         [--comfy http://127.0.0.1:8188] [--only <name> ...] [--redo <name> ...] [--faces 20000] [--seed 1]
         [--quality draft|normal|high|max] [--set Class.input=value ...]

--quality changes the settings of the template's nodes that decide the detail: the remesh grid, the smoothing,
the number of faces, the size of the baked textures, the steps of the samplers (QUALITY below; normal leaves the
template as it is). --set does the same for one input of every node of a class, e.g. --set RemeshMesh.resolution=1280.
A run prints what was changed. The game takes the model after pdm_glb_optimize.py (--faces, --tex): a bigger
GLB is the source of that, not the size of the model in the game.
"""
import argparse
import base64
import copy
import json
import os
import socket
import struct
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from comfy_voice_batch import Comfy  # noqa: E402

VIEWS = {"IMAGE": "front", "IMAGE_RIGHT": "right", "IMAGE_BACK": "back", "IMAGE_LEFT": "left"}
MODEL_EXT = (".glb", ".gltf", ".obj", ".fbx", ".ply")
POLL = 2.0


class Comfy3D(Comfy):
    def result(self, pid):
        """The 3D file of a finished prompt, None while it runs; an error of the graph stops the run."""
        h = self.call(f"/history/{pid}")
        if pid not in h:
            return None
        status = h[pid].get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI: {json.dumps(status.get('messages', []), ensure_ascii=False)[:800]}")
        # Save 3D lists its file under a key of its own (3d, result, ...): any file of a 3D format
        for out in h[pid]["outputs"].values():
            for files in out.values():
                for f in files if isinstance(files, list) else ():
                    if isinstance(f, dict) and str(f.get("filename", "")).lower().endswith(MODEL_EXT):
                        return f
        raise RuntimeError(f"ComfyUI: no 3D file in the outputs of {pid}: is the SAVE node a Save 3D?")

    def fetch(self, a, to: Path):
        q = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""),
                                    "type": a.get("type", "output")})
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_bytes(urllib.request.urlopen(f"{self.url}/view?{q}", timeout=600).read())


class Progress:
    """The events of ComfyUI over its websocket (standard library only): which node runs, which step it is on.
    Without a connection the run goes on silently, the way it did before."""

    def __init__(self, url, client):
        self.sock = None
        self.node, self.step, self.steps, self.done = None, 0, 0, set()
        try:
            u = urllib.parse.urlparse(url)
            self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=2)
            key = base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((f"GET /ws?clientId={client} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\n"
                               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            head = b""
            while b"\r\n\r\n" not in head:
                head += self.sock.recv(1)
            if b" 101 " not in head.split(b"\r\n")[0]:
                raise OSError("no websocket")
        except OSError:
            self.sock = None

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return buf

    def _frame(self):
        b1, b2 = self._read(2)
        size = b2 & 0x7F
        if size == 126:
            size = struct.unpack(">H", self._read(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", self._read(8))[0]
        data = self._read(size)
        if b1 & 0x0F == 9:  # ping: a pong must be masked
            mask = os.urandom(4)
            self.sock.sendall(bytes([0x8A, 0x80 | len(data)]) + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))
        return b1 & 0x0F, data

    def poll(self, wait):
        """Reads the events for `wait` seconds."""
        if self.sock is None:
            time.sleep(wait)
            return
        end = time.time() + wait
        while (left := end - time.time()) > 0:
            self.sock.settimeout(left)
            try:
                op, data = self._frame()
            except (socket.timeout, TimeoutError):
                return
            except OSError:
                self.sock = None
                time.sleep(max(end - time.time(), 0))
                return
            if op != 1:
                continue
            m = json.loads(data)
            d = m.get("data", {})
            if m.get("type") == "executing" and d.get("node"):
                self.node, self.step, self.steps = d["node"], 0, 0
                self.done.add(d["node"])
            elif m.get("type") == "progress":
                self.node, self.step, self.steps = d.get("node", self.node), d["value"], d["max"]
                self.done.add(self.node)
            elif m.get("type") == "execution_cached":
                self.done.update(d.get("nodes", []))


def titled(graph, title):
    return next((n for n in graph.values() if n.get("_meta", {}).get("title") == title), None)


def set_number(node, name, value, title):
    """The input `name` of the node; a node with one number input takes it there whatever its name."""
    inputs = node["inputs"]
    if name not in inputs:
        numbers = [k for k, v in inputs.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(numbers) != 1:
            sys.exit(f"comfy_model_batch: node {title} has no input {name} (inputs: {', '.join(inputs)})")
        name = numbers[0]
    inputs[name] = value


# class of the node -> input -> value of every quality; the input is left alone if the graph has no such node
QUALITY = {
    "draft": {"RemeshMesh": {"resolution": 512, "smooth_iters": 20}, "DecimateMesh": {"target_face_count": 300000},
              "BakeTextureFromVoxel": {"texture_size": 1024}, "UnwrapMesh": {"resolution": 1024},
              "BakeAmbientOcclusion": {"resolution": 512}, "BakeNormalMapFromMesh": {"resolution": 1024}},
    "normal": {},
    "high": {"RemeshMesh": {"resolution": 1024, "smooth_iters": 2}, "DecimateMesh": {"target_face_count": 1500000},
             "BakeTextureFromVoxel": {"texture_size": 4096}, "UnwrapMesh": {"resolution": 4096},
             "BakeAmbientOcclusion": {"resolution": 2048}, "BakeNormalMapFromMesh": {"resolution": 4096},
             "KSampler": {"steps": ("min", 20)}},
    "max": {"RemeshMesh": {"resolution": 1280, "smooth_iters": 0}, "DecimateMesh": {"target_face_count": 2500000},
            "BakeTextureFromVoxel": {"texture_size": 4096}, "UnwrapMesh": {"resolution": 4096},
            "BakeAmbientOcclusion": {"resolution": 2048}, "BakeNormalMapFromMesh": {"resolution": 4096},
            "KSampler": {"steps": ("min", 30)}},
}


def apply_quality(graph, rules):
    """rules: class -> input -> value, or ("min", value) to raise the input to at least that. Returns the log."""
    log = []
    for nid, node in graph.items():
        for name, value in rules.get(node["class_type"], {}).items():
            old = node["inputs"].get(name)
            if old is None or isinstance(old, list):  # no such input, or it comes from another node
                continue
            if isinstance(value, tuple):
                value = max(old, value[1])
            if old != value:
                node["inputs"][name] = value
                log.append(f"{node['class_type']}[{nid}].{name}: {old} -> {value}")
    return log


def parse_set(items):
    rules = {}
    for item in items:
        try:
            key, value = item.split("=", 1)
            cls, name = key.split(".", 1)
            rules.setdefault(cls, {})[name] = json.loads(value)
        except ValueError:
            sys.exit(f"comfy_model_batch: --set takes Class.input=value, not {item}")
    return rules


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("game", type=Path)
    ap.add_argument("--workflow", type=Path, default=TOOLS / "model3d" / "image_to_model_api.json")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--views", type=Path)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--redo", nargs="*", default=[])
    ap.add_argument("--faces", type=int, default=20000, help="a skinned model holds 65536 vertices at most")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seed-input", default="seed")
    ap.add_argument("--faces-input", default="value")
    ap.add_argument("--quality", choices=QUALITY, default="normal")
    ap.add_argument("--set", nargs="*", default=[], metavar="Class.input=value")
    a = ap.parse_args()
    if not a.workflow.exists():
        sys.exit(f"comfy_model_batch: no {a.workflow}: export the template as API (docs/ai-models.md, step 3)")
    graph = json.loads(a.workflow.read_text(encoding="utf-8"))
    for title in ("IMAGE", "SAVE"):
        if titled(graph, title) is None:
            sys.exit(f"comfy_model_batch: no node titled {title} in the workflow (docs/ai-models.md, step 3)")
    log = apply_quality(graph, QUALITY[a.quality])
    log += apply_quality(graph, parse_set(a.set))
    if log:
        print("comfy_model_batch: quality " + a.quality + "\n  " + "\n  ".join(log))
    views = a.views or a.game / "data" / "ai_models" / "views"
    out = a.game / "data" / "ai_models" / "glb"
    names = sorted(p.name[:-len("_front.png")] for p in views.glob("*_front.png"))
    names = [n for n in names if not a.only or n in a.only]
    todo = [n for n in names if n in a.redo or not (out / f"{n}.glb").exists()]
    print(f"comfy_model_batch: {len(todo)} of {len(names)} models to make")
    comfy = Comfy3D(a.comfy)
    spent = []  # seconds of the models made in this run, for the estimate
    tries = {}
    if (out / "seeds.json").exists():
        tries = json.loads((out / "seeds.json").read_text())
    started = time.time()
    for k, name in enumerate(todo):
        g = copy.deepcopy(graph)
        for title, view in VIEWS.items():
            node = titled(g, title)
            if node is None:
                continue
            png = views / f"{name}_{view}.png"
            if not png.exists():
                sys.exit(f"comfy_model_batch: the workflow takes {title}, there is no {png}")
            comfy.upload(png, "pdm_models")
            node["inputs"]["image"] = f"pdm_models/{png.name}"
        seed = a.seed + tries.get(name, 0) + (1 if name in a.redo else 0)
        if (node := titled(g, "SEED")) is not None:
            set_number(node, a.seed_input, seed, "SEED")
        if (node := titled(g, "FACES")) is not None:
            set_number(node, a.faces_input, a.faces, "FACES")
        progress = Progress(a.comfy, "pdm-voice")
        pid = comfy.queue(g)
        t0 = time.time()
        while (f := comfy.result(pid)) is None:
            progress.poll(POLL)
            node = g.get(str(progress.node), {})
            title = node.get("_meta", {}).get("title") or node.get("class_type", "...")
            step = f" {progress.step}/{progress.steps}" if progress.steps else ""
            eta = f", about {max(sum(spent) / len(spent) - (time.time() - t0), 0) / 60:.0f} min left" if spent else ""
            print(f"\r{name}: node {len(progress.done)}/{len(g)} {title}{step}, {(time.time() - t0) / 60:.1f} min{eta}"
                  .ljust(100), end="", flush=True)
        print()
        spent.append(time.time() - t0)
        suffix = Path(f["filename"]).suffix.lower()
        comfy.fetch(f, out / f"{name}{suffix}")
        tries[name] = seed - a.seed
        (out / "seeds.json").write_text(json.dumps(tries, indent=1, sort_keys=True))
        left = (time.time() - started) / (k + 1) * (len(todo) - k - 1)
        print(f"{name}{suffix}: seed {seed}, {left / 60:.0f} min left", flush=True)


if __name__ == "__main__":
    main()
