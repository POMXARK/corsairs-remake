"""Inspects a Storm Engine 2.8 .gm (RDF) geometry file and dumps its structure.

Usage: gm_inspect.py <file.gm>
"""
import struct
import sys
from pathlib import Path

FLAGS_BSP_PRESENT = 2


def main():
    path = Path(sys.argv[1])
    data = path.read_bytes()
    off = 0

    def rd(fmt):
        nonlocal off
        size = struct.calcsize("<" + fmt)
        vals = struct.unpack_from("<" + fmt, data, off)
        off += size
        return vals

    version, flags, name_size, names, ntextures, nmaterials, nlights, nlabels, nobjects, ntriangles, nvrtbuffs = rd("11i")
    _bbox = rd("7f")
    bbox_size, bbox_center, radius = _bbox[0:3], _bbox[3:6], _bbox[6]
    print(f"file size        : {len(data)}")
    print(f"version          : 0x{version:08X} ({chr(version & 255)}{chr((version >> 8) & 255)}{chr((version >> 16) & 255)}{chr((version >> 24) & 255)})")
    print(f"flags            : {flags}")
    print(f"name_size        : {name_size}")
    print(f"names            : {names}")
    print(f"ntextures        : {ntextures}")
    print(f"nmaterials       : {nmaterials}")
    print(f"nlights          : {nlights}")
    print(f"nlabels          : {nlabels}")
    print(f"nobjects         : {nobjects}")
    print(f"ntriangles       : {ntriangles}")
    print(f"nvrtbuffs        : {nvrtbuffs}")
    print(f"bbox_size        : {bbox_size}")
    print(f"bbox_center      : {bbox_center}")
    print(f"radius           : {radius}")

    globname = data[off:off + name_size]
    off += name_size
    print("\n-- globname (raw) --")
    for i in range(0, len(globname), 32):
        chunk = globname[i:i + 32]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {i:5d}  {hexs:<96}  {asc}")

    names_arr = rd(f"{names}i") if names else ()
    print("\n-- names array (offsets into globname) --")
    for i, o in enumerate(names_arr):
        s = globname[o:o + 64].split(b"\x00")[0].decode("latin-1", "replace")
        print(f"  [{i:2d}] off={o:5d}  {s!r}")

    if ntextures:
        tname = rd(f"{ntextures}i")
        print("\n-- texture name offsets --")
        for i, o in enumerate(tname):
            s = globname[o:o + 64].split(b"\x00")[0].decode("latin-1", "replace")
            print(f"  [{i}] off={o}  {s!r}")

    if nmaterials:
        print("\n-- materials --")
        for m in range(nmaterials):
            group_name, name = rd("2i")
            diffuse, specular, gloss, selfIllum = rd("4f")
            texture_type = rd("4i")
            texture = rd("4i")
            g = globname[group_name:group_name + 64].split(b"\x00")[0].decode("latin-1", "replace") if group_name < len(globname) else "?"
            n = globname[name:name + 64].split(b"\x00")[0].decode("latin-1", "replace") if name < len(globname) else "?"
            print(f"  [{m}] group={g!r} name={n!r} diff={diffuse:.2f} spec={specular:.2f} gloss={gloss:.2f} selfIllum={selfIllum:.2f}")
            print(f"       texture_type={texture_type}")
            print(f"       texture={texture}")

    if nlights:
        raise SystemExit("nlights != 0, RDF_LIGHT size not implemented in inspector")

    if nlabels:
        print("\n-- labels --")
        for l in range(nlabels):
            group_name, name, flags_l = rd("3i")
            mat = rd("16f")
            bones = rd("4i")
            weight = rd("4f")
            g = globname[group_name:group_name + 64].split(b"\x00")[0].decode("latin-1", "replace") if group_name < len(globname) else "?"
            n = globname[name:name + 64].split(b"\x00")[0].decode("latin-1", "replace") if name < len(globname) else "?"
            print(f"  [{l:2d}] group={g!r} name={n!r} flags=0x{flags_l:08X}")
            for row in range(4):
                print(f"       m[{row}] = {mat[row * 4:row * 4 + 4]}")
            print(f"       bones={bones} weight={weight}")

    if nobjects:
        print("\n-- objects --")
        for o in range(nobjects):
            group_name, name, flags_o = rd("3i")
            center = rd("3f")
            radius_o = rd("f")[0]
            vertex_buff, ntri_o, striangle, nvertices, svertex = rd("5i")
            material = rd("i")[0]
            lights = rd("8i")
            bones = rd("4i")
            atriangles = rd("i")[0]
            g = globname[group_name:group_name + 64].split(b"\x00")[0].decode("latin-1", "replace") if group_name < len(globname) else "?"
            n = globname[name:name + 64].split(b"\x00")[0].decode("latin-1", "replace") if name < len(globname) else "?"
            print(f"  [{o}] group={g!r} name={n!r} flags=0x{flags_o:08X}")
            print(f"       center={center} radius={radius_o}")
            print(f"       vertex_buff={vertex_buff} ntriangles={ntri_o} striangle={striangle} nvertices={nvertices} svertex={svertex}")
            print(f"       material={material} lights={lights} bones={bones} atriangles={atriangles}")

    if ntriangles:
        print("\n-- triangles --")
        for t in range(ntriangles):
            v = rd("3H")
            print(f"  [{t}] {v}")

    if nvrtbuffs:
        print("\n-- vertex buffers --")
        for v in range(nvrtbuffs):
            size, fmt = rd("2i")
            print(f"  [{v}] size={size} format={fmt}")
            off += size
            print(f"       (skipped {size} bytes of vertex data)")

    if flags & FLAGS_BSP_PRESENT:
        print("\n-- BSP present (not dumped) --")

    print(f"\nfinal offset: {off} / {len(data)} (tail = {len(data) - off} bytes)")
    if off < len(data):
        tail = data[off:off + 64]
        print("tail hex:", " ".join(f"{b:02x}" for b in tail))


if __name__ == "__main__":
    main()
