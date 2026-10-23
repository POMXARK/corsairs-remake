#!/usr/bin/env python3
"""What is inside a GLB: triangles per mesh, the maps of every material and the size of every image.
Standard library only.

usage: pdm_glb_info.py model.glb [more.glb ...]
"""
import json
import struct
import sys


def read(path):
    with open(path, "rb") as f:
        magic, _, _ = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF":
            sys.exit(f"pdm_glb_info: {path} is not a GLB")
        length, kind = struct.unpack("<I4s", f.read(8))
        if kind != b"JSON":
            sys.exit(f"pdm_glb_info: {path} has no JSON chunk first")
        return json.loads(f.read(length))


def png_size(path, gltf, image):
    """The pixel size of an embedded PNG/JPEG without decoding it (the header only)."""
    view = gltf["bufferViews"][image["bufferView"]]
    with open(path, "rb") as f:
        f.seek(12)
        while True:
            length, kind = struct.unpack("<I4s", f.read(8))
            if kind == b"BIN\0":
                base = f.tell()
                break
            f.seek(length, 1)
        f.seek(base + view.get("byteOffset", 0))
        head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for path in sys.argv[1:]:
        g = read(path)
        acc = g.get("accessors", [])
        print(path)
        for m in g.get("meshes", []):
            for p in m["primitives"]:
                n = acc[p["indices"]]["count"] // 3 if "indices" in p else acc[p["attributes"]["POSITION"]]["count"] // 3
                attrs = ",".join(sorted(p["attributes"]))
                print(f"  mesh {m.get('name', '?')}: {n:,} triangles, material {p.get('material')}, {attrs}")
        for i, mat in enumerate(g.get("materials", [])):
            pbr = mat.get("pbrMetallicRoughness", {})
            maps = {"baseColor": pbr.get("baseColorTexture"), "metallicRoughness": pbr.get("metallicRoughnessTexture"),
                    "normal": mat.get("normalTexture"), "occlusion": mat.get("occlusionTexture"),
                    "emissive": mat.get("emissiveTexture")}
            print(f"  material {i} {mat.get('name', '?')}: " + ", ".join(
                f"{k}={'image ' + str(g['textures'][v['index']].get('source')) if v else '-'}" for k, v in maps.items()))
        for i, im in enumerate(g.get("images", [])):
            print(f"  image {i}: {im.get('mimeType')} {png_size(path, g, im) if 'bufferView' in im else im.get('uri')}")


if __name__ == "__main__":
    main()
