"""Build assets/caissa.ico (and the small UI mark) from assets/caissa.png.

Pure standard library: decodes the PNG with zlib, box-filters it down to each icon
size, and packs the results into a Vista-style .ico whose entries are PNGs.

    py tools/make_icon.py
"""

import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "assets", "caissa.png")
ICON = os.path.join(ROOT, "assets", "caissa.ico")
MARK = os.path.join(ROOT, "assets", "caissa-128.png")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def read_png(path):
    """-> (width, height, rows) with rows as RGBA bytearrays."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG: " + path)

    pos, idat, width, height, depth, ctype = 8, bytearray(), 0, 0, 8, 6
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
            interlace = body[12]
            if interlace:
                raise SystemExit("interlaced PNGs are not supported")
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length

    if depth != 8 or ctype not in (2, 6):
        raise SystemExit("need an 8-bit RGB or RGBA PNG (got depth %d type %d)" % (depth, ctype))

    channels = 4 if ctype == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows, previous = [], bytearray(stride)

    for y in range(height):
        start = y * (stride + 1)
        filter_type = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = previous[x]
            c = previous[x - channels] if x >= channels else 0
            if filter_type == 1:
                line[x] = (line[x] + a) & 0xFF
            elif filter_type == 2:
                line[x] = (line[x] + b) & 0xFF
            elif filter_type == 3:
                line[x] = (line[x] + (a + b) // 2) & 0xFF
            elif filter_type == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 0xFF
        previous = line
        if channels == 3:                       # promote to RGBA
            rgba = bytearray(width * 4)
            for x in range(width):
                rgba[x * 4:x * 4 + 3] = line[x * 3:x * 3 + 3]
                rgba[x * 4 + 3] = 255
            rows.append(rgba)
        else:
            rows.append(line)
    return width, height, rows


def resize(width, height, rows, size):
    """Box filter down to size×size, averaging over the source block."""
    out = []
    for y in range(size):
        y0, y1 = y * height // size, max(y * height // size + 1, (y + 1) * height // size)
        line = bytearray(size * 4)
        for x in range(size):
            x0, x1 = x * width // size, max(x * width // size + 1, (x + 1) * width // size)
            r = g = b = a = n = 0
            for sy in range(y0, y1):
                row = rows[sy]
                for sx in range(x0, x1):
                    i = sx * 4
                    alpha = row[i + 3]
                    r += row[i] * alpha
                    g += row[i + 1] * alpha
                    b += row[i + 2] * alpha
                    a += alpha
                    n += 1
            if a:                               # weight color by alpha so edges stay clean
                line[x * 4:x * 4 + 4] = bytes((r // a, g // a, b // a, a // n))
            else:
                line[x * 4:x * 4 + 4] = b"\x00\x00\x00\x00"
        out.append(line)
    return out


def write_png(rows, size):
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body +
                struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    raw = bytearray()
    for row in rows:
        raw.append(0)                           # filter: none
        raw += row
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main():
    if not os.path.exists(SOURCE):
        raise SystemExit("missing " + SOURCE)
    width, height, rows = read_png(SOURCE)
    print("source: %dx%d" % (width, height))

    images = []
    for size in SIZES:
        scaled = resize(width, height, rows, size)
        images.append((size, write_png(scaled, size)))
        print("  rendered %dx%d (%d bytes)" % (size, size, len(images[-1][1])))
        if size == 128:
            with open(MARK, "wb") as handle:
                handle.write(images[-1][1])

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        entries += struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
                               0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)

    with open(ICON, "wb") as handle:
        handle.write(header + entries + blobs)
    print("wrote %s (%.0f KB) and %s" % (ICON, os.path.getsize(ICON) / 1024, MARK))


if __name__ == "__main__":
    sys.exit(main())
