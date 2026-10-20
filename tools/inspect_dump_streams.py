"""Inspect crash.dmp custom streams to find module base addresses."""
import struct

p = r"C:\corsairs-remake\engine\build\default\Debug\crash.dmp"
with open(p, 'rb') as f:
    data = f.read(0x20000)  # first 128KB is enough for header+streams

def dump(off, n, label):
    print("\n=== %s (file offset 0x%X, %d bytes) ===" % (label, off, n))
    for o in range(0, n, 16):
        b = data[off + o:off + o + 16]
        if not b:
            break
        hexs = ' '.join('%02X' % x for x in b)
        asc = ''.join(chr(x) if 32 <= x < 127 else '.' for x in b)
        print('%06X  %-48s  %s' % (off + o, hexs, asc))

# Memory64List stream: rva=0x648 size=0xA8 -> (base, size) pairs
dump(0x648, 0xA8, "Memory64List")
mem = []
cnt = struct.unpack_from('<I', data, 0x648)[0]
print("run count:", cnt)
for i in range(cnt):
    off = 0x648 + 4 + i * 12
    base, size = struct.unpack_from('<QI', data, off)
    mem.append((base, size))
    print("  run[%d] base=0x%016X size=0x%X" % (i, base, size))

dump(0xF4, 0x200, "T15 stream")
dump(0xA54, 0x200, "T17 stream")
dump(0x3D4C, 0x1F4, "T21 stream")
dump(0x3F38, 0x280, "T22 stream + module name table")

# Exception stream
dump(0x6F0, 0x100, "Exception stream")
