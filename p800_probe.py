#!/usr/bin/env python3
"""
p800_probe.py - interactive protocol probe for a USB thermal printer on /dev/usb/lp0.

Usage:
    sudo cupsdisable P800            # stop CUPS from touching the device while testing
    python3 p800_probe.py            # run every probe, asking after each one
    python3 p800_probe.py /dev/usb/lp0 escpos_text tspl   # run only some probes
    sudo cupsenable P800             # when done

After each probe the script prints whatever the printer sent back (if anything)
and asks whether the printer reacted (motor, LED change, printed output).
Paste the final summary and the 'device info' block back for analysis.
"""
import os
import select
import sys
import time

DEV = "/dev/usb/lp0"
args = sys.argv[1:]
if args and args[0].startswith("/dev/"):
    DEV = args.pop(0)


# ---------------------------------------------------------------- probes ---
def raster_block(width_bytes=8, height=64):
    """Boxed test pattern, 1 = black. GS v 0 header: 1D 76 30 m xL xH yL yH."""
    rows = []
    for y in range(height):
        if y < 4 or y >= height - 4:
            rows.append(b"\xff" * width_bytes)
        else:
            rows.append(b"\xc0" + b"\x00" * (width_bytes - 2) + b"\x03")
    hdr = b"\x1d\x76\x30\x00" + bytes([width_bytes & 0xFF, width_bytes >> 8,
                                       height & 0xFF, height >> 8])
    return hdr + b"".join(rows)


PROBES = {
    # --- query-only probes: safe, never move paper. Look for a reply. ---
    "escpos_status": b"\x10\x04\x01",                       # DLE EOT 1 realtime status
    "escpos_id": b"\x1d\x49\x42\x1d\x49\x43\x1d\x49\x41",   # GS I: maker, model, firmware
    # --- print probes ---
    "escpos_text": b"\x1b\x40P800 ESCPOS TEST\n\n\n\n\x1b\x64\x04",
    "escpos_text_ff": b"\x1b\x40P800 ESCPOS FF TEST\r\n\x0c",
    "escpos_raster": b"\x1b\x40" + raster_block() + b"\x1b\x64\x04",
    "tspl": (b"SIZE 210 mm,297 mm\r\nGAP 0,0\r\nCLS\r\n"
             b'TEXT 50,50,"3",0,1,1,"P800 TSPL"\r\nPRINT 1,1\r\n'),
    "cpcl": (b"! 0 200 200 400 1\r\nTEXT 4 0 30 40 P800 CPCL\r\n"
             b"FORM\r\nPRINT\r\n"),
    "zpl": b"^XA^FO50,50^A0N,50,50^FDP800 ZPL^FS^XZ",
    "pcl": b"\x1bE P800 PCL TEST\r\n\x0c",
}


# --------------------------------------------------------------- helpers ---
def read_sysfs(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def device_info():
    print("=== device info ===")
    base = "/sys/class/usbmisc/" + os.path.basename(DEV) + "/device"
    print("ieee1284_id :", read_sysfs(base + "/ieee1284_id"))
    for key in ("idVendor", "idProduct", "manufacturer", "product", "serial"):
        print(f"{key:12}:", read_sysfs(base + "/../" + key))
    print("(also run: lsusb -v -d VID:PID  and  dmesg | tail -30)\n")


def hexdump(b):
    return " ".join(f"{x:02x}" for x in b) + "   |" + \
        "".join(chr(x) if 32 <= x < 127 else "." for x in b) + "|"


def send(fd, data, chunk=512):
    for i in range(0, len(data), chunk):
        part = data[i:i + chunk]
        while part:
            try:
                n = os.write(fd, part)
                part = part[n:]
            except BlockingIOError:
                select.select([], [fd], [], 1.0)


def read_reply(fd, wait=1.5):
    out = b""
    end = time.time() + wait
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if not r:
            continue
        try:
            chunk = os.read(fd, 256)
        except (BlockingIOError, OSError):
            continue
        if not chunk:
            break
        out += chunk
    return out


# ------------------------------------------------------------------ main ---
def main():
    names = args or list(PROBES)
    unknown = [n for n in names if n not in PROBES]
    if unknown:
        sys.exit(f"unknown probe(s): {unknown}; available: {list(PROBES)}")

    device_info()
    try:
        fd = os.open(DEV, os.O_RDWR | os.O_NONBLOCK)
    except OSError as e:
        sys.exit(f"cannot open {DEV}: {e} (is CUPS holding it? are you in group lp?)")

    results = {}
    for name in names:
        data = PROBES[name]
        print(f"--- {name}: sending {len(data)} bytes")
        read_reply(fd, 0.2)            # drain stale input
        send(fd, data)
        reply = read_reply(fd)
        print("    reply:", hexdump(reply) if reply else "(none)")
        ans = input("    did the printer react (motor/LED/print)? [y/N/q] ").strip().lower()
        results[name] = ("REACTED" if ans == "y" else "no reaction") + \
                        (f", reply={reply.hex()}" if reply else "")
        if ans == "q":
            break
        time.sleep(1.0)
    os.close(fd)

    print("\n=== summary ===")
    for k, v in results.items():
        print(f"{k:16} {v}")


if __name__ == "__main__":
    main()
