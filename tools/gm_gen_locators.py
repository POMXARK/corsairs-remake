"""Generates a minimal Storm Engine 2.8 .gm (RDF) file containing only locator labels.

Produces MainMenu_locators.gm for the Corsairs menu scene:
  - 11 locator labels (camera, menu02-07, Light, fonar, fire, seagull)
  - 1 dummy triangle (avoids CreateIndexBuffer(0) edge case)
  - All other sections zero-length

Usage: python gm_gen_locators.py [output_path]
Default output: ../korsari-run/resource/models/MainMenu/MainMenu_locators.gm
"""
import struct
import sys
from pathlib import Path

RDF_VERSION = 0x312E3035  # '1.05' multi-char constant


def identity_matrix(tx, ty, tz):
    """4x4 row-major: identity rotation + translation."""
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        tx, ty, tz, 1.0,
    ]


def camera_matrix():
    """Camera at P=(0,0,-10) looking toward +Z.

    BuildMatrix(0, pi, 0) rotation = diag(-1, 1, -1), translation=(0,0,-10).
    GetAngles recovers (0, pi, 0). SetCamera then places camera at (0,0,-10) looking +Z.
    """
    return [
        -1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, -1.0, 0.0,
        0.0, 0.0, -10.0, 1.0,
    ]


def build_string_table(strings):
    """Pack null-terminated strings into a contiguous blob.

    Returns (blob_bytes, list_of_offsets).
    """
    blob = b""
    offsets = []
    for s in strings:
        offsets.append(len(blob))
        blob += s.encode("latin-1") + b"\x00"
    return blob, offsets


def write_label(f, group_name_offset, name_offset, matrix):
    """Write one RDF_LABEL (108 bytes)."""
    f.write(struct.pack("<3i", group_name_offset, name_offset, 0))
    f.write(struct.pack("<16f", *matrix))
    f.write(struct.pack("<4i", 0, 0, 0, 0))   # bones
    f.write(struct.pack("<4f", 0.0, 0.0, 0.0, 0.0))  # weight


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\corsairs-remake\korsari-run\resource\models\MainMenu\MainMenu_locators.gm"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- String table ---
    strings = [
        "locators",  # group name for all labels
        "camera",
        "menu02",
        "menu03",
        "menu04",
        "menu05",
        "menu06",
        "menu07",
        "Light",
        "fonar",
        "fire",
        "seagull",
    ]
    globname, name_offsets = build_string_table(strings)
    name_size = len(globname)
    n_names = len(strings)

    # --- Label definitions: (string_index, matrix) ---
    labels = [
        (1, camera_matrix()),                              # camera
        (2, identity_matrix(0.0, 1.5, 0.0)),              # menu02
        (3, identity_matrix(0.0, 1.0, 0.0)),              # menu03
        (4, identity_matrix(0.0, 0.5, 0.0)),              # menu04
        (5, identity_matrix(0.0, 0.0, 0.0)),              # menu05
        (6, identity_matrix(0.0, -0.5, 0.0)),             # menu06
        (7, identity_matrix(0.0, -1.0, 0.0)),             # menu07
        (8, identity_matrix(0.0, 2.0, -5.0)),             # Light
        (9, identity_matrix(-3.0, 0.0, -5.0)),            # fonar
        (10, identity_matrix(3.0, 0.0, -5.0)),            # fire
        (11, identity_matrix(0.0, 2.0, -8.0)),            # seagull
    ]
    n_labels = len(labels)

    # --- Write file ---
    with open(out_path, "wb") as f:
        # RDF_HEAD (72 bytes)
        f.write(struct.pack("<11i",
            RDF_VERSION,   # version
            0,             # flags
            name_size,     # name_size
            n_names,       # names
            0,             # ntextures
            0,             # nmaterials
            0,             # nlights
            n_labels,      # nlabels
            0,             # nobjects
            1,             # ntriangles
            0,             # nvrtbuffs
        ))
        f.write(struct.pack("<7f",
            1.0, 1.0, 1.0,    # bbox_size
            0.0, 0.0, 0.0,    # bbox_center
            1.0,              # radius
        ))

        # globname
        f.write(globname)

        # names array (offsets into globname)
        f.write(struct.pack(f"<{n_names}i", *name_offsets))

        # labels (108 bytes each)
        for str_idx, mat in labels:
            write_label(f, name_offsets[0], name_offsets[str_idx], mat)

        # 1 dummy triangle
        f.write(struct.pack("<3H", 0, 0, 0))

    total = out_path.stat().st_size
    print(f"Wrote {out_path} ({total} bytes)")
    print(f"  name_size={name_size}, names={n_names}, nlabels={n_labels}, ntriangles=1")
    print(f"  labels: {', '.join(s for s in strings[1:])}")


if __name__ == "__main__":
    main()
