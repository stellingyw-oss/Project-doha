#!/usr/bin/env python3
"""Deeper interaction test: style sheet, mic fallback, movie end, album persistence."""
import json
from playwright.sync_api import sync_playwright

URL = "file:///workspace/project-doha/index.html"

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1180, "height": 820}, permissions=[])
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(900)

    out = {}

    # style sheet from home picker
    pg.click(".st-card:nth-child(7)")   # crayon
    out["style_home"] = pg.inner_text("#styleNow")
    pg.click(".st-card:nth-child(1)")   # back to 3d

    # canvas + style sheet mid-story
    pg.click("#startBtn")
    pg.wait_for_timeout(1500)
    pg.query_selector_all("#chipRow .chip")[0].click()  # 그림체 바꾸기
    pg.wait_for_timeout(500)
    out["sheet_open"] = pg.eval_on_selector("#styleSheet", "e=>e.classList.contains('on')")
    pg.click("#sheetRow .st-card:nth-child(6)")          # 실사
    pg.wait_for_timeout(800)
    out["sheet_closed"] = pg.eval_on_selector("#styleSheet", "e=>!e.classList.contains('on')")
    out["style_canvas"] = pg.inner_text("#styleBadge")

    # custom input
    pg.fill("#sayInput", "공룡이 라면을 끓이기 시작했어!")
    pg.press("#sayInput", "Enter")
    pg.wait_for_timeout(1200)
    out["scenes"] = pg.inner_text("#cvMeta")
    out["title"] = pg.inner_text("#cvTitle")

    # mic (no permission granted -> fallback path)
    pg.click("#micBtn")
    pg.wait_for_timeout(900)
    out["mic_listening"] = pg.eval_on_selector("#micBtn", "e=>e.classList.contains('listening')")
    out["toast"] = pg.inner_text("#toast")
    pg.click("#micBtn")
    pg.wait_for_timeout(300)
    out["mic_off"] = pg.eval_on_selector("#micBtn", "e=>!e.classList.contains('listening')")

    # movie -> wait to the end
    pg.click("#endBtn")
    pg.wait_for_timeout(1000)
    out["movie_dots"] = pg.eval_on_selector_all("#mvDots i", "els=>els.length")
    pg.wait_for_timeout(21000)
    out["ended"] = pg.eval_on_selector("#mvEnded", "e=>e.classList.contains('on')")
    out["tc_end"] = pg.inner_text("#mvTc")

    # dad note + save + persistence
    pg.fill("#dadNote", "오늘은 라면 냄새 나는 상상이었다.")
    pg.click("#saveAlbumBtn")
    pg.wait_for_timeout(900)
    out["album_cards"] = pg.eval_on_selector_all(".al-card", "els=>els.length")
    out["first_title"] = pg.inner_text(".al-card .al-meta h3")

    pg.reload()
    pg.wait_for_timeout(900)
    pg.click("#albumBtn")
    pg.wait_for_timeout(700)
    out["after_reload_cards"] = pg.eval_on_selector_all(".al-card", "els=>els.length")
    out["after_reload_title"] = pg.inner_text(".al-card .al-meta h3")
    out["after_reload_count"] = pg.inner_text("#alCount")

    out["errors"] = pg.evaluate("window.__ERRORS||[]")
    out["pageerrors"] = errs
    print(json.dumps(out, ensure_ascii=False, indent=1))
    b.close()
