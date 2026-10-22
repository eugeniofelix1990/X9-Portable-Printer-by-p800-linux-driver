#!/usr/bin/env python3
"""
p800print.py - print an image on the P800 using ESC/POS GS v 0 raster.

    pip install pillow            (or: sudo apt install python3-pil)
    python3 p800print.py clip.png
    python3 p800print.py table.png --width-bytes 208 --feed 8
    python3 p800print.py clip.png -o job.bin      # write the byte stream to a file instead

Stream layout:  ESC @  |  { GS v 0 m xL xH yL yH <rows> } per band  |  ESC d n
The image is scaled to the full row width (WIDTH_BYTES * 8 dots), converted to
1 bit (1 = black) and sent in bands so the firmware buffer is never overrun.
Set --width-bytes from the result of p800_width_test.py.
"""
import argparse
import sys
import time

from PIL import Image

INVERT = bytes(255 - i for i in range(256))   # Pillow '1': 0=black; printer: 1=black


def load_gray(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    return im.convert("L")


def prepare(im, width_bytes, rotate, scale, align, threshold, dither):
    width_px = width_bytes * 8
    if rotate:
        im = im.rotate(-rotate, expand=True, fillcolor=255)
    if scale:
        new_h = max(1, round(im.height * width_px / im.width))
        im = im.resize((width_px, new_h), Image.LANCZOS)
    elif im.width > width_px:
        im = im.crop((0, 0, width_px, im.height))
    if im.width < width_px:
        canvas = Image.new("L", (width_px, im.height), 255)
        x = 0 if align == "left" else (width_px - im.width) // 2
        canvas.paste(im, (x, 0))
        im = canvas
    if dither:
        bw = im.convert("1")                       # Floyd-Steinberg
    else:
        bw = im.point(lambda p: 255 if p > threshold else 0).convert("1", dither=Image.NONE)
    return bw


def build_stream(bw, width_bytes, band, feed):
    raw = bw.tobytes().translate(INVERT)           # packed MSB-first, 1 = black
    assert len(raw) == width_bytes * bw.height
    out = bytearray(b"\x1b\x40")
    for y in range(0, bw.height, band):
        rows = min(band, bw.height - y)
        chunk = raw[y * width_bytes:(y + rows) * width_bytes]
        out += b"\x1d\x76\x30\x00"
        out += bytes([width_bytes & 0xFF, width_bytes >> 8, rows & 0xFF, rows >> 8])
        out += chunk
    out += b"\x1b\x64" + bytes([feed])
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--dev", default="/dev/usb/lp0")
    ap.add_argument("-o", "--output", help="write stream to this file instead of the device")
    ap.add_argument("--width-bytes", type=int, default=216,
                    help="bytes per row (8 dots each); calibrate with p800_width_test.py")
    ap.add_argument("--band", type=int, default=128, help="rows per GS v 0 block")
    ap.add_argument("--feed", type=int, default=6, help="lines to feed at the end (ESC d n)")
    ap.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0)
    ap.add_argument("--no-scale", action="store_true", help="don't scale to full width")
    ap.add_argument("--align", choices=("left", "center"), default="left")
    ap.add_argument("--threshold", type=int, default=160, help="used with --no-dither")
    ap.add_argument("--no-dither", action="store_true", help="hard threshold instead of dithering")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to pause between bands")
    a = ap.parse_args()

    im = load_gray(a.image)
    bw = prepare(im, a.width_bytes, a.rotate, not a.no_scale, a.align,
                 a.threshold, not a.no_dither)
    stream = build_stream(bw, a.width_bytes, a.band, a.feed)

    if a.output:
        with open(a.output, "wb") as f:
            f.write(stream)
        print(f"wrote {len(stream)} bytes to {a.output} ({bw.width}x{bw.height} dots)")
        return
    with open(a.dev, "wb") as f:
        step = a.band * a.width_bytes + 8
        head = b"\x1b\x40"
        f.write(head)
        body = stream[len(head):-3]
        for i in range(0, len(body), step):
            f.write(body[i:i + step])
            f.flush()
            if a.delay:
                time.sleep(a.delay)
        f.write(stream[-3:])
    print(f"printed {bw.width}x{bw.height} dots ({len(stream)} bytes) to {a.dev}")


if __name__ == "__main__":
    sys.exit(main())
