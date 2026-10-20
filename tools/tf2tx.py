#!/usr/bin/env python3
"""Convert Sea Dogs .tf texture files to engine .tx format (TXF_A8R8G8B8)."""
import os
import sys
import struct
import argparse


def decode_rgb565(data_16bit):
    """Decode 16-bit RGB565 pixel data to RGBA8 (B,G,R,A order for D3D9)."""
    out = bytearray()
    for i in range(0, len(data_16bit), 2):
        v = data_16bit[i] | (data_16bit[i + 1] << 8)
        r5 = (v >> 11) & 0x1F
        g6 = (v >> 5) & 0x3F
        b5 = v & 0x1F
        r8 = (r5 << 3) | (r5 >> 2)
        g8 = (g6 << 2) | (g6 >> 4)
        b8 = (b5 << 3) | (b5 >> 2)
        out += bytes([b8, g8, r8, 255])
    return bytes(out)


def decode_rgba5551(data_16bit):
    """Decode 16-bit RGBA5551 pixel data to RGBA8 (B,G,R,A order for D3D9)."""
    out = bytearray()
    for i in range(0, len(data_16bit), 2):
        v = data_16bit[i] | (data_16bit[i + 1] << 8)
        r5 = (v >> 11) & 0x1F
        g5 = (v >> 6) & 0x1F
        b5 = (v >> 1) & 0x1F
        a1 = v & 1
        r8 = (r5 << 3) | (r5 >> 2)
        g8 = (g5 << 3) | (g5 >> 2)
        b8 = (b5 << 3) | (b5 >> 2)
        a8 = 255 if a1 else 0
        out += bytes([b8, g8, r8, a8])
    return bytes(out)


def decode_palette_indexed(indices, palette):
    """Decode 8-bit palette indices to RGBA8 (B,G,R,A order for D3D9)."""
    out = bytearray()
    for idx in indices:
        r, g, b, a = palette[idx]
        out += bytes([b, g, r, a])
    return bytes(out)


def convert_tf_to_tx(tf_path, tx_path):
    """Convert a single .tf file to .tx format. Returns (ok, error_msg)."""
    with open(tf_path, 'rb') as f:
        data = f.read()

    # Parse header (16 bytes)
    if len(data) < 16:
        return False, "file too small"

    type_ = data[5]
    mm_count = data[6]
    pal_count = data[7]
    width, height = struct.unpack_from('<II', data, 8)

    if width == 0 or height == 0:
        return False, f"zero dimensions {width}x{height}"
    if width > 4096 or height > 4096:
        return False, f"dimensions too large {width}x{height}"

    offset = 16
    mips_rgba8 = []

    # Read 16-bit mip images (mmCount of them, halving dimensions each)
    w, h = width, height
    for mip_idx in range(mm_count):
        if w == 0 or h == 0:
            break
        size = w * h * 2
        if offset + size > len(data):
            return False, f"mip {mip_idx} (16-bit) overflows file"
        raw = data[offset:offset + size]
        offset += size

        if type_ == 1:
            rgba8 = decode_rgba5551(raw)
        else:
            rgba8 = decode_rgb565(raw)
        mips_rgba8.append(rgba8)

        w //= 2
        h //= 2

    # Read palette: 256 entries * 4 bytes (R, G, B, pad)
    palette = None
    if pal_count > 0:
        if offset + 1024 > len(data):
            return False, "palette overflows file"
        palette = []
        for i in range(256):
            r = data[offset + i * 4]
            g = data[offset + i * 4 + 1]
            b = data[offset + i * 4 + 2]
            # 4th byte is pad, alpha always 255 (per Noesis reference)
            palette.append((r, g, b, 255))
        offset += 1024

    # Read palette-indexed mips (palCount of them)
    pal_mips_rgba8 = []
    w, h = width, height
    for mip_idx in range(pal_count):
        if w == 0 or h == 0:
            break
        size = w * h
        if offset + size > len(data):
            return False, f"mip {mip_idx} (palette) overflows file"
        indices = data[offset:offset + size]
        offset += size

        if palette is not None:
            rgba8 = decode_palette_indexed(indices, palette)
        else:
            rgba8 = bytes([0, 0, 0, 255] * size)
        pal_mips_rgba8.append(rgba8)

        w //= 2
        h //= 2

    # Decide which mips to use: prefer 16-bit, fall back to palette
    if mips_rgba8:
        all_mips = mips_rgba8
    elif pal_mips_rgba8:
        all_mips = pal_mips_rgba8
    else:
        return False, "no texture data found"

    # Write .tx file
    # TX_FILE_HEADER (24 bytes): flags, width, height, nmips, format, mip_size
    tx_format = 21  # TXF_A8R8G8B8
    mip0_size = width * height * 4

    header = struct.pack('<6i', 0, width, height, len(all_mips), tx_format, mip0_size)

    with open(tx_path, 'wb') as f:
        f.write(header)
        for mip_data in all_mips:
            f.write(mip_data)

    return True, None


def batch_convert(src_dir, dst_dir=None, verbose=True):
    """Convert all .tf files in src_dir to .tx. Returns (ok_count, fail_count)."""
    if dst_dir is None:
        dst_dir = src_dir

    ok_count = 0
    fail_count = 0

    tf_files = []
    for root, dirs, files in os.walk(src_dir):
        for fname in files:
            if fname.lower().endswith('.tf'):
                tf_files.append(os.path.join(root, fname))

    if verbose:
        print(f"Found {len(tf_files)} .tf files")

    for tf_path in sorted(tf_files):
        rel = os.path.relpath(tf_path, src_dir)
        tx_rel = os.path.splitext(rel)[0] + '.tx'
        tx_path = os.path.join(dst_dir, tx_rel)

        out_dir = os.path.dirname(tx_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        ok, err = convert_tf_to_tx(tf_path, tx_path)
        if ok:
            ok_count += 1
        else:
            fail_count += 1
            if verbose:
                print(f"  FAIL: {rel}: {err}")

    if verbose:
        print(f"Done: {ok_count} converted, {fail_count} failed")

    return ok_count, fail_count


def main():
    parser = argparse.ArgumentParser(description="Convert .tf to .tx texture format")
    parser.add_argument('input', help="Input .tf file or directory")
    parser.add_argument('output', nargs='?', help="Output .tx file or directory")
    parser.add_argument('-q', '--quiet', action='store_true', help="Quiet mode")

    args = parser.parse_args()

    if os.path.isfile(args.input):
        if not args.output:
            print("Error: output required for single file conversion")
            sys.exit(1)
        ok, err = convert_tf_to_tx(args.input, args.output)
        if not ok:
            print(f"Error: {err}")
            sys.exit(1)
        if not args.quiet:
            print(f"Converted: {args.input} -> {args.output}")
    elif os.path.isdir(args.input):
        dst = args.output
        batch_convert(args.input, dst, verbose=not args.quiet)
    else:
        print(f"Error: '{args.input}' not found")
        sys.exit(1)


if __name__ == '__main__':
    main()
