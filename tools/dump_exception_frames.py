import struct

path = r"C:\corsairs-remake\engine\build\default\Debug\crash.dmp"
with open(path, "rb") as f:
    data = f.read()

# Exception stream at 0x6F0, size 0x364
# First DWORD = 0x12 (18) - NOT a valid SizeOfExceptionRecord
# Let's try interpreting as array of records
off = 0x6F0
size = 0x364

# First: dump first 128 bytes with structure annotations
print("=== Exception stream raw (first 128 bytes) ===")
chunk = data[off:off+128]
for i in range(0, len(chunk), 16):
    row = chunk[i:i+16]
    hexs = " ".join(f"{b:02x}" for b in row)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    print(f"{off+i:06x}  {hexs:<48}  {asc}")

print()
print("=== Try: array of 32-byte records ===")
n_records = size // 32
for i in range(min(n_records, 20)):
    rec_off = off + i * 32
    # Try various interpretations
    d0 = struct.unpack_from("<I", data, rec_off)[0]
    d1 = struct.unpack_from("<I", data, rec_off+4)[0]
    d2 = struct.unpack_from("<I", data, rec_off+8)[0]
    d3 = struct.unpack_from("<I", data, rec_off+12)[0]
    d4 = struct.unpack_from("<I", data, rec_off+16)[0]
    d5 = struct.unpack_from("<I", data, rec_off+20)[0]
    d6 = struct.unpack_from("<I", data, rec_off+24)[0]
    d7 = struct.unpack_from("<I", data, rec_off+28)[0]
    q0 = struct.unpack_from("<Q", data, rec_off)[0]
    q1 = struct.unpack_from("<Q", data, rec_off+8)[0]
    q2 = struct.unpack_from("<Q", data, rec_off+16)[0]
    q3 = struct.unpack_from("<Q", data, rec_off+24)[0]
    print(f"  [{i:2d}] d: {d0:08x} {d1:08x} {d2:08x} {d3:08x} | {d4:08x} {d5:08x} {d6:08x} {d7:08x}")
    print(f"       q: {q0:016x} {q1:016x} {q2:016x} {q3:016x}")

print()
print("=== Try: first DWORD is count, then records ===")
count = struct.unpack_from("<I", data, off)[0]
print(f"  count = {count} (0x{count:x})")
if 1 <= count <= 100:
    # Maybe: [count(4)][records...]
    rec_start = off + 4
    for i in range(min(count, 20)):
        rec_off = rec_start + i * 32
        if rec_off + 32 > off + size:
            break
        d0 = struct.unpack_from("<I", data, rec_off)[0]
        d1 = struct.unpack_from("<I", data, rec_off+4)[0]
        d2 = struct.unpack_from("<I", data, rec_off+8)[0]
        d3 = struct.unpack_from("<I", data, rec_off+12)[0]
        d4 = struct.unpack_from("<I", data, rec_off+16)[0]
        d5 = struct.unpack_from("<I", data, rec_off+20)[0]
        d6 = struct.unpack_from("<I", data, rec_off+24)[0]
        d7 = struct.unpack_from("<I", data, rec_off+28)[0]
        print(f"  [{i:2d}] {d0:08x} {d1:08x} {d2:08x} {d3:08x} | {d4:08x} {d5:08x} {d6:08x} {d7:08x}")

print()
print("=== Try: QWORD-aligned records (each 16 bytes) ===")
n16 = size // 16
for i in range(min(n16, 30)):
    rec_off = off + i * 16
    q0 = struct.unpack_from("<Q", data, rec_off)[0]
    q1 = struct.unpack_from("<Q", data, rec_off+8)[0]
    print(f"  [{i:2d}] {q0:016x}  {q1:016x}")
