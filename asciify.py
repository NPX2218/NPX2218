#!/usr/bin/env python3
"""Convert ``photo.jpg`` to a high-contrast, aspect-correct ``ascii-art.txt``.

This replaces the low-contrast, full-frame output a web converter produced (every
cell a mid-tone glyph, no blank background -> downsamples to gray mush). Here we
control the tone curve ourselves: grayscale -> autocontrast -> optional black
floor + gamma -> map luminance to a density ramp, with the row count corrected
for the monospace cell aspect so the render isn't squished.

Polarity is light-on-dark to match the header: BRIGHT photo areas become DENSE
glyphs ("@") that glow; DARK areas become blank space (the background drops out).

    python asciify.py --cols 200 --clip 2 --floor 0 --gamma 1.0 \
        --crop-top 0 --crop-bottom 1 --crop-left 0 --crop-right 1

Writes ``ascii-art.txt``; feed it to ``downsample.py`` to make ``portrait.txt``.
"""
from __future__ import annotations

import argparse

from PIL import Image, ImageOps

# Pillow >=9.1 moved resampling filters onto Image.Resampling; fall back for old.
LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

# Density ramp, blank -> densest. Index grows with pixel brightness, so a bright
# pixel picks "@" (which downsample.py also reads as densest) and a dark pixel
# picks " ". Kept consistent with downsample.py's density ordering.
RAMP = " .:-=+*#%@"

# On-screen monospace cell aspect (width/height). render.py draws the portrait at
# CW*PSTRETCH = 8.4-scaled... actually PFS=5 -> ~3.45px advance, PLH=5.6px line
# height -> 3.45/5.6 = 0.616. Sampling rows in this ratio keeps faces round, not
# stretched. Overridable because downsample.py preserves whatever grid we bake.
CELL_ASPECT = 0.616


def build(args: argparse.Namespace) -> str:
    im = Image.open(args.src).convert("L")           # grayscale (luma-weighted)

    # Stretch the tonal range to full black..white, clipping a few % of outliers
    # at each end. Done on the FULL frame BEFORE cropping so the normalization
    # anchors to the whole photo's brightest/darkest points — cropping first
    # would re-stretch the darker remainder and flood the background with glyphs.
    im = ImageOps.autocontrast(im, cutoff=args.clip)

    # Crop (fractions of the frame) to frame the subject(s).
    W, H = im.size
    box = (int(args.crop_left * W), int(args.crop_top * H),
           int(args.crop_right * W), int(args.crop_bottom * H))
    im = im.crop(box)
    W, H = im.size

    # Output grid. rows corrected for cell aspect so the portrait isn't squished.
    cols = args.cols
    rows = max(1, round(cols * (H / W) * CELL_ASPECT))
    im = im.resize((cols, rows), LANCZOS)

    # Image.load() is typed as `PixelAccess | None` (None only if Pillow fails to
    # decode). Assert it away so px[x, y] below is provably indexable — and so a
    # real decode failure surfaces here instead of as a confusing None index.
    px = im.load()
    assert px is not None
    span = max(1, 255 - args.floor)
    out_rows = []
    for y in range(rows):
        line = []
        for x in range(cols):
            v = px[x, y]
            if v <= args.floor:                       # black floor -> blank bg
                line.append(" ")
                continue
            t = (v - args.floor) / span               # 0..1 above the floor
            if args.invert:                            # dark photo -> dense glyph
                t = 1 - t
            t = t ** args.gamma                        # >1 darkens mids, <1 lifts
            line.append(RAMP[min(len(RAMP) - 1, int(t * len(RAMP)))])
        out_rows.append("".join(line).rstrip())
    return "\n".join(out_rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", default="photo.jpg")
    p.add_argument("--out", default="ascii-art.txt")
    p.add_argument("--cols", type=int, default=200, help="output width in chars")
    p.add_argument("--clip", type=float, default=2.0, help="autocontrast %% cutoff")
    p.add_argument("--floor", type=int, default=0, help="luma <= this -> blank")
    p.add_argument("--gamma", type=float, default=1.0, help=">1 darkens mids")
    p.add_argument("--invert", action="store_true", help="dark photo -> dense glyph")
    p.add_argument("--crop-top", type=float, default=0.0)
    p.add_argument("--crop-bottom", type=float, default=1.0)
    p.add_argument("--crop-left", type=float, default=0.0)
    p.add_argument("--crop-right", type=float, default=1.0)
    args = p.parse_args()

    art = build(args)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(art)
    lines = art.split("\n")
    print(f"# wrote {args.out}: {max(len(l) for l in lines)}x{len(lines)}")


if __name__ == "__main__":
    main()
