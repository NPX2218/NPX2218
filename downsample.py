#!/usr/bin/env python3
"""Downsample the full-res ASCII portrait to header size, rendered light-on-dark.

Usage:  python downsample.py [WIDTH] [invert]
    WIDTH   output width in characters (default 68). Smaller source blocks =>
            more detail; height scales with it to keep the aspect ratio.
    invert  flip bright<->dark (subject on a light field instead of dark).

Reads ``ascii-art.txt`` (next to this file) and writes ``portrait.txt``, which
``render.py`` embeds in the header. It works on ASCII, not the raw photo: the
photo is already characters, so each glyph already encodes a brightness.
"""
from __future__ import annotations

import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ascii-art.txt")
TARGET_W = int(sys.argv[1]) if len(sys.argv) > 1 else 68   # output width (chars)
INVERT = len(sys.argv) > 2 and sys.argv[2] == "invert"     # flip light/dark

# Read the source grid and pad every line to equal width (a clean rectangle).
lines = [l.rstrip("\n") for l in open(SRC, encoding="utf-8")]
W = max(len(l) for l in lines)
lines = [l.ljust(W) for l in lines]
H = len(lines)

# Input ramp: characters ordered darkest -> lightest, so density() maps a char
# to how much ink it carries (1.0 = densest glyph, 0.0 = blank space).
ramp = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
n = len(ramp)
dens = {ch: 1.0 - i / (n - 1) for i, ch in enumerate(ramp)}


def density(ch: str) -> float:
    """How much ink a character carries (1.0 densest, 0.0 blank; unknown -> 0.5)."""
    return dens.get(ch, 0.5)


bx = W / TARGET_W          # source chars per output char (block size)
TH = int(H / bx)           # output height, scaled by the same factor (keeps aspect)
out_ramp = " .:-=+*#%@"    # output palette, dark -> light


def out_char(d: float) -> str:
    """Pick the output character for an average block density ``d`` (0..1)."""
    if INVERT:
        d = 1 - d
    return out_ramp[min(len(out_ramp) - 1, int(d * len(out_ramp)))]


# For each output cell, average the ink of the source block it covers and paint
# one character for it.
rows: list[str] = []
for oy in range(TH):                       # output rows (top -> bottom)
    row: list[str] = []
    for ox in range(TARGET_W):             # output columns (left -> right)
        x0, x1 = int(ox * bx), int((ox + 1) * bx)
        y0, y1 = int(oy * bx), int((oy + 1) * bx)
        tot = 0.0
        cnt = 0
        for yy in range(y0, min(y1, H)):
            for xx in range(x0, min(x1, W)):
                tot += density(lines[yy][xx])
                cnt += 1
        row.append(out_char(tot / cnt if cnt else 0.0))
    rows.append("".join(row).rstrip())

# Crop fully-blank rows off the top and bottom so the portrait sits tight.
while rows and not rows[0].strip():
    rows.pop(0)
while rows and not rows[-1].strip():
    rows.pop()

portrait = "\n".join(rows)
with open("portrait.txt", "w", encoding="utf-8") as f:
    f.write(portrait)
print(f"# {TARGET_W}x{len(rows)}")
print(portrait)
