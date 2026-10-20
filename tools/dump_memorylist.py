import struct

path = r"C:\corsairs-remake\engine\build\default\Debug\crash.dmp"
with open(path, "rb") as f:
    data = f.read()

def hexdump(off, size, label):
    print(f"=== {label} (offset 0x{off:x}, {size} bytes) ===")
    chunk = data[off:off+size]
    for i in range(0, len(chunk), 16):
        row = chunk[i:i+16]
        hexs = " ".join(f"{b:02x}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"{off+i:06x}  {hexs:<48}  {asc}")
    print()

# MemoryList stream: type=6, size=0xA8, rva=0x648
# Standard MINIDUMP_MEMORY_LIST: [DWORD SizeOfStruct][DWORD NumberOfBlocks][MEMORY_DESCRIPTOR blocks...]
# MEMORY_DESCRIPTOR (x64): [QWORD BaseAddress][QWORD MemorySize][DWORD AllocationProtect][DWORD Type]
# Actually standard is:
#   MINIDUMP_MEMORY_DESCRIPTOR:
#     ULONG64 BaseAddress
#     ULONG SizeOfMemory
#   (for x64 minidump, that's it - 12 bytes per descriptor)
# But some writers use the full Windows MEMORY_DESCRIPTOR:
#   ULONG64 BaseAddress
#   ULONG SizeOfMemory  
#   ULONG32 AllocationProtect
#   ULONG8 CommitCharge

off = 0x648
size = 0xA8
hexdump(off, size, "MemoryList @0x648")

print()
print("=== Parse as MINIDUMP_MEMORY_LIST ===")
# First: check if it starts with SizeOfStruct + Count
sz_struct = struct.unpack_from("<I", data, off)[0]
print(f"  First DWORD: 0x{sz_struct:x} ({sz_struct})")

# Try: [count(4)] then array of [QWORD base][DWORD size] (12-byte records)
count = sz_struct
if count < 100:
    print(f"  Interpreting as count={count}")
    rec_off = off + 4
    for i in range(min(count, 30)):
        base = struct.unpack_from("<Q", data, rec_off + i*12)[0]
        msize = struct.unpack_from("<I", data, rec_off + i*12 + 8)[0]
        print(f"  [{i:2d}] Base=0x{base:016x} Size=0x{msize:x} ({msize/1024:.1f} KB)")

print()
print("=== Parse as [count(4)] then [QWORD base][QWORD size] (16-byte records) ===")
rec_off = off + 4
n16 = (size - 4) // 16
for i in range(min(n16, 20)):
    base = struct.unpack_from("<Q", data, rec_off + i*16)[0]
    msize = struct.unpack_from("<Q", data, rec_off + i*16 + 8)[0]
    print(f"  [{i:2d}] Base=0x{base:016x} Size=0x{msize:x}")

print()
print("=== Parse as raw QWORD pairs from start ===")
for i in range(size // 8):
    q0 = struct.unpack_from("<Q", data, off + i*8)[0]
    print(f"  [{i:2d}] 0x{q0:016x}")
