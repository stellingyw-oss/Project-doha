#!/usr/bin/env python3
"""Capture the review screenshots for PROJECT DOHA v0.1."""
import os
from playwright.sync_api import sync_playwright

URL = "file:///workspace/project-doha/index.html"
DL = "/workspace/downloads"
os.makedirs(DL, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1180, "height": 820}, device_scale_factor=2)
    pg = ctx.new_page()
    logs, errs = [], []
    pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(1400)

    # 1. home
    pg.screenshot(path=f"{DL}/project_doha_v01_home.png")

    # 2. canvas — a few scenes
    pg.click("#startBtn")
    pg.wait_for_timeout(1600)
    chips = pg.query_selector_all("#chipRow .chip")
    chips[2].click()           # 더 크게
    pg.wait_for_timeout(1200)
    chips[4].click()           # 같이 우주선
    pg.wait_for_timeout(1200)
    pg.fill("#sayInput", "달이 온통 치즈로 만들어졌어!")
    pg.press("#sayInput", "Enter")
    pg.wait_for_timeout(1400)
    pg.screenshot(path=f"{DL}/project_doha_v01_canvas.png")

    # 3. movie
    pg.click("#endBtn")
    pg.wait_for_timeout(6200)
    pg.screenshot(path=f"{DL}/project_doha_v01_movie.png")

    # 4. album (extra)
    pg.wait_for_timeout(500)
    pg.click("#mvAlbumBtn")
    pg.wait_for_timeout(900)
    pg.screenshot(path=f"{DL}/project_doha_v01_album.png")

    print("errors:", pg.evaluate("window.__ERRORS || []"), errs, [l for l in logs if l.startswith("error")])
    print("title:", pg.evaluate("document.querySelector('.al-title h1').textContent"))
    b.close()
