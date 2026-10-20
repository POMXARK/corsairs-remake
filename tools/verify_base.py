import struct

# Verify engine.exe load base hypothesis: 0x7FF752EA0000
# from MemoryList stream in crash.dmp

base_candidate = 0x7FF752EA0000

# Crash frames from crash_stack.txt (the main cluster in engine range)
frames = [
    0x7FF752F3B04B,
    0x7FF75370D43B,
    0x7FF7537122D6,
    0x7FF753CF2535,
]

print(f"Base candidate: 0x{base_candidate:016X}")
print(f"{'Frame':<20} {'RVA':<12} {'In 35MB?'}")
print("-" * 50)
for fr in frames:
    rva = fr - base_candidate
    in_range = 0 <= rva < 0x2300000
    print(f"0x{fr:016X}     0x{rva:08X}     {in_range}")

print()
# Also check the addresses from MemoryList
memlist_addrs = [
    0x7FF754ED98A0,
    0x7FF752EA0000,
    0x7FF755F5B000,
    0x7FFE683D055C,
    0x7FFE6AB26C6F,
]
print("MemoryList addresses vs base:")
for a in memlist_addrs:
    rva = a - base_candidate
    print(f"  0x{a:016X}  RVA=0x{rva:08X}  in_image={0 <= rva < 0x2300000}")

print()
# Check alignment
print(f"Base & 0xFFF = 0x{base_candidate & 0xFFF:x} (4KB aligned: {base_candidate % 0x1000 == 0})")
print(f"Base & 0xFFFFF = 0x{base_candidate & 0xFFFFF:x} (1MB aligned: {base_candidate % 0x100000 == 0})")
print(f"Base & 0x1FFFFF = 0x{base_candidate & 0x1FFFFF:x} (2MB aligned: {base_candidate % 0x200000 == 0})")
