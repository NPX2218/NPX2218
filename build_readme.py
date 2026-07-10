#!/usr/bin/env python3
"""
build_readme.py — fetch live GitHub stats (via today.py) and render dark_mode.svg.

Run locally:   ACCESS_TOKEN=<pat> USER_NAME=NPX2218 python build_readme.py
The GitHub Action runs this on a schedule and commits the refreshed SVG.
"""
import datetime
import os
import re
import urllib.request

import today          # Andrew6rant's GraphQL fetch engine (unchanged)
import render         # our SVG layout / content

# The komarev counter is keyed on this string (not the GitHub handle). It must
# match the hidden <img> in README.md so the terminal "Views" number lines up
# with what visitors actually tick.
VIEWS_USERNAME = "neel-b5"


def fetch_views(username: str) -> int | None:
    """Read the current profile-view count from the komarev badge, or None on failure."""
    url = (f"https://komarev.com/ghpvc/?username={username}"
           f"&style=flat&color=0d1117&label=views")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        svg = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        # The value is the numeric <text> element (the "views" label is the other one).
        nums = [t for t in re.findall(r"<text[^>]*>([^<]+)</text>", svg)
                if re.fullmatch(r"[\d,]+", t.strip())]
        return int(nums[-1].replace(",", "")) if nums else None
    except Exception:
        return None


def main() -> None:
    """Fetch every stat, format it, and write the rendered SVG to dark_mode.svg."""
    os.makedirs("cache", exist_ok=True)  # today.py writes cache/<hash>.txt
    user_name = os.environ["USER_NAME"]

    # user_getter returns ({'id': ...}, createdAt); the id dict is what
    # loc_counter_one_repo compares each commit author against.
    owner_id, _created = today.user_getter(user_name)
    today.OWNER_ID = owner_id

    # loc_query -> [additions, deletions, net(add-del), cached]
    total_loc = today.loc_query(
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"], 7)
    commits = today.commit_counter(7)
    stars = today.graph_repos_stars("stars", ["OWNER"])
    repos = today.graph_repos_stars("repos", ["OWNER"])
    contrib = today.graph_repos_stars(
        "repos", ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"])
    followers = today.follower_getter(user_name)
    views = fetch_views(VIEWS_USERNAME)

    stats: render.Stats = {
        "repos": f"{repos:,}",
        "contrib": f"{contrib:,}",
        "stars": f"{stars:,}",
        "followers": f"{followers:,}",
        "commits": f"{commits:,}",
        "views": f"{views:,}" if views is not None else "",
        "loc": f"{total_loc[2]:,}",
        "loc_add": f"{total_loc[0]:,}",
        "loc_del": f"{total_loc[1]:,}",
        "today": datetime.date.today(),
    }

    svg = render.build(stats)
    with open("dark_mode.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print("dark_mode.svg updated ->",
          {k: stats[k] for k in ("repos", "stars", "commits", "loc")})


if __name__ == "__main__":
    main()
