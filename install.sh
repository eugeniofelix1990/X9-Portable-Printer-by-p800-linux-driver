#!/bin/sh
# Build and install the rastertop800 filter + P800 queue on Debian/Ubuntu/Mint.
set -e
cd "$(dirname "$0")"

sudo apt-get install -y build-essential libcups2-dev cups-client
gcc -O2 -Wall -o rastertop800 rastertop800.c $(cups-config --cflags --libs)
sudo install -o root -g root -m 0755 rastertop800 /usr/lib/cups/filter/rastertop800
cupstestppd -W translations p800.ppd

# The CUPS usb backend needs a real URI such as usb://BY/P800?serial=...
URI=$(lpinfo -v | awk '$2 ~ /^usb:\/\/BY\/P800/ {print $2; exit}')
if [ -z "$URI" ]; then
  echo "lpinfo -v does not list the P800 - plug it in / check 'dmesg | tail' and retry." >&2
  exit 1
fi
echo "Using device URI: $URI"

cancel -a P800 2>/dev/null || true
sudo lpadmin -p P800 -E -v "$URI" -P p800.ppd -o printer-is-shared=false
lpstat -p P800
echo "Test:  lp -d P800 -o fit-to-page some_image.png"
