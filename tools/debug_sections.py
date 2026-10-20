import sys, struct
sys.stdout.reconfigure(encoding='utf-8')

exe_path = r'C:\corsairs-remake\engine\build\default\Debug\engine.exe'
with open(exe_path, 'rb') as f:
    data = f.read()

print(f"File size: 0x{len(data):X}")

e_lfanew = struct.unpack_from('<I', data, 60)[0]
print(f"e_lfanew: 0x{e_lfanew:X}")

coff_off = e_lfanew + 4
machine, nsec = struct.unpack_from('<HH', data, coff_off)
opt_size = struct.unpack_from('<H', data, coff_off + 16)[0]
opt_off = coff_off + 20
magic = struct.unpack_from('<H', data, opt_off)[0]
print(f"machine=0x{machine:X}, nsec={nsec}, opt_size=0x{opt_size:X}, magic=0x{magic:X}")

sect_off = opt_off + opt_size
print(f"Section table at: 0x{sect_off:X}")

for i in range(nsec):
    off = sect_off + i * 40
    name = data[off:off+8].rstrip(b'\x00').decode('latin-1')
    vsz, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', data, off + 8)
    print(f"  {name:8s} VA=0x{vaddr:08X} VSz=0x{vsz:08X} RawPtr=0x{rawptr:08X} RawSz=0x{rawsz:08X}")

# Check where our target RVAs fall
targets = [0x16CD07C, 0x16CD088, 0x16CD0C0, 0x16CD0C8]
for rva in targets:
    for i in range(nsec):
        off = sect_off + i * 40
        name = data[off:off+8].rstrip(b'\x00').decode('latin-1')
        vsz, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', data, off + 8)
        if vaddr <= rva < vaddr + vsz:
            foff = rawptr + (rva - vaddr)
            in_file = "OK" if foff < len(data) else "BEYOND FILE"
            print(f"  RVA 0x{rva:X} -> {name} file_off=0x{foff:X} [{in_file}]")
            break
