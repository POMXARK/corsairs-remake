#!/usr/bin/env python3
"""Reads constants out of a 32-bit DLL of the original by their virtual address.

Ghidra prints a constant of the code as _DAT_1000c200; this shows what lies there as float, double
and int, so the logic found in the decompiled C gets its numbers.

usage: pe_const.py <file.dll> <address>...   (addresses in hex, as Ghidra shows them)
"""
import struct
import sys


def main():
    data = open(sys.argv[1], "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    table = pe + 24 + optional

    def offset(va):
        rva = va - base
        for k in range(sections):
            size, start, raw_size, raw = struct.unpack_from("<IIII", data, table + 40 * k + 8)
            if start <= rva < start + max(size, raw_size):
                return raw + rva - start
        return None

    for arg in sys.argv[2:]:
        va = int(arg.removeprefix("_DAT_"), 16)
        o = offset(va)
        if o is None:
            print(f"{va:#x}  not in the file")
            continue
        f, = struct.unpack_from("<f", data, o)
        d, = struct.unpack_from("<d", data, o)
        i, = struct.unpack_from("<i", data, o)
        print(f"{va:#x}  float {f:.9g}  double {d:.9g}  int {i}")


if __name__ == "__main__":
    main()
