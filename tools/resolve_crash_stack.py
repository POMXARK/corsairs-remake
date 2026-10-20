"""
Resolve crash stack frames against engine.exe disassembly.

1. Parse crash.dmp MINIDUMP_MODULE_LIST_STREAM -> exact engine.exe BaseOfImage (ASLR base)
2. Read raw frames from crash_stack.txt
3. Compute RVAs for engine frames
4. Single-pass scan of C:\engine_disasm.txt (UTF-16LE) to map each RVA -> containing function + offset

Usage: python tools\resolve_crash_stack.py
"""
import struct
import sys
import time

DUMP_PATH = r"C:\corsairs-remake\engine\build\default\Debug\crash.dmp"
STACK_PATH = r"C:\corsairs-remake\engine\build\default\Debug\crash_stack.txt"
DISASM_PATH = r"C:\engine_disasm.txt"


def parse_dump_modules(path):
    """Return list of (base, size, name) from MINIDUMP_MODULE_LIST_STREAM."""
    with open(path, 'rb') as f:
        raw = f.read(16384)
    sig, version, num_streams, stream_dir_rva = struct.unpack_from('<IIII', raw, 0)
    if sig != 0x504D444D:
        raise SystemExit("not a minidump")
    streams = []
    for i in range(num_streams):
        off = stream_dir_rva + i * 12
        if off + 12 > len(raw):
            break
        stype, ssize, srva = struct.unpack_from('<III', raw, off)
        streams.append((stype, ssize, srva))
    mod_stream = next((s for s in streams if s[0] == 0), None)
    if not mod_stream:
        return []
    _, msize, mrva = mod_stream
    with open(path, 'rb') as f:
        f.seek(mrva)
        data = f.read(msize)
    num_modules = struct.unpack_from('<I', data, 0)[0]
    mod_size = (msize - 4) // num_modules
    modules = []
    for i in range(num_modules):
        off = 4 + i * mod_size
        base = struct.unpack_from('<Q', data, off)[0]
        size = struct.unpack_from('<I', data, off + 8)[0]
        name_bytes = data[off + 112: off + 112 + 512]
        name = name_bytes.decode('utf-16-le', 'replace').split('\x00')[0].strip()
        modules.append((base, size, name))
    return modules


def read_stack_frames(path):
    frames = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('frame['):
                addr = int(line.split('=')[1].strip(), 16)
                frames.append(addr)
    return frames


def scan_disasm(disasm_path, targets):
    """
    Single pass over disasm. targets: sorted list of (rva, frame_idx).
    Returns dict frame_idx -> (func_name, func_start_rva, offset_in_func).
    Tracks function label lines ("name:") and address lines ("0000000140XXXXXXXX: ...").
    """
    results = {}
    cur_func = None
    cur_func_start = None
    target_idx = 0
    total = len(targets)

    with open(disasm_path, 'r', encoding='utf-16-le') as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            # Function label: ends with ':' and does not start with a hex digit
            if s.endswith(':') and len(s) > 2 and not s[0].isdigit():
                cur_func = s[:-1]
                cur_func_start = None
                continue
            # Address line: starts with 16 hex digits
            if len(s) >= 17 and s[0] in '0123456789':
                head = s[:16].strip()
                if len(head) != 16 or any(c not in '0123456789abcdefABCDEF' for c in head):
                    continue
                va = int(head, 16)
                if cur_func_start is None and cur_func is not None:
                    cur_func_start = va
                while target_idx < total and va > targets[target_idx][0]:
                    rva, fidx = targets[target_idx]
                    results[fidx] = (cur_func, cur_func_start)
                    target_idx += 1
                if target_idx >= total:
                    break
    return results


def main():
    print("=" * 72)
    print("CRASH STACK RESOLVER")
    print("=" * 72)

    print("\n[1] crash.dmp module list ...")
    modules = parse_dump_modules(DUMP_PATH)
    engine = None
    for base, size, name in modules:
        mark = ""
        if 'engine' in name.lower():
            engine = (base, size, name)
            mark = "  <<< ENGINE"
        print("    0x%016X  size=0x%X  %s%s" % (base, size, name, mark))

    if engine is None:
        raise SystemExit("engine module not found in dump")
    base, size, name = engine
    print("\n    engine.exe base = 0x%016X  size = 0x%X" % (base, size))

    print("\n[2] crash_stack.txt frames ...")
    frames = read_stack_frames(STACK_PATH)
    print("    %d frames" % len(frames))

    engine_frames = []
    for i, addr in enumerate(frames):
        if base <= addr < base + size:
            engine_frames.append((i, addr, addr - base))
        else:
            print("    [%2d] 0x%016X  (system)" % (i, addr))

    print("\n[3] resolving %d engine frames via disasm ..." % len(engine_frames))
    targets = sorted((rva, i) for i, _, rva in engine_frames)
    t0 = time.time()
    results = scan_disasm(DISASM_PATH, targets)
    print("    done in %.1fs" % (time.time() - t0))

    print("\n[4] RESOLVED STACK")
    print("=" * 72)
    IMAGE_BASE = 0x140000000
    for i, addr in enumerate(frames):
        if i in results:
            func, fstart = results[i]
            rva = addr - base
            extra = ""
            if fstart is not None:
                frva = fstart - IMAGE_BASE
                extra = "  (func start RVA 0x%08X, +0x%X)" % (frva, rva - frva)
            print("  [%2d] engine+0x%08X  %s%s" % (i, rva, func, extra))
        else:
            print("  [%2d] 0x%016X  (system)" % (i, addr))


if __name__ == '__main__':
    main()
