#!/usr/bin/env python3
"""
p800_width_test.py - print a calibration page to find the P800's real row width.

Usage:
    sudo cupsdisable P800
    python3 p800_width_test.py 216            # try 216 bytes/row (1728 dots)
    python3 p800_width_test.py 208            # then other candidates: 208, 210, 224 ...
    python3 p800_width_test.py 216 /dev/usb/lp0

The page (all sizes assume 203 dpi, i.e. 8 dots/mm, 1 byte = 8 dots = 1 mm):
  1. solid bar, 8 rows        -> shows how much of each row actually prints
  2. blank gap
  3. tick marks every 16 bytes (16 mm), long tick every 64 bytes (64 mm)
  4. blank gap
  5. 64 rows with a line at the first byte, the middle byte and the last byte
     (a slanted/sheared line means the row width you sent is wider than the head)
"""
import os
import sys

W = int(sys.argv[1]) if len(sys.argv) > 1 else 216
DEV = sys.argv[2] if len(sys.argv) > 2 else "/dev/usb/lp0"

rows = []
rows += [b"\xff" * W] * 8
rows += [bytes(W)] * 8
for _ in range(24):
    r = bytearray(W)
    for x in range(0, W, 16):
        r[x] = 0xFF
        if x % 64 == 0 and x + 1 < W:
            r[x + 1] = 0xFF
    rows.append(bytes(r))
rows += [bytes(W)] * 8
for _ in range(64):
    r = bytearray(W)
    r[0] = 0xFF
    r[W // 2] = 0xFF
    r[-1] = 0xFF
    rows.append(bytes(r))

h = len(rows)
stream = (b"\x1b\x40"
          + b"\x1d\x76\x30\x00" + bytes([W & 0xFF, W >> 8, h & 0xFF, h >> 8])
          + b"".join(rows)
          + b"\x1b\x64\x06")

with open(DEV, "wb") as f:
    f.write(stream)
print(f"sent {len(stream)} bytes: {W} bytes/row ({W * 8} dots) x {h} rows to {DEV}")
