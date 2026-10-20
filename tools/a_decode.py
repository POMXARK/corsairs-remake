#!/usr/bin/env python3
"""Decode Sea Dogs (PDM) action files .a: byte i of every 8-byte block is rotated right by i bits.

Algorithm from AlexKimov/seadogs-file-formats scripts/010editor/decodeActionFile.1sc (MIT).
usage: a_decode.py <file.a | dir> [out_file | out_dir]
"""
import sys
from pathlib import Path


def decode(data: bytes) -> bytes:
    out = bytearray(data)
    for n, b in enumerate(out):
        i = n % 8
        out[n] = ((b >> i) | (b << (8 - i))) & 0xFF
    return bytes(out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    if src.is_dir():
        dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src
        for f in sorted(src.rglob("*")):
            if f.suffix.lower() == ".a":
                out = dst / f.relative_to(src).with_suffix(".a.txt")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(decode(f.read_bytes()))
    else:
        out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".a.txt")
        out.write_bytes(decode(src.read_bytes()))


if __name__ == "__main__":
    main()
