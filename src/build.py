#!/usr/bin/env python3
"""PROJECT DOHA v0.1 — build the single self-contained index.html.

Inlines every illustration and style thumbnail as a base64 data URI so the
prototype still works when the one HTML file is opened on its own
(iPhone / iPad, no server, no assets folder).

Run:  python3 project-doha/src/build.py
"""
import base64
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "index.src.html")
OUT = os.path.join(ROOT, "index.html")
WEB = os.path.join(ROOT, "assets", "web")


def data_uri(name):
    path = os.path.join(WEB, name)
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")


TOKENS = {
    "IMG_living": "living.jpg",
    "IMG_space": "space.jpg",
    "IMG_giant": "giant.jpg",
    "IMG_ship": "ship.jpg",
    "T_3d": "style_3d.jpg",
    "T_storybook": "style_storybook.jpg",
    "T_clay": "style_clay.jpg",
    "T_block": "style_block.jpg",
    "T_comic": "style_comic.jpg",
    "T_photo": "style_photo.jpg",
    "T_crayon": "style_crayon.jpg",
    "T_pixel": "style_pixel.jpg",
}


def main():
    with open(SRC, encoding="utf-8") as f:
        html = f.read()
    for token, filename in TOKENS.items():
        html = html.replace("{{%s}}" % token, data_uri(filename))
    left = re.findall(r"\{\{[^}]+\}\}", html)
    if left:
        raise SystemExit("unreplaced tokens: %s" % left)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("built %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
