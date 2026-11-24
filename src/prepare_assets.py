#!/usr/bin/env python3
"""PROJECT DOHA v0.1 — asset preparation.

- Resizes the four generated scene illustrations for embedding (JPEG).
- Renders 8 small style thumbnails from one base scene so the art-style
  picker shows a real preview of every style.

Run:  python3 project-doha/src/prepare_assets.py
"""
import os
import random
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ASSETS, "web")
os.makedirs(OUT, exist_ok=True)

SCENES = {
    "living": "scene1_livingroom.png",
    "space": "scene2_space.png",
    "giant": "scene3_giant.png",
    "ship": "scene4_spaceship.png",
}


def sat(im, f):
    return ImageEnhance.Color(im).enhance(f)


def con(im, f):
    return ImageEnhance.Contrast(im).enhance(f)


def bri(im, f):
    return ImageEnhance.Brightness(im).enhance(f)


def crop_16x9(im):
    w, h = im.size
    target = 16 / 9
    if w / h > target:
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
    else:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h + nh) // 2))
    return im


def mosaic(im, block, sample=Image.BILINEAR):
    w, h = im.size
    small = im.resize((max(1, w // block), max(1, h // block)), sample)
    return small.resize((w, h), Image.NEAREST)


def grain(im, amount, seed=3):
    rnd = random.Random(seed)
    px = im.load()
    w, h = im.size
    for _ in range((w * h) // 8):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]
        n = rnd.randint(-amount, amount)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return im


def storybook(im):
    v = bri(con(sat(im, 0.55), 0.9), 1.12).filter(ImageFilter.GaussianBlur(1.1))
    paper = Image.new("RGB", v.size, "#f6e7c9")
    return Image.blend(v, ImageChops.multiply(v, paper), 0.25)


def clay(im):
    return bri(con(sat(im, 1.8), 1.2), 1.05).filter(ImageFilter.GaussianBlur(0.6))


def block(im):
    m = con(sat(mosaic(im, 10, Image.BOX), 1.5), 1.12)
    d = ImageDraw.Draw(m)
    w, h = m.size
    for x in range(0, w, 10):
        d.line([(x, 0), (x, h)], fill=(20, 14, 10), width=1)
    for y in range(0, h, 10):
        d.line([(0, y), (w, y)], fill=(20, 14, 10), width=1)
    return m


def comic(im):
    """Comic-print grade: strong colour, flat contrast, halftone screen."""
    v = bri(con(sat(im, 1.6), 1.18), 1.06)
    dots = Image.new("L", v.size, 255)
    d = ImageDraw.Draw(dots)
    for y in range(0, v.size[1], 5):
        for x in range(0, v.size[0], 5):
            d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=170)
    v = Image.blend(v, ImageChops.multiply(v, dots.convert("RGB")), 0.22)
    return v


def photo(im):
    v = con(sat(im, 1.03), 1.08).filter(ImageFilter.UnsharpMask(2, 120, 2))
    return grain(v, 10)


def crayon(im):
    v = ImageOps.posterize(sat(bri(im, 1.16), 1.3), 3)
    v = v.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.9))
    paper = Image.new("RGB", v.size, "#f3e8d6")
    v = Image.blend(v, Image.blend(v, paper, 0.3), 0.5)
    tex = Image.effect_noise(v.size, 34).convert("RGB")
    v = Image.blend(v, Image.blend(v, tex, 0.1), 0.55)
    return grain(v, 14, 9)


def pixel(im):
    return ImageOps.posterize(mosaic(im, 8), 4)


THUMBS = {
    "3d": lambda im: im,
    "storybook": storybook,
    "clay": clay,
    "block": block,
    "comic": comic,
    "photo": photo,
    "crayon": crayon,
    "pixel": pixel,
}


def main():
    total = 0
    for key, fname in SCENES.items():
        im = Image.open(os.path.join(ASSETS, fname)).convert("RGB")
        im = crop_16x9(im).resize((1200, 675), Image.LANCZOS)
        path = os.path.join(OUT, f"{key}.jpg")
        im.save(path, "JPEG", quality=72, optimize=True, progressive=True)
        size = os.path.getsize(path)
        total += size
        print(f"scene {key}: 1200x675 {size // 1024} KB")

    base = Image.open(os.path.join(ASSETS, "scene1_livingroom.png")).convert("RGB")
    base = crop_16x9(base).resize((360, 202), Image.LANCZOS)
    ttotal = 0
    for style, fn in THUMBS.items():
        tim = fn(base.copy())
        path = os.path.join(OUT, f"style_{style}.jpg")
        tim.save(path, "JPEG", quality=78, optimize=True, progressive=True)
        size = os.path.getsize(path)
        ttotal += size
        print(f"style {style}: {size // 1024} KB")
    print(f"TOTAL scenes {total // 1024} KB · thumbs {ttotal // 1024} KB · sum {(total + ttotal) // 1024} KB")


if __name__ == "__main__":
    main()
