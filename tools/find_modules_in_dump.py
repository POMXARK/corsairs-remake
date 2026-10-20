"""Locate module names inside crash.dmp to find the real module list."""
p = r"C:\corsairs-remake\engine\build\default\Debug\crash.dmp"
with open(p, 'rb') as f:
    data = f.read()
print('file size:', len(data))

for enc, label in ((('utf-16-le'), 'utf16le'), (('ascii'), 'ascii')):
    needle = 'engine.exe'.encode(enc)
    idx = 0
    hits = []
    while True:
        i = data.find(needle, idx)
        if i < 0:
            break
        hits.append(i)
        idx = i + 1
    print(label, 'engine.exe hits:', ['0x%X' % h for h in hits[:30]], 'total', len(hits))

# Show context around first utf16le hit: look backwards for structure start
needle = 'engine.exe'.encode('utf-16-le')
i = data.find(needle)
if i >= 0:
    start = max(0, i - 256)
    chunk = data[start:i + 128]
    print('\ncontext around first utf16le hit (file offset 0x%X):' % i)
    for off in range(0, len(chunk), 16):
        b = chunk[off:off + 16]
        hexs = ' '.join('%02X' % x for x in b)
        asc = ''.join(chr(x) if 32 <= x < 127 else '.' for x in b)
        print('%06X  %-48s  %s' % (start + off, hexs, asc))
