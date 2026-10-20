import struct

path = r"C:\corsairs-remake\engine\build\default\Debug\crash.dmp"
with open(path, "rb") as f:
    head = f.read(0x1000)

sig = head[0:4]
num_streams = struct.unpack_from("<I", head, 4)[0]
dir_rva = struct.unpack_from("<I", head, 8)[0]
checksum = struct.unpack_from("<I", head, 12)[0]
timestamp = struct.unpack_from("<I", head, 16)[0]
flags = struct.unpack_from("<Q", head, 20)[0]

print(f"sig={sig} num_streams={num_streams} dir_rva=0x{dir_rva:x}")
print(f"checksum=0x{checksum:08x} timestamp=0x{timestamp:08x} flags=0x{flags:x}")
print()

for off in range(0, 0x200, 16):
    chunk = head[off:off+16]
    hexs = " ".join(f"{b:02x}" for b in chunk)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{off:04x}  {hexs:<48}  {asc}")

print()
for i in range(num_streams):
    e = dir_rva + i * 12
    if e + 12 > len(head):
        break
    t, s, r = struct.unpack_from("<III", head, e)
    print(f"entry[{i}]: type={t} size=0x{s:x} rva=0x{r:x}")
