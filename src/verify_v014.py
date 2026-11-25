#!/usr/bin/env python3
"""PROJECT DOHA v0.1.4 검증 — 메인 화면 '따뜻한 동화·모험 톤' 리뉴얼.

디자인만 바뀌고 기능·정직성 표시는 그대로인지 확인하고, 영우님이 눈으로
확인할 미리보기 스크린샷을 만든다. 커밋·배포는 하지 않는다.

검증 항목
  A. 정직성 라벨·안전 UI 문구가 소스에 그대로 있는가
  B. 세 해상도에서 가로 밀림이 없는가 (문서 폭 = 창 폭, #app.scrollLeft = 0)
  C. 크림 배경 위 본문 글자가 읽을 만한가 (WCAG 대비 4.5:1, 큰 글씨 3:1)
  D. 무대(캔버스)는 따뜻한 밤하늘 프레임을 유지하는가
  E. 영화 화면 정지(제목 카드 .intro 표시) 상태에서 실제 사용자 클릭으로 ▶ 재생이 시작되는가
  F. 미리보기 스크린샷 저장 (downloads/doha-v0.1.4-preview)

사용:
  LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu \\
    python3 project-doha/src/verify_v014.py
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
SHOTS = "/workspace/downloads/doha-v0.1.4-preview"
REPORT = {"checks": [], "data": {}}
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
VIEWPORTS = [
    ("desktop", 1440, 900, 1, False),
    ("ipad", 1180, 820, 2, False),
    ("ipad-portrait", 820, 1180, 2, False),
    ("phone", 390, 844, 2, True),
]
CONTRAST = [
    # (selector, 화면, 최소 대비, 설명)
    (".home-copy h1", "home", 3.0, "홈 제목"),
    (".lede", "home", 4.5, "홈 소개문"),
    (".home-note", "home", 4.5, "홈 안내문"),
    (".st-card span", "home", 4.5, "그림체 카드 이름"),
    (".home-foot span", "home", 4.5, "홈 하단 문구"),
    (".brand-sub", "home", 4.5, "버전 표기"),
    (".chip", "canvas", 4.5, "예시 장면 칩"),
    (".cv-deck .hint", "canvas", 4.5, "캔버스 안내문"),
    (".stt-note", "canvas", 4.5, "자막 변환 안내"),
    (".cv-title strong", "canvas", 4.5, "캔버스 제목"),
    (".card-k", "movie", 4.5, "카드 라벨"),
    (".oneline .q", "movie", 3.0, "오늘의 한 줄"),
    (".parent p:not(.card-k)", "movie", 4.5, "관찰 노트 본문"),
    (".mv-actions .hint", "movie", 4.5, "영화 하단 안내"),
    (".tag", "movie", 4.5, "태그"),
    (".al-meta h3", "album", 4.5, "앨범 카드 제목"),
    (".al-meta .sub", "album", 4.5, "앨범 카드 부제"),
    (".al-card-btn", "album", 4.5, "앨범 카드 버튼"),
    (".al-sec-head p", "album", 4.5, "앨범 섹션 안내"),
]
CONTRAST_JS = """
(args) => {
  const [sel] = args;
  const el = document.querySelector(sel);
  if (!el) return null;
  const parse = (c) => {
    const m = String(c).match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const A = lum(a), B = lum(b), hi = Math.max(A, B), lo = Math.min(A, B); return (hi + 0.05) / (lo + 0.05); };
  const layers = [];
  let n = el, bg = [254, 248, 236];
  while (n && n.nodeType === 1) {
    const c = parse(getComputedStyle(n).backgroundColor);
    if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    n = n.parentElement;
  }
  for (let i = layers.length - 1; i >= 0; i--) {
    const l = layers[i];
    bg = [l[0] * l[3] + bg[0] * (1 - l[3]), l[1] * l[3] + bg[1] * (1 - l[3]), l[2] * l[3] + bg[2] * (1 - l[3])];
  }
  const fg = parse(getComputedStyle(el).color);
  const size = parseFloat(getComputedStyle(el).fontSize);
  return {text: (el.textContent || "").trim().slice(0, 24), color: getComputedStyle(el).color,
          bg: "rgb(" + bg.map((v) => Math.round(v)).join(",") + ")",
          ratio: Math.round(ratio(fg, bg) * 100) / 100, size: size};
}
"""


def check(name, ok, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + ("  · " + str(detail)[:300] if detail != "" else ""))


def static_checks():
    src = open(SRC, encoding="utf-8").read()
    check("버전 meta = 0.1.4", 'name="doha-version" content="0.1.4"' in src)
    check("홈 버전 표기 v0.1.4", "PROJECT DOHA · v0.1.4" in src)
    for label in ['광고 없음 · 이 브라우저에만', '이 브라우저에만 저장', '예시 장면',
                  '예시 그림 ·', '예시 필터 ·', '▶ 방금 녹음 듣기',
                  '음성 자막 변환 (임시 · 브라우저 서버 전송 가능)']:
        check("정직성 라벨 유지: " + label, label in src)
    check("녹음 전 동의 확인 문구 유지", "녹음" in src and "confirm(" in src)
    check("음성 자막 변환 토글 기본 OFF", 'id="sttBtn"' in src and 'aria-checked="false"' in src)
    check("원본 녹음 카드 유지", 'id="originalAudio"' in src)
    check("저장·내보내기 버튼 유지", 'id="saveAlbumBtn"' in src and "기록 + 음성 JSON" in src)
    check("일부 음성 누락을 정직하게 알리는 문구", "missingAudioClipCount" in src and "missingAudioNote" in src
          and "구간이 빠졌어요" in src)
    check("다크 톤 배경색(#120F0B) 제거", "#120F0B" not in src)
    check("크림 종이 배경 토큰", "--paper:#FEF8EC" in src)
    check("theme-color = 크림", 'name="theme-color" content="#FEF8EC"' in src)
    # 영화 제목 카드가 재생 바 클릭을 막지 않도록 클릭을 통과시키는지 (v0.1.4 버그 수정)
    intro_rule = re.search(r"\.intro\{([^}]*)\}", src)
    check("제목 카드 .intro 에 pointer-events:none",
          bool(intro_rule) and "pointer-events:none" in intro_rule.group(1),
          intro_rule.group(1)[-120:] if intro_rule else "no .intro rule")


def run_viewport(browser, name, w, h, dsf, mobile):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=dsf,
                              is_mobile=mobile, has_touch=mobile,
                              permissions=["microphone"], accept_downloads=True)
    page = ctx.new_page()
    errors, cerrs = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: d.accept())
    page.goto("file://" + SRC)
    page.wait_for_timeout(1100)

    def shot(tag, full=False):
        page.screenshot(path=os.path.join(SHOTS, "%s-%s.png" % (name, tag)), full_page=full)

    info = {"viewport": [w, h], "dsf": dsf}
    info["overflow_home"] = page.evaluate(
        "({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,"
        "appSL:document.querySelector('#app').scrollLeft,"
        "bodyBg:getComputedStyle(document.body).backgroundColor})")
    info["labels"] = {
        "none_ads": page.get_by_text("광고 없음 · 이 브라우저에만").count() > 0,
        "sample_tag": page.get_by_text("예시 장면", exact=True).count() > 0,
    }
    shot("home")

    # 캔버스 — 시작 직후에는 장면이 없는 빈 무대여야 한다(강제 시작 장면 없음)
    page.click("#startBtn")
    page.wait_for_timeout(800)
    info["canvas_empty_frames"] = page.evaluate("document.querySelectorAll('#stage .frame').length")
    shot("canvas-empty")
    page.evaluate("document.querySelector('#chipRow').parentElement.open = true")
    page.wait_for_timeout(200)
    page.click("#chipRow .chip:nth-child(2)")
    page.wait_for_timeout(1300)
    info["canvas"] = page.evaluate(
        "({title:document.querySelector('#cvMeta').textContent,"
        "cap:document.querySelector('#capText').textContent,"
        "frames:document.querySelectorAll('#stage .frame').length,"
        "img:!!document.querySelector('#stage .frame.on img').getAttribute('src'),"
        "stageBorder:getComputedStyle(document.querySelector('#stage')).borderTopWidth,"
        "stageBg:getComputedStyle(document.querySelector('#stage')).backgroundImage.slice(0,60)})")
    info["labels"]["only_browser"] = page.get_by_text("이 브라우저에만 저장").count() > 0
    info["labels"]["sample_caption"] = page.locator("#capText").inner_text().startswith("예시 그림 ·")
    shot("canvas")

    if page.locator("#styleBadge").is_visible():
        page.click("#styleBadge")
    else:
        # 휴대폰에서는 #styleBadge가 숨겨져 있어 칩의 '그림체 바꾸기'로 연다
        page.click("#chipRow .chip:nth-child(1)")
    page.wait_for_timeout(700)
    shot("canvas-sheet")
    page.click("#sheetClose")
    page.wait_for_timeout(400)

    # 영화 저장까지: 직접 입력한 한 줄 + 마이크 한 번으로 실제 장면과 원본 목소리를 만든다
    page.fill("#sayInput", "그때 하늘에서 별이 쏟아졌어")
    page.press("#sayInput", "Enter")
    page.wait_for_timeout(600)
    page.click("#micBtn")
    page.wait_for_function("__DOHA.mic().on")
    page.wait_for_timeout(1400)
    page.click("#micBtn")
    page.wait_for_function("!__DOHA.mic().on && !__DOHA.mic().stopping")
    page.wait_for_timeout(400)
    page.click("#endBtn")
    page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=15000)
    page.wait_for_timeout(900)
    shot("movie-intro")

    # 영화 화면이 멈춰 있는(제목 카드 .intro 가 보이는) 상태에서, 스크립트 호출이 아니라
    # 실제 사용자 클릭으로 ▶ 재생 버튼이 눌리고 재생이 시작되는지 확인한다.
    # (예전 버그: .intro 가 재생 바를 덮어 사람이 눌러도 아무 일이 없었다)
    play = {}
    play["intro_shown"] = page.evaluate(
        "!document.querySelector('#mvIntro').classList.contains('out')"
        " && getComputedStyle(document.querySelector('#mvIntro')).opacity !== '0'")
    play["tc_before"] = page.inner_text("#mvTc")
    play["icon_before"] = page.evaluate("document.querySelector('#playIcon path').getAttribute('d')")
    play["cover"] = page.evaluate("""() => {
        const b = document.querySelector('#playBtn');
        const r = b.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        const intro = document.querySelector('#mvIntro');
        return {tag: hit ? hit.tagName : null,
                onPlayBtn: !!(hit && (hit === b || b.contains(hit))),
                introPointerEvents: getComputedStyle(intro).pointerEvents,
                introZ: getComputedStyle(intro).zIndex};
    }""")
    play["clicked"] = False
    play["click_error"] = ""
    try:
        # Playwright의 click 은 실제 마우스 좌표로 누르고, 가로채는 요소가 있으면 실패한다.
        page.locator("#playBtn").click(timeout=5000)
        play["clicked"] = True
    except Exception as exc:  # noqa: BLE001 — 덮는 요소가 있으면 이 경로로 떨어진다
        play["click_error"] = str(exc).replace("\n", " ")[:280]
    page.wait_for_timeout(3600)
    play["tc_after"] = page.inner_text("#mvTc")
    play["icon_after"] = page.evaluate("document.querySelector('#playIcon path').getAttribute('d')")
    play["progress"] = page.evaluate("document.querySelector('#mvProg').style.width")
    play["intro_gone_while_playing"] = page.evaluate(
        "document.querySelector('#mvIntro').classList.contains('out')")
    info["movie_play"] = play

    info["movie"] = page.evaluate(
        "({tc:document.querySelector('#mvTc').textContent,"
        "cap:document.querySelector('#mvCap').textContent,"
        "audioCards:document.querySelectorAll('#originalAudio audio').length})")
    shot("movie")

    page.click("#mvAlbumBtn")
    page.wait_for_timeout(1000)
    info["album"] = page.evaluate(
        "({cards:document.querySelectorAll('.al-card-wrap').length,"
        "count:document.querySelector('#alCount').textContent})")
    info["overflow_album"] = page.evaluate(
        "({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,"
        "appSL:document.querySelector('#app').scrollLeft})")
    shot("album")
    page.click(".tab[data-tab='year']")
    page.wait_for_timeout(700)
    shot("yearbook")
    page.click(".tab[data-tab='capsule']")
    page.wait_for_timeout(700)
    shot("capsule")

    # 대비 — 홈으로 돌아가 화면별로 측정
    page.click("#alBack")
    page.wait_for_timeout(700)
    measured = {}
    for screen in ("home",):
        for sel, scr, minimum, label in CONTRAST:
            if scr != screen:
                continue
            res = page.evaluate(CONTRAST_JS, [sel])
            measured[label] = res
    page.click("#startBtn")
    page.wait_for_timeout(700)
    page.evaluate("document.querySelector('#chipRow').parentElement.open = true")
    for sel, scr, minimum, label in CONTRAST:
        if scr != "canvas":
            continue
        measured[label] = page.evaluate(CONTRAST_JS, [sel])
    page.fill("#sayInput", "다음엔 달에 가고 싶어")
    page.press("#sayInput", "Enter")
    page.wait_for_timeout(700)
    page.click("#endBtn")
    page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=15000)
    page.wait_for_timeout(600)
    for sel, scr, minimum, label in CONTRAST:
        if scr != "movie":
            continue
        measured[label] = page.evaluate(CONTRAST_JS, [sel])
    page.click("#mvAlbumBtn")
    page.wait_for_timeout(800)
    for sel, scr, minimum, label in CONTRAST:
        if scr != "album":
            continue
        measured[label] = page.evaluate(CONTRAST_JS, [sel])
    info["contrast"] = measured

    info["errors"] = errors
    info["console_errors"] = cerrs
    ctx.close()
    return info



def check_missing_audio_export(browser):
    """원본 음성 한 구간이 사라진 상태에서 내보내면 '일부 누락'을 알리는지 확인한다."""
    ctx = browser.new_context(viewport={"width": 1180, "height": 820}, permissions=["microphone"],
                              accept_downloads=True)
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto("file://" + SRC)
    page.wait_for_timeout(800)
    page.click("#startBtn")
    page.wait_for_timeout(500)
    page.fill("#sayInput", "가상의 두 번째 문장")
    page.press("#sayInput", "Enter")
    page.wait_for_timeout(500)
    page.click("#micBtn")
    page.wait_for_function("__DOHA.mic().on")
    page.wait_for_timeout(1200)
    page.click("#micBtn")
    page.wait_for_function("!__DOHA.mic().on && !__DOHA.mic().stopping")
    page.wait_for_timeout(300)
    page.click("#endBtn")
    page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=15000)
    page.wait_for_timeout(700)
    removed = page.evaluate("""async () => {
        const db = await new Promise((res, rej) => { const r = indexedDB.open('doha-universe'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
        const keys = await new Promise((res, rej) => { const r = db.transaction('clips').objectStore('clips').getAllKeys(); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
        if (!keys.length) return 0;
        await new Promise((res, rej) => { const t = db.transaction('clips', 'readwrite'); t.oncomplete = res; t.onabort = () => rej(t.error); t.objectStore('clips').delete(keys[0]); });
        db.close();
        return keys.length;
    }""")
    check("누락 시나리오 준비(원본 음성 1구간 삭제)", removed >= 1, removed)
    # 새로고침으로 메모리에 남은 Blob 회수 경로도 끊어, 실제로 파일에 담을 수 없는 상태를 만든다
    page.reload()
    page.wait_for_timeout(900)
    page.click("#albumBtn")
    page.wait_for_timeout(900)
    with page.expect_download() as event:
        page.locator(".al-card-wrap").first.get_by_text("기록 + 음성 JSON").click()
    path = event.value.path()
    data = json.loads(open(path, encoding="utf-8").read())
    toast = page.locator("#toast").text_content() or ""
    manifest = data.get("manifest", {})
    check("누락된 음성 수를 파일에 기록", manifest.get("missingAudioClipCount") == 1, manifest)
    check("파일 안에 누락 안내 문구", "찾지 못해" in str(manifest.get("missingAudioNote", "")), manifest.get("missingAudioNote"))
    check("파일 note에도 누락 표시", "빠져" in str(data.get("note", "")), data.get("note"))
    check("화면 안내도 '일부 음성 누락'을 알림", "빠졌어요" in toast, toast)
    check("내보내기 파일 자체는 정상 생성", os.path.getsize(path) > 0, os.path.getsize(path))
    ctx.close()


def main():
    os.makedirs(SHOTS, exist_ok=True)
    static_checks()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=FAKE)
        print("Chromium", browser.version, flush=True)
        results = {}
        for name, w, h, dsf, mobile in VIEWPORTS:
            print("---", name, flush=True)
            info = run_viewport(browser, name, w, h, dsf, mobile)
            results[name] = info
            ov = info["overflow_home"]
            check("[%s] 홈 가로 밀림 없음" % name, ov["sw"] == ov["cw"] and ov["appSL"] == 0, ov)
            check("[%s] 크림 배경(body)" % name, ov["bodyBg"] == "rgb(254, 248, 236)", ov["bodyBg"])
            check("[%s] 정직성 라벨 보임" % name,
                  info["labels"]["none_ads"] and info["labels"]["sample_tag"]
                  and info["labels"]["only_browser"] and info["labels"]["sample_caption"], info["labels"])
            check("[%s] 시작 직후 빈 무대(장면 0 · 예시 장면 강제 없음)" % name,
                  info["canvas_empty_frames"] == 0, info["canvas_empty_frames"])
            cv = info["canvas"]
            check("[%s] 캔버스: 예시 장면 그림 + '예시 그림 ·' 자막" % name,
                  cv["frames"] >= 1 and cv["img"] and info["labels"]["sample_caption"], cv)
            check("[%s] 무대 프레임 유지(크림 테두리·밤하늘 그라데이션)" % name,
                  float(cv["stageBorder"].replace("px","")) >= 5 and "gradient" in cv["stageBg"], cv["stageBorder"])
            al = info["overflow_album"]
            check("[%s] 앨범 가로 밀림 없음" % name, al["sw"] == al["cw"] and al["appSL"] == 0, al)
            mp = info["movie_play"]
            check("[%s] 영화 정지 상태에서 제목 카드가 ▶를 덮지 않음" % name,
                  mp["intro_shown"] and mp["cover"]["onPlayBtn"]
                  and mp["cover"]["introPointerEvents"] == "none", mp["cover"])
            check("[%s] 실제 클릭으로 ▶ 재생 시작(아이콘 · 타임코드 · 진행바 변화)" % name,
                  mp["clicked"] and mp["icon_after"] != mp["icon_before"]
                  and mp["tc_after"] != mp["tc_before"] and mp["progress"] not in ("", "0%")
                  and mp["intro_gone_while_playing"],
                  {k: mp[k] for k in ("clicked", "click_error", "tc_before", "tc_after",
                                      "progress", "intro_gone_while_playing")})
            check("[%s] 원본 목소리 카드 유지" % name, info["movie"]["audioCards"] >= 1, info["movie"])
            check("[%s] 런타임·콘솔 에러 0" % name, not info["errors"] and not info["console_errors"],
                  info["errors"] or info["console_errors"])
        print("--- 일부 음성 누락 내보내기", flush=True)
        check_missing_audio_export(browser)
        browser.close()

    base = results["ipad"]["contrast"]
    REPORT["data"]["contrast"] = base
    for sel, scr, minimum, label in CONTRAST:
        res = base.get(label)
        ok = bool(res) and res["ratio"] >= minimum
        check("대비 %s(%s) %.2f ≥ %.1f" % (label, scr, res["ratio"] if res else 0, minimum), ok, res)

    REPORT["data"]["viewports"] = results
    ok = all(c["ok"] for c in REPORT["checks"])
    print("\n=== RESULT:", "ALL PASS" if ok else "FAILED", "=== (%d checks)" % len(REPORT["checks"]))
    print("screenshots:", SHOTS)
    print(json.dumps({"shots": sorted(os.listdir(SHOTS))}, ensure_ascii=False)[:1200])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
