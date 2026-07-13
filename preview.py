#!/usr/bin/env python3
"""Render ASCII text file(s) to a PNG the way the SVG header shows them:
light glyphs on a dark field, at the render's cell aspect. Lets us eyeball
candidates instead of squinting at wrapped terminal text.

    python preview.py out.png LABEL1 file1.txt LABEL2 file2.txt ...
"""
from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFont

ADV, LH, FS = 7.0, 11.4, 13          # cell advance/line-height/font (ratio ~0.61)
BG, FG = (13, 17, 23), (220, 224, 210)
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", FS)
LABEL_FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
PAD, GAP = 24, 40


def panel(path: str) -> Image.Image:
    lines = open(path, encoding="utf-8").read().split("\n")
    cols = max(len(l) for l in lines)
    w, h = int(cols * ADV) + 2 * PAD, int(len(lines) * LH) + 2 * PAD
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    for r, line in enumerate(lines):
        for c, ch in enumerate(line):
            if ch != " ":
                d.text((PAD + c * ADV, PAD + r * LH), ch, font=FONT, fill=FG)
    return img


def main() -> None:
    out = sys.argv[1]
    pairs = list(zip(sys.argv[2::2], sys.argv[3::2]))
    panels = [(lbl, panel(f)) for lbl, f in pairs]
    W = sum(p.width for _, p in panels) + GAP * (len(panels) + 1)
    H = max(p.height for _, p in panels) + 60
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(canvas)
    x = GAP
    for lbl, p in panels:
        d.text((x, 12), lbl, font=LABEL_FONT, fill=(255, 210, 120))
        canvas.paste(p, (x, 44))
        x += p.width + GAP
    canvas.save(out)
    print(f"# {out}: {W}x{H}, {len(panels)} panels")


if __name__ == "__main__":
    main()
