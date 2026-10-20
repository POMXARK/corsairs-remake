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

# Exception stream: SizeOfRecord(4) + record
rec_off = 0x6F0 + 4
code = struct.unpack_from("<I", data, rec_off)[0]
flags = struct.unpack_from("<I", data, rec_off+4)[0]
rec_ptr = struct.unpack_from("<Q", data, rec_off+8)[0]
exc_addr = struct.unpack_from("<Q", data, rec_off+16)[0]
num_params = struct.unpack_from("<I", data, rec_off+24)[0]
print(f"ExceptionCode=0x{code:08x} Flags=0x{flags:x} Record=0x{rec_ptr:x} Address=0x{exc_addr:016x} NumParams={num_params}")
print()

hexdump(0x6F0, 0x364, "Exception stream")
hexdump(0xF4, 0x300, "T15 @0xF4")
hexdump(0xA54, 0x300, "T17 @0xA54")
hexdump(0x3F38, 0x98, "T22 @0x3F38")

# find engine.exe UTF-16LE occurrences
needle = "engine.exe".encode("utf-16-le")
pos = 0
print("=== 'engine.exe' UTF-16LE occurrences ===")
while True:
    pos = data.find(needle, pos)
    if pos == -1:
        break
    print(f"  offset 0x{pos:x}")
    pos += 2
