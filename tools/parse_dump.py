#!/usr/bin/env python3
"""Parse Windows minidump to extract exception info, thread contexts, and loaded modules."""
import struct
import sys

def parse_minidump(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    # MINIDUMP_HEADER (28 bytes)
    signature = data[:4]
    if signature != b'MDMP':
        print(f"ERROR: Not a minidump (signature={signature})")
        return
    
    version = struct.unpack_from('<I', data, 4)[0]
    stream_count = struct.unpack_from('<I', data, 8)[0]
    stream_rva = struct.unpack_from('<I', data, 12)[0]
    
    print(f"Version: 0x{version:08X}, Streams: {stream_count}")
    
    # Parse stream directory (12 bytes per entry)
    streams = {}
    offset = stream_rva
    for i in range(stream_count):
        stype, size, rva = struct.unpack_from('<III', data, offset)
        offset += 12
        streams[stype] = (size, rva)
    
    print(f"Stream types: {[hex(k) for k in sorted(streams.keys())]}")
    
    # Exception stream (type 3 = MINIDUMP_EXCEPTION_STREAM)
    # Actually type 1 = thread list, 2 = module list, 3 = exception
    # Let me check: 
    # MINIDUMP_THREAD_LIST_STREAM = 0
    # MINIDUMP_MODULE_LIST_STREAM = 1
    # MINIDUMP_EXCEPTION_STREAM = 3
    # MINIDUMP_SYSTEM_INFO_STREAM = 4
    # MINIDUMP_THREAD_EXC_STREAM = 5
    
    # Actually the standard types are:
    # 0 = ThreadList, 1 = ModuleList, 2 = NotUsed, 3 = Exception, 
    # 4 = SystemInfo, 5 = ThreadExc, 6 = MemoryList, 7 = Memory64List
    
    # Exception stream (type 3)
    if 3 in streams:
        size, rva = streams[3]
        # MINIDUMP_EXCEPTION_STREAM: 
        #   DWORD ExceptionRecord (8 bytes actually - ULONG64)
        #   ... 
        # Actually it's:
        #   ULONG64 ExceptionRecord (points to EXCEPTION_RECORD in memory)
        #   DWORD ThreadId
        #   ULONG64 AdditionalInformation
        exc_record_ptr = struct.unpack_from('<Q', data, rva)[0]
        thread_id = struct.unpack_from('<I', data, rva + 8)[0]
        print(f"\n=== EXCEPTION ===")
        print(f"Exception record ptr: 0x{exc_record_ptr:016X}, ThreadId: {thread_id}")
    
    # Module list (type 1)
    modules = []
    if 1 in streams:
        size, rva = streams[1]
        module_count = struct.unpack_from('<I', data, rva)[0]
        mod_off = rva + 4
        print(f"\n=== MODULES ({module_count}) ===")
        for i in range(module_count):
            base = struct.unpack_from('<Q', data, mod_off)[0]
            img_size = struct.unpack_from('<I', data, mod_off + 8)[0]
            name_rva = struct.unpack_from('<I', data, mod_off + 20)[0]
            # Read module name (UTF-16LE null-terminated)
            name_end = data.index(b'\x00\x00', name_rva)
            name_bytes = data[name_rva:name_end]
            name = name_bytes.decode('utf-16-le', errors='replace')
            modules.append((base, img_size, name))
            mod_off += 36
        
        # Show interesting modules
        for base, size, name in modules:
            if 'engine' in name.lower() or 'd3d9' in name.lower():
                print(f"  0x{base:016X} - 0x{base+size:016X} ({size:#X}): {name}")
    
    # Thread list (type 0)
    if 0 in streams:
        size, rva = streams[0]
        thread_count = struct.unpack_from('<I', data, rva)[0]
        print(f"\n=== THREADS ({thread_count}) ===")
        
        # Thread exception stream (type 5)
        exc_thread_idx = -1
        if 5 in streams:
            size, rva = streams[5]
            exc_thread_idx = struct.unpack_from('<I', data, rva)[0]
            print(f"Exception thread index: {exc_thread_idx}")
        
        # MINIDUMP_THREAD: 48 bytes each
        # ThreadId(4) + SuspendCount(4) + ClientId(8) + ExceptionRecord(8) + ContextPointers(8) + Stack.Start(8) + Stack.Size(8)
        for i in range(thread_count):
            t_off = rva + 4 + i * 48
            tid = struct.unpack_from('<I', data, t_off)[0]
            ctx_rva = struct.unpack_from('<Q', data, t_off + 24)[0]
            marker = " <-- EXCEPTION" if i == exc_thread_idx else ""
            
            if i < 5 or marker:
                print(f"  Thread {i}: TID={tid}, CtxRVA=0x{ctx_rva:08X}{marker}")
            
            # Parse CONTEXT for exception thread
            if i == exc_thread_idx and ctx_rva > 0:
                # x64 CONTEXT layout (from Windows SDK):
                # Offset 0: P1Home..P6Home (48 bytes)
                # Offset 48: ContextFlags (4)
                # Offset 52: MxCsr (4)
                # Offset 56: SegCs (2), SegDs(2), SegEs(2), SegFs(2), SegGs(2), SegSs(2), EFlags(4) = 16 bytes
                # Offset 72: Dr0-Dr7 (36 bytes)  
                # Offset 108: Rax... wait let me recalculate
                
                # Actually the x64 CONTEXT structure:
                # 0x00: P1Home[6] (48 bytes)
                # 0x30: ContextFlags (4)
                # 0x34: MxCsr (4)  
                # 0x38: SegCs(2), SegDs(2), SegEs(2), SegFs(2), SegGs(2), SegSs(2), EFlags(4) = 16 bytes
                # 0x48: Dr0-Dr7 (8*4=32 bytes)
                # 0x68: Rax
                # 0x70: Rcx
                # 0x78: Rdx
                # 0x80: Rbx
                # 0x88: Rsp
                # 0x90: Rbp
                # 0x98: Rsi
                # 0xA0: Rdi
                # 0xA8: Rip
                
                rip = struct.unpack_from('<Q', data, ctx_rva + 0xA8)[0]
                rsp = struct.unpack_from('<Q', data, ctx_rva + 0x88)[0]
                rbp = struct.unpack_from('<Q', data, ctx_rva + 0x90)[0]
                rax = struct.unpack_from('<Q', data, ctx_rva + 0x68)[0]
                rbx = struct.unpack_from('<Q', data, ctx_rva + 0x80)[0]
                rcx = struct.unpack_from('<Q', data, ctx_rva + 0x70)[0]
                rdx = struct.unpack_from('<Q', data, ctx_rva + 0x78)[0]
                
                print(f"    RIP=0x{rip:016X} RSP=0x{rsp:016X} RBP=0x{rbp:016X}")
                print(f"    RAX=0x{rax:016X} RBX=0x{rbx:016X} RCX=0x{rcx:016X} RDX=0x{rdx:016X}")
                
                # Find which module RIP is in
                for base, size, name in modules:
                    if base <= rip < base + size:
                        print(f"    RIP in {name} at offset 0x{rip - base:08X}")
                        break
    
    # Memory list (type 7 = MINIDUMP_MEMORY64_LIST_STREAM or type 6)
    for mem_type in [6, 7]:
        if mem_type in streams:
            size, rva = streams[mem_type]
            mem_count = struct.unpack_from('<I', data, rva)[0]
            print(f"\n=== MEMORY (type {mem_type}) ===")
            print(f"Memory ranges: {mem_count}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: parse_dump.py <minidump_file>")
        sys.exit(1)
    parse_minidump(sys.argv[1])
