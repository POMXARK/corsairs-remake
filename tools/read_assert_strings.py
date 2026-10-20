import sys, struct
sys.stdout.reconfigure(encoding='utf-8')

exe_path = r'C:\corsairs-remake\engine\build\default\Debug\engine.exe'
with open(exe_path, 'rb') as f:
    data = f.read()

e_lfanew = struct.unpack_from('<I', data, 60)[0]
coff_off = e_lfanew + 4
machine, nsec = struct.unpack_from('<HH', data, coff_off)
opt_off = coff_off + 20
magic = struct.unpack_from('<H', data, opt_off)[0]
opt_size = struct.unpack_from('<H', data, coff_off + 16)[0]
sect_off = opt_off + opt_size

sections = []
for i in range(nsec):
    off = sect_off + i * 40
    name = data[off:off+8].rstrip(b'\x00').decode('latin-1')
    vsz, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', data, off + 8)
    sections.append((name, vaddr, vsz, rawptr, rawsz))

def rva_to_file(rva):
    for name, vaddr, vsz, rawptr, rawsz in sections:
        if vaddr <= rva < vaddr + vsz:
            return rawptr + (rva - vaddr)
    return None

targets = {
    'file1 (line 1534)': 0x16CD07C,
    'expr1 (line 1534)': 0x16CD088,
    'file2 (line 1536)': 0x16CD0C0,
    'expr2 (line 1536)': 0x16CD0C8,
}

for label, rva in targets.items():
    foff = rva_to_file(rva)
    if foff is None:
        print(f'{label}: RVA 0x{rva:X} not in any section')
        continue
    if foff >= len(data):
        print(f'{label}: file offset 0x{foff:X} beyond file size 0x{len(data):X}')
        continue
    chunk = data[foff:foff+256]
    end = chunk.find(b'\x00')
    if end < 0:
        end = len(chunk)
    s = chunk[:end].decode('utf-8', errors='replace')
    print(f'{label}: "{s}"')
