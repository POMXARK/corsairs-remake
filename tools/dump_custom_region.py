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

# Custom region between directory end and first stream data
# Directory is at 0x20, 13 entries * 8 bytes = 104 bytes = 0x68, ends at 0x88
# But stream data starts at 0xB0 (per prior analysis)
hexdump(0x88, 0x1C8, "Custom region 0x88-0x250")

# Also dump the area with small offsets (0x430-0x442 range)
# Let's look at a wider window around where version strings are
hexdump(0x250, 0x1F8, "Custom region 0x250-0x448")
