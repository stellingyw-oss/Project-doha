#!/usr/bin/env python3
"""커밋된 index.html 이 src/index.src.html 과 어긋나지 않았는지 검사한다.

빌드 소스를 고치고 build.py 를 돌리지 않은 채 index.html 만 손대면,
다음 빌드에서 그 변경이 조용히 사라진다(PR #1 통합 때 실제로 있었던 사고).
그래서 테스트 앞단에서 이 검사를 같이 돌린다.

사용:  python3 project-doha/src/check_build.py   (어긋나면 exit 1)
"""
import base64
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "index.src.html")
OUT = os.path.join(ROOT, "index.html")
WEB = os.path.join(ROOT, "assets", "web")

TOKENS = {
    "IMG_living": "living.jpg", "IMG_space": "space.jpg",
    "IMG_giant": "giant.jpg", "IMG_ship": "ship.jpg",
    "T_3d": "style_3d.jpg", "T_storybook": "style_storybook.jpg",
    "T_clay": "style_clay.jpg", "T_block": "style_block.jpg",
    "T_comic": "style_comic.jpg", "T_photo": "style_photo.jpg",
    "T_crayon": "style_crayon.jpg", "T_pixel": "style_pixel.jpg",
}


def build_text():
    with open(SRC, encoding="utf-8") as f:
        html = f.read()
    for token, filename in TOKENS.items():
        path = os.path.join(WEB, filename)
        with open(path, "rb") as f:
            uri = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
        html = html.replace("{{%s}}" % token, uri)
    left = re.findall(r"\{\{[^}]+\}\}", html)
    if left:
        raise SystemExit("unreplaced tokens: %s" % left)
    return html


def main():
    expected = build_text()
    with open(OUT, encoding="utf-8") as f:
        actual = f.read()
    if expected == actual:
        print("OK  index.html == build(src/index.src.html)  (%d bytes)" % len(actual.encode("utf-8")))
        return 0
    print("DRIFT  index.html differs from src/index.src.html", file=sys.stderr)
    print("       src=%d bytes  index=%d bytes" % (len(expected.encode("utf-8")), len(actual.encode("utf-8"))), file=sys.stderr)
    print("       fix: python3 src/build.py", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
