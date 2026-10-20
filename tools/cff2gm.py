"""Converts .cff (Cyclone/Sea Dogs quantized model) to .gm (Storm Engine RDF) format.

Usage:
  cff2gm.py <input.cff> [output.gm]
  cff2gm.py --batch <src_dir> <dst_dir>

The CFF format stores positions and UVs as int16 quantized into a per-file bounding box,
with per-vertex RGB color (0..127). This tool dequantizes positions/UVs, computes smooth
vertex normals from face cross-products, and writes a standard Storm RDF .gm file.
"""
import math
import struct
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "engine" / "demos"
sys.path.insert(0, str(DEMOS / "common"))
from storm_formats import Mesh, write_gm  # noqa: E402


class CFFReader:
    def __init__(self, data: bytes):
        self.data = data
        self.off = 0

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.data, self.off)[0]
        self.off += 4
        return v

    def u8(self) -> int:
        v = self.data[self.off]
        self.off += 1
        return v

    def i16(self) -> int:
        v = struct.unpack_from("<h", self.data, self.off)[0]
        self.off += 2
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.data, self.off)[0]
        self.off += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.data, self.off)[0]
        self.off += 4
        return v

    def skip(self, n: int):
        self.off += n

    def bytes(self, n: int) -> bytes:
        v = self.data[self.off:self.off + n]
        self.off += n
        return v


def _parse_meshes_at(data: bytes, off: int, lod_count: int, vert_size: int):
    """Try to parse all LOD/mesh data starting at offset with given vertex size.
    Returns (lods, success)."""
    r = CFFReader(data)
    r.off = off
    lods = []
    for _ in range(lod_count):
        mesh_count = r.u32()
        if mesh_count > 10000:
            return None, False
        r.skip(4)
        meshes = []
        for _ in range(mesh_count):
            if r.off + 44 > len(data):
                return None, False
            mesh_origin = (r.f32(), r.f32(), r.f32())
            uv_delim = r.f32()
            radius = r.f32()
            tex_index = r.u32()
            vertex_count = r.u32()
            face_count = r.u32()
            r.u32()  # unknown flag
            anim_key_count = r.u32()
            if vertex_count > 100000 or face_count > 200000 or anim_key_count > 10000:
                return None, False
            mesh_name = r.bytes(4)

            face_size = 6 if vertex_count > 256 else 3
            needed = vertex_count * vert_size + face_count * face_size + anim_key_count * 28
            if r.off + needed > len(data):
                return None, False

            vertices = []
            for _ in range(vertex_count):
                x, y, z = r.i16(), r.i16(), r.i16()
                u, v = r.i16(), r.i16()
                r.skip(vert_size - 10)  # color bytes (2 or 3)
                vertices.append((x, y, z, u, v))

            faces = []
            for _ in range(face_count):
                if vertex_count > 256:
                    a, b, c = r.u16(), r.u16(), r.u16()
                else:
                    a, b, c = r.u8(), r.u8(), r.u8()
                faces.append((a, b, c))

            r.skip(anim_key_count * 28)

            raw = mesh_name.rstrip(b'\x00')
            try:
                mesh_nm = raw.decode("ascii")
            except UnicodeDecodeError:
                mesh_nm = ""
            meshes.append({
                "name": mesh_nm,
                "uv_delim": uv_delim,
                "tex_index": tex_index,
                "vertices": vertices,
                "faces": faces,
            })
        lods.append(meshes)
    return lods, True


def parse_cff(path: Path):
    """Parse a .cff file. Returns (origin, scale, textures, meshes)."""
    data = path.read_bytes()
    r = CFFReader(data)

    # FILE_HEADER (44 bytes)
    origin = (r.f32(), r.f32(), r.f32())
    scale = (r.f32(), r.f32(), r.f32())
    texture_count = r.u32()
    material_count = r.u32()
    lod_count = r.u32()
    r.skip(4)  # section_offset / bsp
    r.skip(4)  # cull_radius (LOD switch distance)

    # TEXTURES: uint8 length + raw bytes
    textures = []
    for _ in range(texture_count):
        length = r.u8()
        name = r.bytes(length).decode("utf-8", errors="replace")
        textures.append(name)

    # MATERIALS: skip (36B header + count + count*20B per material)
    for _ in range(material_count):
        r.skip(36)
        count = r.u32()
        r.skip(count * 20)

    mesh_section_start = r.off

    # Determine vertex size: try 13B first (most common), fall back to 12B
    lods, ok = _parse_meshes_at(data, mesh_section_start, lod_count, 13)
    if not ok:
        lods, ok = _parse_meshes_at(data, mesh_section_start, lod_count, 12)
    if not ok:
        raise ValueError(f"Cannot parse mesh data (tried 13B and 12B vertices)")

    return origin, scale, textures, lods


def compute_normals(positions, faces):
    """Compute smooth per-vertex normals (area-weighted average of face normals)."""
    n = len(positions)
    acc = [[0.0, 0.0, 0.0] for _ in range(n)]

    for a, b, c in faces:
        pa, pb, pc = positions[a], positions[b], positions[c]
        e1 = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        e2 = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        fn = (
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0],
        )
        for idx in (a, b, c):
            acc[idx][0] += fn[0]
            acc[idx][1] += fn[1]
            acc[idx][2] += fn[2]

    result = []
    for nx, ny, nz in acc:
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length > 1e-12:
            result.append((nx / length, ny / length, nz / length))
        else:
            result.append((0.0, 1.0, 0.0))
    return result


def cff_to_gm(cff_path: Path, gm_path: Path) -> bool:
    """Convert one .cff to .gm. Returns True on success."""
    origin, scale, textures, lods = parse_cff(cff_path)

    if not lods or not lods[0]:
        return False

    # Use LOD 0 (highest detail)
    cff_meshes = lods[0]
    meshes = []

    for mi, mdata in enumerate(cff_meshes):
        tex_idx = mdata["tex_index"]
        if tex_idx < len(textures):
            tex_name = textures[tex_idx].split(".")[0]
        else:
            tex_name = "default"

        uv_delim = mdata["uv_delim"]
        if uv_delim == 0.0:
            uv_delim = 1.0

        # Dequantize positions and UVs
        positions = []
        uvs = []
        for x, y, z, u, v in mdata["vertices"]:
            px = origin[0] + x * scale[0] / 32767.0
            py = origin[1] + y * scale[1] / 32767.0
            pz = origin[2] + z * scale[2] / 32767.0
            positions.append((px, py, pz))
            uvs.append((u / uv_delim, v / uv_delim))

        # CFF stores back-facing winding; reverse to CCW front-facing
        faces = [(a, c, b) for a, b, c in mdata["faces"]]

        # Compute smooth normals
        normals = compute_normals(positions, faces)

        # Use actual CFF mesh name (e.g. "hull", "mast1")
        name = mdata["name"] if mdata["name"] else f"mesh_{mi}"
        m = Mesh(name, tex_name)
        for pos, normal, uv in zip(positions, normals, uvs):
            m.vertex(pos, normal, uv)
        for a, b, c in faces:
            m.triangle(a, b, c)

        meshes.append(m)

    write_gm(meshes, gm_path)
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--batch":
        if len(sys.argv) < 4:
            print("Usage: cff2gm.py --batch <src_dir> <dst_dir>")
            sys.exit(1)
        src = Path(sys.argv[2])
        dst = Path(sys.argv[3])
        dst.mkdir(parents=True, exist_ok=True)
        ok = 0
        fail = 0
        for cff_file in sorted(src.rglob("*.cff")):
            rel = cff_file.relative_to(src)
            gm_file = dst / (rel.with_suffix(".gm"))
            gm_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                if cff_to_gm(cff_file, gm_file):
                    ok += 1
                else:
                    fail += 1
                    print(f"  SKIP: {cff_file.name} (no meshes)")
            except Exception as e:
                fail += 1
                print(f"  ERROR: {cff_file.name}: {e}")
        print(f"Done: {ok} converted, {fail} failed")
    else:
        cff_path = Path(sys.argv[1])
        gm_path = Path(sys.argv[2]) if len(sys.argv) > 2 else cff_path.with_suffix(".gm")
        if cff_to_gm(cff_path, gm_path):
            print(f"OK: {cff_path.name} -> {gm_path}")
        else:
            print(f"FAILED: {cff_path.name} (no meshes)")
            sys.exit(1)


if __name__ == "__main__":
    main()
