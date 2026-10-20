import struct, os

path = r"C:\corsairs-remake\engine\build\default\Debug\engine.exe"
sz = os.path.getsize(path)
print(f"File: {path}  size={sz} ({sz/1024/1024:.1f} MB)")

with open(path, "rb") as f:
    dos = f.read(64)
    pe_off = struct.unpack_from("<I", dos, 60)[0]
    f.seek(pe_off)
    sig = f.read(4)
    assert sig == b"PE\0\0", f"Not PE: {sig!r}"
    coff_data = f.read(20)
    # COFF: Machine(2) NSec(2) TDS(4) SymPtr(4) NumSym(4) OptSz(2) Chars(2) = 20
    machine, nsec, ts, sym_off, sym_sz, optsz, chars = struct.unpack("<HHIIIHH", coff_data)
    print(f"  COFF: Machine=0x{machine:x} NSections={nsec} OptSize={optsz} Chars=0x{chars:04x}")

    f.seek(pe_off + 24)
    opt = f.read(optsz)
    magic = struct.unpack_from("<H", opt, 0)[0]
    print(f"  OptionalHeader magic=0x{magic:x} (0x20b=PE32+, 0x10b=PE32)")
    if magic == 0x20b:
        image_base = struct.unpack_from("<Q", opt, 0x18)[0]
        section_align = struct.unpack_from("<I", opt, 0x1C)[0]
        file_align = struct.unpack_from("<I", opt, 0x20)[0]
        image_size = struct.unpack_from("<I", opt, 0x38)[0]
        subsys = struct.unpack_from("<H", opt, 0x44)[0]
        dll_chars = struct.unpack_from("<I", opt, 0x58)[0]
        print(f"  ImageBase=0x{image_base:016x}")
        print(f"  SectionAlign=0x{section_align:x} FileAlign=0x{file_align:x}")
        print(f"  SizeOfImage=0x{image_size:x} ({image_size/1024/1024:.1f} MB)")
        print(f"  Subsystem=0x{subsys:x}")
        print(f"  DLLCharacteristics=0x{dll_chars:08x}")
        DYNAMIC_BASE = bool(dll_chars & 0x0040)
        NX_COMPAT = bool(dll_chars & 0x0100)
        HIGH_ENTROPY_VA = bool(dll_chars & 0x0200)
        print(f"  DYNAMIC_BASE (ASLR): {DYNAMIC_BASE}")
        print(f"  NX_COMPAT: {NX_COMPAT}")
        print(f"  HIGH_ENTROPY_VA: {HIGH_ENTROPY_VA}")
    elif magic == 0x10b:
        image_base = struct.unpack_from("<I", opt, 0x1C)[0]
        section_align = struct.unpack_from("<I", opt, 0x20)[0]
        file_align = struct.unpack_from("<I", opt, 0x24)[0]
        image_size = struct.unpack_from("<I", opt, 0x38)[0]
        subsys = struct.unpack_from("<H", opt, 0x44)[0]
        dll_chars = struct.unpack_from("<H", opt, 0x46)[0]
        print(f"  ImageBase=0x{image_base:08x}")
        print(f"  SectionAlign=0x{section_align:x} FileAlign=0x{file_align:x}")
        print(f"  SizeOfImage=0x{image_size:x} ({image_size/1024/1024:.1f} MB)")
        print(f"  Subsystem=0x{subsys:x}")
        print(f"  DLLCharacteristics=0x{dll_chars:04x}")
        DYNAMIC_BASE = bool(dll_chars & 0x0040)
        print(f"  DYNAMIC_BASE (ASLR): {DYNAMIC_BASE}")

    sec_off = pe_off + 24 + optsz
    f.seek(sec_off)
    print(f"\n  Sections:")
    for i in range(nsec):
        sh = f.read(40)
        name = sh[:8].rstrip(b"\0").decode("ascii", errors="replace")
        vsz, rv, rawsz, rawptr = struct.unpack("<IIII", sh[8:24])
        chars = struct.unpack_from("<I", sh, 36)[0]
        print(f"    [{i}] {name:<8} VSz=0x{vsz:x} RVA=0x{rv:x} RawSz=0x{rawsz:x} RawPtr=0x{rawptr:x} Chars=0x{chars:08x}")
