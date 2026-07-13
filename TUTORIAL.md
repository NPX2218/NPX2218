# How this profile works

The README is a single generated image, `dark_mode.svg`. Two pipelines build it,
and they meet in `render.py`.

```
photo.jpg -> asciify.py -> ascii-art.txt -> downsample.py -> portrait.txt --+
                                                                            +-> render.py -> dark_mode.svg
GitHub API -> today.py -> cache/ -> build_readme.py -> stats ---------------+
```

## The portrait

Run these by hand when the photo changes.

1. `asciify.py` turns `photo.jpg` into a full-size ASCII grid, `ascii-art.txt`.
   It grayscales the photo, stretches the contrast, and maps brightness to
   characters, so bright areas become dense glyphs and dark areas stay blank.
   (The art first came from asciiart.eu, but that version was too low-contrast
   to shrink cleanly, so `asciify.py` does the conversion directly.)
2. `downsample.py` shrinks `ascii-art.txt` to header size, `portrait.txt`, by
   averaging each block of characters into one. `render.py` embeds this file.
3. `preview.py` optionally renders an ASCII file to a PNG so you can compare
   versions while tuning.

## The stats

The GitHub Action runs these on a schedule.

1. `today.py` runs the GitHub GraphQL queries for repos, stars, commits, and
   lines of code. Counting lines of code is slow, so it caches each repo's count
   in `cache/` and only re-reads repos whose commit count changed. The queries
   were adapted from Andrew6rant's profile.
2. `build_readme.py` is the entry point. It collects the stats from `today.py`,
   reads the view count from the komarev badge, formats everything, and passes
   it to `render.py`.

## render.py

`render.py` does the layout and hits no network. It takes the stats, embeds
`portrait.txt`, and writes `dark_mode.svg`.

## Running it

```bash
# Rebuild the portrait after changing photo.jpg
python asciify.py --cols 200      # writes ascii-art.txt
python downsample.py 68           # writes portrait.txt

# Preview the layout with placeholder stats (no API needed)
python render.py                  # writes dark_mode.svg

# Full build with live stats (needs a GitHub token)
ACCESS_TOKEN=<pat> USER_NAME=NPX2218 python build_readme.py
```
