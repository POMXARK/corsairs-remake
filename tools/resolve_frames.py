import re, os

LOAD_BASE = 0x7FF752EA0000
PREFERRED_BASE = 0x140000000
IMAGE_SIZE = 0x32F6000

stack_path = r"C:\corsairs-remake\engine\build\default\Debug\crash_stack.txt"
with open(stack_path, "r") as f:
    content = f.read()

# Format: frame[N]=XXXXXXXXXXXXXXXX (no 0x prefix)
matches = re.findall(r'frame\[(\d+)\]=([0-9A-Fa-f]+)', content)
all_frames = [(int(idx), int(addr, 16)) for idx, addr in matches]
print(f"Total frames: {len(all_frames)}")

engine_frames = []
for idx, addr in all_frames:
    if LOAD_BASE <= addr < LOAD_BASE + IMAGE_SIZE:
        rva = addr - LOAD_BASE
        engine_frames.append((idx, addr, rva))

print(f"Engine frames: {len(engine_frames)}")
print(f"{'Idx':<5} {'Address':<22} {'RVA':<12} {'DisasmAddr'}")
print("-" * 60)
for idx, addr, rva in engine_frames:
    disasm = PREFERRED_BASE + rva
    print(f"[{idx:<3}] 0x{addr:016X}     0x{rva:08X}     0x{disasm:016X}")

# Now search disassembly
print(f"\nSearching C:\\engine_disasm.txt for {len(engine_frames)} addresses...")
disasm_path = r"C:\engine_disasm.txt"

# Build set of target address strings (16 zero-padded hex + colon)
targets = {}
for idx, addr, rva in engine_frames:
    disasm_addr = PREFERRED_BASE + rva
    key = f"{disasm_addr:016X}:"
    targets[key] = (idx, addr, rva)

print(f"Target address patterns: {len(targets)}")
for k in list(targets.keys())[:5]:
    print(f"  looking for: {k}")
print("  ...")

# Read and search
found = {}
with open(disasm_path, "r", encoding="utf-16-le", errors="ignore") as f:
    for lineno, line in enumerate(f):
        if not targets:
            break
        # Address format: "  000000014009B04B:" (2 spaces + 16 hex + colon)
        # Extract address part
        stripped = line.strip()
        if len(stripped) < 17 or stripped[16] != ':':
            continue
        key = stripped[:16] + ":"
        if key in targets:
            idx, addr, rva = targets[key]
            found[idx] = (addr, rva, lineno, line.rstrip())
            del targets[key]
            print(f"  [{idx}] RVA=0x{rva:08X} @line {lineno}: {line.rstrip()[:80]}")

print(f"\nFound {len(found)}/{len(engine_frames)} addresses in disassembly")

# Show context for each found address (re-read file around those lines)
if found:
    print("\n=== Disassembly at crash frame addresses ===")
    # Re-read to get context
    with open(disasm_path, "r", encoding="utf-16-le", errors="ignore") as f:
        lines = []
        target_lines = {v[2] for v in found.values()}
        for i, line in enumerate(f):
            if i in target_lines or any(abs(i - tl) < 3 for tl in target_lines if abs(i - tl) <= 5):
                lines.append((i, line.rstrip()))
    
    # Print grouped by frame index
    for idx in sorted(found.keys()):
        addr, rva, lineno, first_line = found[idx]
        print(f"\n  frame[{idx}] = 0x{addr:016X}  RVA=0x{rva:08X}  (disasm line {lineno})")
        # Print the matched line and a few after
        for i, l in lines:
            if abs(i - lineno) <= 4:
                marker = ">>>" if i == lineno else "   "
                print(f"  {marker} {i}: {l[:100]}")
