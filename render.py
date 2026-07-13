#!/usr/bin/env python3
"""Generate ``dark_mode.svg``, a neofetch-style terminal profile for myself.

The file is one self-contained SVG: an ASCII portrait, a neofetch-style info
column, and ``cat``-style sections for what I'm building, my projects, and my
work history (each company drawn with its real logo).

Edit the CONTENT block to change text; call :func:`build` with a stats mapping
to produce the SVG. Running this module directly renders it with placeholder
stats so you can preview the layout without hitting the GitHub API.
"""
from __future__ import annotations

import base64
import datetime
import os
from typing import Optional, TypedDict

# Editable content

BIRTHDAY = datetime.date(2007, 8, 12)


def load_portrait() -> list[str]:
    """Return the ASCII portrait as a list of lines.

    Reads ``portrait.txt`` next to this file (regenerate it from a photo with
    ``downsample.py``). Falls back to a placeholder line if the file is absent.
    """
    path = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "portrait.txt")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().rstrip("\n").split("\n")
    except FileNotFoundError:
        return ["(portrait.txt missing)"]


# Info rows: (label, value). A value of None on "Uptime" is replaced with the
# live age; a None entry is a blank spacer line.
SYSTEM: list[Optional[tuple[str, Optional[str]]]] = [
    ("OS", "macOS, Android, Linux"),
    ("Uptime", None),                       # filled with live age
    ("Host", "Northeastern University"),
    ("Kernel", "CS + Math"),
    ("Editor", "VS Code, Neovim"),
    None,
    ("Languages.Programming", "TypeScript, Python, C++, Java"),
    ("Languages.Web", "React, Next.js, Three.js, Node"),
    ("Languages.Spoken", "English, Hindi, Spanish"),
    None,
    ("Hobbies", "Gym, Music, Drawing, Writing, Solving Rubiks Cubes"),
    ("Interests", "Aerospace, Astronomy, ML Research"),
]

CONTACT: list[tuple[str, str]] = [
    ("Email.Personal", "neelbansalx@gmail.com"),
    ("Email.School", "bansal.neel@northeastern.edu"),
    ("LinkedIn", "neel-bansal"),
    ("GitHub", "NPX2218"),
]

NOW: list[str] = [
    "building the future of notetaking @ kov",
    "reclaiming people's peace from phone calls @ osmo",
    "writing two books, ranging from mathematics to an introductory piece on Python",
]

PROJECTS: list[dict[str, str]] = [
    {
        "title": "SEISMIC ML PIPELINE",
        "desc": "earthquake-precursor detection, Northeastern x UAF",
        "body": r"""Raw miniSEED --> Sliding Windows --> Bandpass Filtering --> Features
     |                                    |                   |
     |            +-----------------------+-------------------+
     |            |                       |                   |
     |        HF1 (5-25 Hz)        HF2 (0.1-5 Hz)        LF (drift)
     |            |                       |                   |
     |            +-----------------------+-------------------+
     |                                    |
     |                            Histogram Analysis
     |                                    |
     |                          +---------+---------+
     |                    Centroid (ym)       Spread (S)
     |
     +--> USGS Catalog --> Labels --> Feature Matrix for ML""",
        "stack": "Python · ObsPy · NumPy · SciPy · TensorFlow",
    },
    {
        "title": "LEETION",
        "desc": "save LeetCode problems and solutions directly to your Notion database.",
        "body": r"""
    - 150k+ impressions & 1.4k+ installs
    - Auto-extracts problem details and code from LeetCode.
    - Built-in spaced repetition to schedule reviews and notification system to remind you.
    - Save multiple languages to the same problem entry.
    - Drawing canvas to sketch trees, graphs, and diagrams.
""",
        "stack": "HTML · CSS · JS",
    },
    {
        "title": "REPONODB",
        "desc": "git meets SQL in ~2000 lines of readable C++",
        "body": """  repono> INSERT INTO users VALUES (1, 'Neel', 18);
  repono> COMMIT 'added neel';
  repono> SELECT * FROM users AT COMMIT a3f2b7c;
  repono> MERGE feature INTO main;""",
        "stack": "C++ · Content-Addressed Storage · Append-Only Log",
    },
]

# (company, role, dates) — most recent first. A company may appear twice.
WORK: list[tuple[str, str, str]] = [
    ("Northeastern", "Teaching Assistant", "Sep 2026 - Present"),
    ("OsmO", "Full-Stack SWE Intern", "May 2026 - Present"),
    ("AWS", "AI & ML Scholar", "Feb 2026 - Present"),
    ("kov", "Co-Founder", "Jan 2026 - Present"),
    ("Leetion", "Creator", "Dec 2025 - Present"),
    ("Datacurve · YC W24", "SWE Contributor", "Mar - Apr 2026"),
    ("Northeastern", "Undergraduate Researcher", "Oct 2025 - Feb 2026"),
    ("Kindlegs", "Software Engineer Intern", "Jul - Sep 2025"),
    ("Arkaa", "Frontend SWE Intern", "Jun - Sep 2025"),
    ("SaudiStockDigest", "Co-Founder", "Mar - Nov 2024"),
    ("Sunshine Boulevard", "SWE Intern", "2023"),
]
WORK_NOTE = "# -> full detail at linkedin.com/in/neel-bansal"

# Company -> logo filename (logos/<slug>.png). A missing file falls back to an
# initial badge. Add/replace a company by dropping a PNG in logos/ and mapping it here.
LOGOS: dict[str, str] = {
    "OsmO":               "osmo",
    "AWS":                "aws",
    "kov":                "kov",
    "Leetion":            "leetion",
    "Datacurve · YC W24": "datacurve",
    "Northeastern":       "northeastern",
    "Kindlegs":           "kindlegs",
    "Arkaa":              "arkaa",
    "SaudiStockDigest":   "saudistockdigest",
    "Sunshine Boulevard": "sunshine",
}


class Stats(TypedDict):
    """The stat strings :func:`build` injects (already comma-formatted)."""
    repos: str
    contrib: str
    stars: str
    followers: str
    commits: str
    views: str
    loc: str
    loc_add: str
    loc_del: str
    today: datetime.date


# ============================ LAYOUT / STYLE ============================
W = 1090                # total canvas width
LH = 22                 # line height (info + body)
CW = 8.4                # monospace char advance at font-size 14
FS = 14                 # base font size
X0 = 28                 # left content margin
# Portrait font: sized so the full-res 220-col art fits left of INFO_X (480).
# 220 * (PFS*0.6*PSTRETCH) + X0 must stay < INFO_X, so PFS=2.9 -> ~2.0px/char ->
# ~440px wide + 28px margin = 468 < 480. Smaller font = denser = more detail;
# we use the full-res art directly (no downsample) because the extra resolution
# reads noticeably crisper at header scale. PLH keeps the ~0.62 cell aspect.
PFS = 2.9               # portrait font size (smaller = denser/more detail)
PLH = 3.3               # portrait line height
# portrait horizontal stretch (>1 = wider, <1 = narrower)
PSTRETCH = 1.05
INFO_X = 480            # neofetch info column x (right of the portrait)
RIGHT = W - 28          # right edge for values / rules
WORK_ROLE_X = X0 + 210
WORK_WHEN_X = X0 + 470

BG = "#0b0b0b"          # page background
BAR = "#121317"         # title bar
BARLINE = "#22252d"     # title bar underline
WHITE = "#ffffff"
VAL = "#f0f0f0"         # info values
DIM = "#8a8a8a"         # labels
MUT = "#6a6a6a"         # muted captions
FAINT = "#5a5a5a"       # prompt punctuation
BODY = "#cfcfcf"        # body text
RULE = "#343434"        # header rules
DOTS = "#3a3a3a"        # dotted leaders

# Accumulator that every emit helper appends SVG fragments to; build() joins it.
E: list[str] = []


def esc(s: str) -> str:
    """Escape the three XML-significant characters for safe SVG text."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def T(x: float, y: float, s: str, fill: str = VAL,
      weight: str = "400", anchor: str = "start") -> None:
    """Emit one ``<text>`` element at (x, y)."""
    E.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-weight="{weight}" '
             f'text-anchor="{anchor}" xml:space="preserve">{esc(s)}</text>')


def LN(x1: float, y1: float, x2: float, y2: float,
       stroke: str, dash: Optional[str] = None, wdt: float = 1) -> None:
    """Emit one ``<line>``; pass ``dash`` (e.g. "1.5,3.5") for a dotted stroke."""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    E.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
             f'stroke="{stroke}" stroke-width="{wdt}"{d}/>')


def prompt(x: float, y: float, cmd: str) -> None:
    """Emit a shell prompt line: ``neel@github ~ % <cmd>``."""
    E.append(
        f'<text x="{x}" y="{y:.1f}" xml:space="preserve">'
        f'<tspan fill="{DIM}">neel@github</tspan>'
        f'<tspan fill="{FAINT}"> ~ % </tspan>'
        f'<tspan fill="{WHITE}" font-weight="700">{esc(cmd)}</tspan></text>')


def age_string(today: datetime.date) -> str:
    """Return ``"X years, Y months, Z days"`` from BIRTHDAY up to ``today``."""
    y = today.year - BIRTHDAY.year
    m = today.month - BIRTHDAY.month
    d = today.day - BIRTHDAY.day
    if d < 0:
        m -= 1
        prev = (today.replace(day=1) - datetime.timedelta(days=1)).day
        d += prev
    if m < 0:
        y -= 1
        m += 12
    return f"{y} years, {m} months, {d} days"


def info_row(y: float, label: str, value: str,
             val_fill: str = VAL, val_weight: str = "600") -> None:
    """Emit a neofetch row: label at the left, value at the right, dotted leader between."""
    T(INFO_X, y, label, fill=DIM)
    T(RIGHT, y, value, fill=val_fill, weight=val_weight, anchor="end")
    # 7 is just a pixel buffer we have on both sides so that it isnt squished
    x1 = INFO_X + len(label) * CW + 7
    x2 = RIGHT - len(value) * CW - 7
    if x2 > x1:
        LN(x1, y - 4, x2, y - 4, DOTS, dash="1.5,3.5")


def section_head(y: float, label: str) -> None:
    """Emit a section header (e.g. ``— Contact``) with a rule to the right edge."""
    T(INFO_X, y, label, fill=DIM)
    LN(INFO_X + len(label) * CW + 9, y - 4, RIGHT, y - 4, "#2b2b2b")


LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos")
_logo_cache: dict[str, Optional[str]] = {}


def _logo_uri(slug: str) -> Optional[str]:
    """Return ``logos/<slug>.png`` as a base64 ``data:`` URI (cached), or None if absent."""
    if slug not in _logo_cache:
        path = os.path.join(LOGO_DIR, slug + ".png")
        if os.path.exists(path):
            with open(path, "rb") as f:
                _logo_cache[slug] = "data:image/png;base64," + \
                    base64.b64encode(f.read()).decode("ascii")
        else:
            _logo_cache[slug] = None
    return _logo_cache[slug]


def badge(x: float, ybase: float, label: str, s: int = 16) -> None:
    """Fallback company mark when a logo image is missing: rounded square + initial."""
    top = ybase - 13
    E.append(
        f'<rect x="{x:.1f}" y="{top:.1f}" width="{s}" height="{s}" rx="4.5" fill="#333"/>')
    E.append(f'<text x="{x + s / 2:.1f}" y="{top + s * 0.72:.1f}" fill="#fff" font-size="10.5" '
             f'font-weight="700" text-anchor="middle" '
             f'font-family="Helvetica,Arial,sans-serif">{esc(label)}</text>')


def draw_logo(x: float, ybase: float, company: str, s: int = 16) -> None:
    """Draw the company's logo (rounded, clipped) at (x, row baseline), or a badge fallback."""
    slug = LOGOS.get(company)
    uri = _logo_uri(slug) if slug else None
    if uri:
        top = ybase - 13
        # unique per row (a company can repeat)
        cid = f"logo_{slug}_{int(ybase)}"
        E.append(f'<clipPath id="{cid}"><rect x="{x:.1f}" y="{top:.1f}" '
                 f'width="{s}" height="{s}" rx="4.5"/></clipPath>')
        E.append(f'<image x="{x:.1f}" y="{top:.1f}" width="{s}" height="{s}" '
                 f'preserveAspectRatio="xMidYMid slice" clip-path="url(#{cid})" '
                 f'href="{uri}" xlink:href="{uri}"/>')
    else:
        badge(x, ybase, (company[:1] or "?").upper(), s)


def build(stats: Stats) -> str:
    """Render the whole profile to an SVG string, injecting the given stats."""
    today = stats.get("today") or datetime.date.today()
    E.clear()
    # --- title bar ---
    # y is the running vertical cursor. It picks up fractional values later
    # (spacer lines add LH*0.5, and ship_bottom is float via PLH=3.3), so it
    # must be float from the start — otherwise mypy locks it to int here and
    # rejects every float assignment below. iy = y inherits float from this.
    y: float = 40 + 30
    prompt(X0, y, "whoami")
    y += LH + 4

    portrait_lines = load_portrait()
    ptop = y - 4
    for i, ln in enumerate(portrait_lines):
        if not ln.strip():
            continue
        tl = len(ln) * (PFS * 0.6) * PSTRETCH
        E.append(f'<text x="{X0}" y="{ptop + i * PLH:.1f}" fill="#e2e2e2" font-size="{PFS}" '
                 f'textLength="{tl:.1f}" lengthAdjust="spacingAndGlyphs" '
                 f'xml:space="preserve">{esc(ln)}</text>')
    ship_bottom = ptop + len(portrait_lines) * PLH

    # --- info column ---
    iy = y
    # header
    E.append(f'<text x="{INFO_X}" y="{iy:.1f}"><tspan fill="{WHITE}" font-weight="700">neel</tspan>'
             f'<tspan fill="{DIM}" font-weight="700">@</tspan>'
             f'<tspan fill="{WHITE}" font-weight="700">github</tspan></text>')
    LN(INFO_X + 11 * CW + 10, iy - 4, RIGHT, iy - 4, RULE)
    iy += LH
    for row in SYSTEM:
        if row is None:
            iy += LH * 0.5
            continue
        k, v = row
        if v is None:
            v = age_string(today)
        info_row(iy, k, v)
        iy += LH
    iy += LH * 0.3
    section_head(iy, "— Contact")
    iy += LH
    for k, v in CONTACT:
        info_row(iy, k, v)
        iy += LH
    iy += LH * 0.3
    section_head(iy, "— GitHub Stats")
    iy += LH
    info_row(
        iy, "Repos", f"{stats['repos']}  |  Contributed: {stats['contrib']}")
    iy += LH
    info_row(iy, "Stars", f"{stats['stars']}")
    iy += LH
    if stats.get("views"):
        info_row(iy, "Views", f"{stats['views']}")
        iy += LH
    # Followers hidden for now — uncomment the next two lines to show it:
    # info_row(iy, "Followers", f"{stats['followers']}")
    # iy += LH
    info_row(iy, "Commits", f"{stats['commits']}")
    iy += LH
    loc_v = f"{stats['loc']}"
    T(INFO_X, iy, "Lines of Code", fill=DIM)
    T(RIGHT, iy, f"({stats['loc_add']}++, {stats['loc_del']}--)",
      fill=MUT, weight="400", anchor="end")
    T(RIGHT - (len(f"({stats['loc_add']}++, {stats['loc_del']}--)")) * CW - 10, iy, loc_v,
      fill=VAL, weight="700", anchor="end")
    iy += LH

    y = max(ship_bottom, iy) + LH

    # --- now ---
    prompt(X0, y, "cat now.txt")
    y += LH + 2
    for line in NOW:
        T(X0, y, "> ", fill=FAINT)
        T(X0 + 2 * CW, y, line, fill=BODY)
        y += LH
    y += LH

    # --- projects ---
    prompt(X0, y, "cat projects.txt")
    y += LH + 6
    for p in PROJECTS:
        T(X0, y, p["title"], fill=WHITE, weight="700")
        T(X0 + (len(p["title"]) + 1) * CW, y, " -> " + p["desc"], fill=MUT)
        y += LH + 2
        for ln in p["body"].split("\n"):
            T(X0, y, ln, fill=BODY)
            y += LH
        y += 4
        T(X0, y, "   " + p["stack"], fill=MUT)
        y += LH + 10

    # --- work ---
    prompt(X0, y, "cat work.txt")
    y += LH + 4
    CO = 28  # room for the logo column
    T(X0 + CO, y, "COMPANY", fill=MUT)
    T(WORK_ROLE_X, y, "ROLE", fill=MUT)
    T(WORK_WHEN_X, y, "WHEN", fill=MUT)
    LN(X0, y + 6, RIGHT, y + 6, "#2b2b2b")
    y += LH + 6
    for company, role, when in WORK:
        draw_logo(X0, y, company)
        T(X0 + CO, y, company, fill=WHITE, weight="700")
        T(WORK_ROLE_X, y, role, fill=BODY)
        T(WORK_WHEN_X, y, when, fill=DIM)
        y += LH + 2
    y += 6
    T(X0, y, WORK_NOTE, fill=FAINT)
    y += LH + 6

    # --- final prompt + cursor ---
    prompt(X0, y, "")
    cur_x = X0 + len("neel@github ~ % ") * CW
    E.append(f'<rect x="{cur_x:.1f}" y="{y - 13:.1f}" width="9" height="16" fill="{WHITE}">'
             f'<animate attributeName="opacity" values="1;1;0;0" dur="1.05s" repeatCount="indefinite"/></rect>')
    y += LH

    H = int(y + 18)
    font = ("ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, "
            "'DejaVu Sans Mono', 'Liberation Mono', monospace")
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{font}" font-size="{FS}">',
        f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>',
        f'<rect width="{W}" height="40" fill="{BAR}"/>',
        f'<line x1="0" y1="40" x2="{W}" y2="40" stroke="{BARLINE}"/>',
        f'<circle cx="24" cy="20" r="5.5" fill="#6a6a6a"/>',
        f'<circle cx="42" cy="20" r="5.5" fill="#454545"/>',
        f'<circle cx="60" cy="20" r="5.5" fill="#2c2c2c"/>',
        f'<text x="86" y="24.5" fill="#6a6a6a" font-size="12">neel@github: ~</text>',
    ]
    out.extend(E)
    out.append("</svg>")
    return "\n".join(out)


# Sample stats so `python render.py` previews the layout without the GitHub API.
PLACEHOLDER: Stats = {
    "repos": "23", "contrib": "41", "stars": "37", "followers": "58",
    "commits": "842", "views": "801", "loc": "446,276",
    "loc_add": "523,178", "loc_del": "76,902",
    "today": datetime.date.today(),
}

if __name__ == "__main__":
    svg = build(PLACEHOLDER)
    with open("dark_mode.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote dark_mode.svg")
