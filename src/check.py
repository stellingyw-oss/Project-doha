#!/usr/bin/env python3
"""Functional + visual check for PROJECT DOHA v0.1 (headless Chromium)."""
import os, sys, json
from playwright.sync_api import sync_playwright

ROOT = "/workspace"
URL = "file://" + os.path.join(ROOT, "project-doha", "index.html")
OUT = os.path.join(ROOT, "tmp", "shots")
os.makedirs(OUT, exist_ok=True)

VIEWPORTS = {
    "ipad-land": dict(width=1180, height=820, dsf=2),
    "ipad-port": dict(width=820, height=1180, dsf=2),
    "iphone": dict(width=390, height=844, dsf=3),
}

def run(pw):
    browser = pw.chromium.launch()
    results = {}
    for name, vp in VIEWPORTS.items():
        ctx = browser.new_context(viewport={"width": vp["width"], "height": vp["height"]},
                                  device_scale_factor=vp["dsf"], is_mobile=(name == "iphone"),
                                  has_touch=True)
        page = ctx.new_page()
        logs, errors = [], []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.wait_for_timeout(1200)
        info = {}
        info["home_scroll"] = page.evaluate("({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,sh:document.querySelector('.home-wrap').scrollHeight,ch:document.querySelector('.home-scroll').clientHeight})")
        page.screenshot(path=f"{OUT}/{name}-home.png")

        # start story
        page.click("#startBtn")
        page.wait_for_timeout(1500)
        info["canvas"] = page.evaluate("({frames:document.querySelectorAll('.stage .frame').length, cap:document.querySelector('#capText').textContent, title:document.querySelector('#cvTitle').textContent})")
        page.screenshot(path=f"{OUT}/{name}-canvas1.png")

        # tap two chips
        chips = page.query_selector_all("#chipRow .chip")
        chips[2].click()
        page.wait_for_timeout(1100)
        chips[4].click()
        page.wait_for_timeout(1100)
        info["after_chips"] = page.evaluate("({frames:document.querySelectorAll('.stage .frame').length, scenes:document.querySelector('#cvMeta').textContent, title:document.querySelector('#cvTitle').textContent, cap:document.querySelector('#capText').textContent})")
        page.screenshot(path=f"{OUT}/{name}-canvas2.png")

        # purple tint chip
        chips[3].click()
        page.wait_for_timeout(1100)
        page.screenshot(path=f"{OUT}/{name}-canvas3.png")

        # style change
        chips[6].click()
        page.wait_for_timeout(900)
        info["style"] = page.evaluate("document.querySelector('#styleBadge').textContent")
        page.screenshot(path=f"{OUT}/{name}-canvas-comic.png")

        # end story -> movie
        page.click("#endBtn")
        page.wait_for_timeout(1000)
        info["movie"] = page.evaluate("({title:document.querySelector('#introTitle').textContent, total:document.querySelector('#mvTc').textContent, dots:document.querySelectorAll('#mvDots i').length})")
        page.screenshot(path=f"{OUT}/{name}-movie-intro.png")
        page.wait_for_timeout(3200)
        page.screenshot(path=f"{OUT}/{name}-movie.png")
        page.wait_for_timeout(2000)
        info["movie_progress"] = page.evaluate("document.querySelector('#mvTc').textContent")

        # album
        page.click("#mvAlbumBtn")
        page.wait_for_timeout(900)
        info["album"] = page.evaluate("({cards:document.querySelectorAll('.al-card').length, count:document.querySelector('#alCount').textContent})")
        page.screenshot(path=f"{OUT}/{name}-album.png", full_page=False)
        # year book tab
        page.click(".tab[data-tab='year']")
        page.wait_for_timeout(600)
        page.screenshot(path=f"{OUT}/{name}-yearbook.png")
        page.click(".tab[data-tab='capsule']")
        page.wait_for_timeout(600)
        page.screenshot(path=f"{OUT}/{name}-capsule.png")

        info["errors"] = page.evaluate("window.__ERRORS || []")
        info["pageerrors"] = errors
        info["console_error"] = [l for l in logs if l.startswith("error")]
        results[name] = info
        ctx.close()
    browser.close()
    return results

with sync_playwright() as pw:
    res = run(pw)
print(json.dumps(res, ensure_ascii=False, indent=1))
