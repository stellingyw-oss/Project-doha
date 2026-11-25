#!/usr/bin/env python3
"""PROJECT DOHA v0.2 첫 실험 검증 — 가상 티키타카 대화(검토용).

실제 아이 목소리·실제 대화·외부 API·유료 호출 없이, 브라우저 안에서 만든
합성 음성(Web Audio/WAV Blob)과 모의 자막만으로 확인한다.

검증 항목
  A. 세 마디가 원래 순서로 끊김 없이 재생되는가 (예약 타임라인 + 실제 재생 로그)
  B. 마지막에 바꾼 그림체·분위기가 장면에 반영되는가 (재생 중 변경 포함)
  C. 자막이 늦거나 빠져도 대화가 계속되고, 원본 음성(WAV)이 보존되며,
     늦게 도착한 문장이 다음 마디·화면에 잘못 붙지 않는가
  D. 재생 중에도 말을 계속 더할 수 있는가 (재생 순서에 끼어들지 않음)
  E. v0.1.4에서 만든 가상 작품이 이 검토본에서도 재생·내보내기 되는가
     (같은 오리진에 /legacy/ 로 v0.1.4 빌드를 함께 내려 실제 교차 버전 확인)
  F. 검토 화면에 모의 자막·예시 그림·합성 음성 표시가 있고, 콘솔·런타임 에러가 0인가
  G. 시연 스크린샷(downloads/doha-v0.2-exp-preview) 저장

사용:
  python3 src/build.py && python3 src/check_build.py
  LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu python3 src/verify_v02_exp.py
"""
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
LEGACY = os.path.join(ROOT, ".legacy-v014")          # v0.1.4 빌드(테스트용, 커밋하지 않음)
SHOTS = "/workspace/downloads/doha-v0.2-exp-preview"
PORT = 8796
BASE = "http://127.0.0.1:%d" % PORT
PORT_LEGACY_COMMIT = "b11387d"                       # v0.1.4 main 병합 커밋
CHECKS = []
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
L1, L2, L3 = "달이 치즈야", "그럼 한입 먹어도 돼?", "안 돼, 그건 달의 귀야!"


def check(name, ok, detail=""):
    CHECKS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + ("  · " + str(detail)[:300] if detail != "" else ""))


def note(name, detail=""):
    print("SKIP " + name + ("  · " + str(detail)[:300] if detail != "" else ""))


# ---------------------------------------------------------------- 정적 검사
def static_checks():
    src = open(SRC, encoding="utf-8").read()
    check("기준 버전 meta = 0.1.4 (v0.1.4 동작 그대로)", 'name="doha-version" content="0.1.4"' in src)
    check("실험 표식 meta = 0.2-exp", 'name="doha-experiment" content="0.2-exp"' in src)
    check("홈에 실험 진입 버튼", 'id="expBtn"' in src and "v0.2 티키타카 실험 (검토용)" in src)
    check("홈에 실험 안내(합성 음성·모의 자막·외부 API 없음)",
          "합성 음성과 모의 자막으로만" in src and "외부 API·유료 호출 없이" in src)
    for label in ["모의 자막 · 예시 그림", "검토용 실험입니다", "합성 음성(삐- 소리)", "예시 그림",
                  "합성 음성 WAV", "자막 시뮬레이션", "마지막에 바꾼 설정"]:
        check("정직성 표시 유지: " + label, label in src)
    check("세 마디 대본이 그대로 들어 있음", all(t in src for t in (L1, L2, L3)))
    check("자막 늦게/누락 시뮬레이션 버튼", 'data-sim="late"' in src and 'data-sim="missing"' in src)
    check("늦은 자막을 제자리에만 붙이는 함수", "tikiCommitSub" in src and "바디에만 붙임" not in src)
    check("외부 API·fetch·XHR 없음", "fetch(" not in src and "XMLHttpRequest" not in src
          and "openai" not in src.lower() and "api.openai" not in src)
    check("저장 스키마(도하·IndexedDB) 변경 없음", 'DB_NAME="doha-universe", DB_VER=1' in src)
    check("v0.1.4 정직성 라벨 유지(광고 없음·예시 그림)",
          "광고 없음 · 이 브라우저에만" in src and "예시 그림 · " in src)


# ---------------------------------------------------------------- 로컬 서버
def make_handler():
    class Dual(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            p = urllib.parse.urlparse(path).path
            if p.startswith("/legacy"):
                rel = p[len("/legacy"):].lstrip("/") or "index.html"
                return os.path.join(LEGACY, rel)
            return os.path.join(ROOT, p.lstrip("/") or "index.html")

        def log_message(self, *a):
            pass

    return functools.partial(Dual, directory=ROOT)


def start_server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def prepare_legacy():
    os.makedirs(LEGACY, exist_ok=True)
    out = os.path.join(LEGACY, "index.html")
    try:
        data = subprocess.check_output(["git", "-C", ROOT, "show",
                                        PORT_LEGACY_COMMIT + ":index.html"], stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001 — 얕은 클론 등에서는 이 항목만 건너뛴다
        return False, str(exc)[:200]
    open(out, "wb").write(data)
    text = data.decode("utf-8", "replace")
    return ('name="doha-version" content="0.1.4"' in text and 'id="s-exp"' not in text), len(data)


def new_page(browser, w=1180, h=820, mobile=False):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1,
                              is_mobile=mobile, has_touch=mobile,
                              permissions=["microphone"], accept_downloads=True)
    page = ctx.new_page()
    errors, cerrs, reqs = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: reqs.append(r.url))
    return ctx, page, errors, cerrs, reqs


SAMPLER = """
window.__EXP_SAMPLES = [];
window.__EXP_IV = setInterval(function(){
  var s = (window.__DOHA && __DOHA.tiki) ? __DOHA.tiki.state() : {};
  var el = document.querySelector('#expCapText');
  __EXP_SAMPLES.push({curId: s.curId, playing: !!s.playing, cap: el ? el.textContent : ''});
}, 60);
"""


def stop_sampler(page):
    page.evaluate("clearInterval(window.__EXP_IV)")


def wav_info(page, url):
    return page.evaluate("""async (url) => {
        const r = await fetch(url);
        const b = await r.arrayBuffer();
        const v = new DataView(b);
        const s = (o, n) => String.fromCharCode.apply(null, new Uint8Array(b, o, n));
        const sr = v.getUint32(24, true);
        const dataBytes = v.getUint32(40, true);
        return {status: r.status, bytes: b.byteLength, riff: s(0, 4), wave: s(8, 4),
                sr: sr, ch: v.getUint16(22, true), bits: v.getUint16(34, true),
                dur: Math.round(dataBytes / (sr * 2) * 1000) / 1000};
    }""", url)


# ---------------------------------------------------------------- A. 순서·끊김
def run_play(browser):
    ctx, page, errors, cerrs, reqs = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(900)
    page.screenshot(path=os.path.join(SHOTS, "01-home-exp-button.png"))
    page.click("#expBtn")
    page.wait_for_timeout(500)
    info = {}
    info["screen"] = page.evaluate("__DOHA.state.screen")
    info["labels"] = page.evaluate("""() => ({
        flag: !!Array.prototype.find.call(document.querySelectorAll('.exp-flag'), e => e.textContent.includes('모의 자막')),
        notice: document.querySelector('#expNotice').textContent,
        tags: Array.prototype.map.call(document.querySelectorAll('.exp-frame .tag'), e => e.textContent),
        frameCount: document.querySelectorAll('.exp-frame').length,
        lineCount: document.querySelectorAll('.exp-line').length,
        styles: document.querySelectorAll('#expStyleRow .st-card').length,
        capTag: document.querySelector('#expCapTag').textContent,
        ears: document.querySelector('#expEar').classList.contains('on'),
        on3: document.querySelectorAll('.exp-frame')[2].classList.contains('on')})""")
    page.screenshot(path=os.path.join(SHOTS, "02-exp-idle.png"))
    info["lines_before"] = page.evaluate("__DOHA.tiki.lines()")
    info["wav"] = [wav_info(page, ln["wav"]) for ln in info["lines_before"]]

    page.evaluate(SAMPLER)
    page.click("#expPlay")
    page.wait_for_timeout(2600)                     # 두 번째 마디가 흐르는 중
    page.screenshot(path=os.path.join(SHOTS, "03-exp-playing.png"))
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    stop_sampler(page)
    page.wait_for_timeout(200)
    info["state"] = page.evaluate("__DOHA.tiki.state()")
    info["timeline"] = page.evaluate("__DOHA.tiki.timeline()")
    info["subs"] = page.evaluate("__DOHA.tiki.subs()")
    info["log"] = page.evaluate("__DOHA.tiki.log()")
    info["samples"] = page.evaluate("__EXP_SAMPLES")
    info["cap"] = page.inner_text("#expCapText")
    info["ears_end"] = page.evaluate("__DOHA.tiki.ears()")
    info["frames_end"] = page.evaluate("__DOHA.tiki.frames()")
    info["lines_after"] = page.evaluate("__DOHA.tiki.lines()")
    info["external_requests"] = [u for u in reqs if u.startswith("http") and not u.startswith(BASE)]
    page.locator("#expLines").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS, "04-exp-lines.png"))
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_play(info):
    lb = info["labels"]
    check("실험 화면 진입", info["screen"] == "exp", info["screen"])
    check("검토 표시: '모의 자막 · 예시 그림' 배지", lb["flag"])
    check("검토 안내: 합성 음성·모의 자막·예시 그림·외부 API 없음",
          all(k in lb["notice"] for k in ("합성 음성", "모의 자막", "예시 그림", "외부 API", "실제 아이 목소리")),
          lb["notice"][:90])
    check("무대와 마디 카드 모두 '예시 그림' 표시", lb["tags"] == ["예시 그림"] * 3, lb["tags"])
    check("세 마디 카드 · 여덟 그림체", lb["lineCount"] == 3 and lb["styles"] == 8, lb)
    check("처음부터 마지막 '달의 귀' 장면이 보임", lb["on3"] and lb["ears"], lb)
    tl = info["timeline"]
    check("타임라인 순서 l1→l2→l3", [t["id"] for t in tl] == ["l1", "l2", "l3"], tl)
    gaps = [round(tl[i + 1]["start"] - tl[i]["end"], 3) for i in range(len(tl) - 1)]
    check("마디 사이 끊김 없음(빈 구간 0.12초 고정·겹침 없음)",
          all(g >= 0 for g in gaps) and all(abs(g - 0.12) < 0.001 for g in gaps), gaps)
    check("첫 마디는 0초에서 시작", abs(tl[0]["start"]) < 0.001, tl[0])
    check("재생 완료(done) 상태", info["state"]["done"] is True, info["state"])
    check("전체 길이 = 마디 합 + 간격", abs(info["state"]["total"] - (tl[-1]["end"])) < 0.02,
          {"total": info["state"]["total"], "end": tl[-1]["end"]})
    logs = info["log"]
    order = [l for l in logs if "재생 시작" in l]
    check("로그상 재생 순서 l1→l2→l3",
          [o.split()[-1] for o in order] == ["l1", "l2", "l3"], order)
    ends = [l for l in logs if "재생 끝" in l]
    check("세 마디 모두 끝까지 재생", [e.split()[-1] for e in ends] == ["l1", "l2", "l3"], ends)
    check("자막 세 개 모두 제자리에 도착",
          [s["status"] for s in info["subs"]] == ["shown"] * 3
          and [s["shown"] for s in info["subs"]] == [L1, L2, L3], info["subs"])
    check("재생이 끝난 뒤 '달의 귀' 장면·자막 유지",
          info["ears_end"]["on"] and info["cap"] == L3 and info["frames_end"][2]["on"],
          {"ears": info["ears_end"], "cap": info["cap"]})
    # 실제로 다시 들을 수 있는 합성 음성 자산(원본) 확인
    wavs = info["wav"]
    check("합성 음성 3개가 WAV Blob으로 보관", all(w["status"] == 200 and w["riff"] == "RIFF"
                                            and w["wave"] == "WAVE" for w in wavs), wavs)
    check("WAV 규격(22050Hz·모노·16bit)", all(w["sr"] == 22050 and w["ch"] == 1 and w["bits"] == 16 for w in wavs), wavs)
    check("WAV 길이가 마디 길이와 일치",
          [round(w["dur"], 2) for w in wavs] == [round(t["end"] - t["start"], 2) for t in tl],
          {"wav": [w["dur"] for w in wavs], "timeline": [round(t["end"] - t["start"], 2) for t in tl]})
    check("합성 음성 용량 3개 모두 0 이상", all(w["bytes"] > 10000 for w in wavs), [w["bytes"] for w in wavs])
    check("외부 요청 0건(라이브 서버 밖으로 나가지 않음)", not info["external_requests"],
          info["external_requests"][:3])
    check("재생 흐름 런타임·콘솔 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- C-1. 늦은 자막
def run_late(browser):
    ctx, page, errors, cerrs, _ = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(800)
    page.click("#expBtn")
    page.wait_for_timeout(400)
    page.click("#expSimRow [data-sim='late']")
    page.evaluate(SAMPLER)
    page.click("#expPlay")
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    stop_sampler(page)
    page.wait_for_timeout(200)
    info = {
        "state": page.evaluate("__DOHA.tiki.state()"),
        "subs": page.evaluate("__DOHA.tiki.subs()"),
        "timeline": page.evaluate("__DOHA.tiki.timeline()"),
        "log": page.evaluate("__DOHA.tiki.log()"),
        "samples": page.evaluate("__EXP_SAMPLES"),
        "lines": page.evaluate("__DOHA.tiki.lines()"),
        "cards": page.evaluate("""() => Array.prototype.map.call(document.querySelectorAll('.exp-line'), li => ({
            id: li.getAttribute('data-line'), txt: li.querySelector('.txt').textContent,
            st: li.querySelector('.st').textContent, cls: li.querySelector('.st').className}))"""),
        "cap": page.inner_text("#expCapText"),
    }
    page.locator("#expLines").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS, "05-exp-late-subtitle.png"))
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_late(info):
    subs = {s["id"]: s for s in info["subs"]}
    check("늦은 자막 시나리오 — 두 번째 마디가 'l3 재생 중'에 도착",
          subs["l2"]["status"] == "late" and subs["l2"]["during"] == "l3", subs["l2"])
    check("늦은 자막은 두 번째 마디 카드에 그대로 보관",
          subs["l2"]["shown"] == L2 and [c for c in info["cards"] if c["id"] == "l2"][0]["st"] == "늦게 도착",
          [c for c in info["cards"] if c["id"] == "l2"])
    check("세 번째 마디 자막은 제자리(정상 도착)", subs["l3"]["status"] == "shown" and subs["l3"]["shown"] == L3, subs["l3"])
    cards3 = [c for c in info["cards"] if c["id"] == "l3"][0]
    check("세 번째 마디 카드에 두 번째 문장이 섞이지 않음",
          L2 not in cards3["txt"] and L3 in cards3["txt"], cards3)
    during_l3 = [s for s in info["samples"] if s["curId"] == "l3"]
    check("세 번째 마디가 흐르는 동안 무대에 두 번째 문장이 붙지 않음",
          bool(during_l3) and all(L2 not in s["cap"] for s in during_l3),
          {"samples": len(during_l3), "bad": [s for s in during_l3 if L2 in s["cap"]][:2]})
    check("세 번째 마디가 흐르는 동안 무대는 세 번째 문장을 유지",
          any(L3 in s["cap"] for s in during_l3), [s["cap"] for s in during_l3][:3])
    tl = info["timeline"]
    check("대화가 중단되지 않고 끝까지 재생(l1→l2→l3)",
          [t["id"] for t in tl] == ["l1", "l2", "l3"]
          and len([l for l in info["log"] if "재생 시작" in l]) == 3
          and info["state"]["done"] is True, info["log"][-1:])
    check("원본 합성 음성 3개 보존(0바이트 없음)",
          all(l["bytes"] > 10000 and l["type"] == "audio/wav" for l in info["lines"]),
          [l["bytes"] for l in info["lines"]])
    check("늦은 자막도 로그에 '제자리에만 붙임'으로 기록",
          any("늦게 도착" in l and "l2" in l and "붙임" in l for l in info["log"]),
          [l for l in info["log"] if "늦게" in l])
    check("늦은 자막 흐름 런타임·콘솔 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- C-2. 누락 + 계속 말하기
def run_missing(browser):
    ctx, page, errors, cerrs, _ = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(800)
    page.click("#expBtn")
    page.wait_for_timeout(400)
    page.click("#expSimRow [data-sim='missing']")
    page.click("#expPlay")
    page.wait_for_timeout(2200)                      # 두 번째 마디쯤
    mid = page.evaluate("__DOHA.tiki.state()")
    timeline_mid = page.evaluate("__DOHA.tiki.timeline()")
    page.fill("#expSay", "그럼 귀는 누가 달아 준 거야?")
    page.press("#expSay", "Enter")
    page.wait_for_timeout(300)
    after_say = page.evaluate("__DOHA.tiki.state()")
    timeline_after = page.evaluate("__DOHA.tiki.timeline()")
    page.screenshot(path=os.path.join(SHOTS, "06-exp-missing-during.png"))
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    page.wait_for_timeout(200)
    info = {
        "mid": mid, "after_say": after_say,
        "timeline_mid": timeline_mid, "timeline_after": timeline_after,
        "state": page.evaluate("__DOHA.tiki.state()"),
        "subs": page.evaluate("__DOHA.tiki.subs()"),
        "extras": page.evaluate("__DOHA.tiki.extras()"),
        "log": page.evaluate("__DOHA.tiki.log()"),
        "lines": page.evaluate("__DOHA.tiki.lines()"),
        "cap": page.inner_text("#expCapText"),
        "capTag": page.inner_text("#expCapTag"),
        "cards": page.evaluate("""() => Array.prototype.map.call(document.querySelectorAll('.exp-line'), li => ({
            id: li.getAttribute('data-line'), txt: li.querySelector('.txt').textContent,
            st: li.querySelector('.st').textContent, audio: !!li.querySelector('audio').getAttribute('src')}))"""),
        "extras_ui": page.inner_text("#expExtras"),
    }
    page.locator("#expLines").scroll_into_view_if_needed()
    page.wait_for_timeout(250)
    page.screenshot(path=os.path.join(SHOTS, "07-exp-missing-lines.png"))
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_missing(info):
    subs = {s["id"]: s for s in info["subs"]}
    check("누락 시나리오 — 세 번째 마디 자막이 오지 않음", subs["l3"]["status"] == "missing", subs["l3"])
    check("첫·두 번째 마디 자막은 정상", subs["l1"]["status"] == "shown" and subs["l2"]["status"] == "shown",
          [subs["l1"], subs["l2"]])
    check("무대·카드에 '자막 없음 · 음성은 그대로' 표시",
          "자막이 오지 않았어요" in info["cap"] and "자막 누락" in info["capTag"]
          and [c for c in info["cards"] if c["id"] == "l3"][0]["st"] == "자막 누락",
          {"cap": info["cap"], "tag": info["capTag"]})
    l3 = [l for l in info["lines"] if l["id"] == "l3"][0]
    check("자막이 빠져도 세 번째 합성 음성은 보관·재생 가능",
          l3["bytes"] > 10000 and l3["type"] == "audio/wav"
          and [c for c in info["cards"] if c["id"] == "l3"][0]["audio"], l3)
    check("자막 누락에도 세 마디가 끝까지 재생(대화 중단 없음)",
          info["state"]["done"] is True and len([l for l in info["log"] if "재생 시작" in l]) == 3,
          info["state"])
    check("재생 중에 말을 더할 수 있음(재생 중이었음)", info["mid"]["playing"] is True, info["mid"])
    check("추가한 마디가 기록됨(재생 중에 추가)",
          len(info["extras"]) == 1 and info["extras"][0]["when"] == "재생 중에 추가"
          and "귀는 누가" in info["extras_ui"], info["extras"])
    check("추가한 마디가 세 마디 재생 순서를 바꾸지 않음",
          info["timeline_after"] == info["timeline_mid"] and info["after_say"]["playing"] is True,
          {"mid": info["timeline_mid"], "after": info["timeline_after"]})
    check("누락 흐름 런타임·콘솔 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- B. 그림체·분위기
def run_style(browser):
    ctx, page, errors, cerrs, _ = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(800)
    page.click("#expBtn")
    page.wait_for_timeout(400)
    before = page.evaluate("__DOHA.tiki.frames()")
    page.click("#expStyleRow .st-card:nth-child(8)")          # 픽셀 월드
    page.wait_for_timeout(500)
    pixel = page.evaluate("__DOHA.tiki.frames()")
    pixel_now = page.inner_text("#expStyleNow")
    page.screenshot(path=os.path.join(SHOTS, "08-exp-style-pixel.png"))
    page.evaluate("document.querySelector('#s-exp .exp-scroll').scrollTop=0")
    page.wait_for_timeout(250)
    page.screenshot(path=os.path.join(SHOTS, "08b-exp-style-pixel-stage.png"))
    page.click("#expStyleRow .st-card:nth-child(2)")          # 동화책(질감 오버레이)
    page.wait_for_timeout(400)
    story = page.evaluate("__DOHA.tiki.frames()")
    tex = page.evaluate("""() => Array.prototype.map.call(document.querySelectorAll('.exp-frame .stage-tex'),
        e => ({cls: e.className, opacity: getComputedStyle(e).opacity}))""")
    page.click("#expMoodRow [data-mood='dusk']")
    page.wait_for_timeout(300)
    mood = {"attr": page.evaluate("__DOHA.tiki.moodAttr()"),
            "filter": page.evaluate("getComputedStyle(document.querySelector('.exp-frame.on img')).filter")}
    page.screenshot(path=os.path.join(SHOTS, "09-exp-mood-dusk.png"))
    # 재생 중 그림체 변경 — 재생이 끊기거나 순서가 바뀌지 않아야 한다
    page.click("#expPlay")
    page.wait_for_timeout(1200)
    tl_before = page.evaluate("__DOHA.tiki.timeline()")
    page.click("#expStyleRow .st-card:nth-child(4)")          # 블록 월드
    page.wait_for_timeout(200)
    mid = page.evaluate("__DOHA.tiki.state()")
    tl_after = page.evaluate("__DOHA.tiki.timeline()")
    frames_mid = page.evaluate("__DOHA.tiki.frames()")
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    log = page.evaluate("__DOHA.tiki.log()")
    info = {
        "before": before, "pixel": pixel, "pixel_now": pixel_now, "story": story, "tex": tex,
        "mood": mood, "mid": mid, "tl_before": tl_before, "tl_after": tl_after,
        "frames_mid": frames_mid, "log": log, "subs": page.evaluate("__DOHA.tiki.subs()"),
        "errors": errors, "console_errors": cerrs,
    }
    ctx.close()
    return info


def check_style(info):
    check("그림체를 바꾸면 세 장면 모두 data-style 반영",
          [f["style"] for f in info["pixel"]] == ["pixel"] * 3, [f["style"] for f in info["pixel"]])
    check("픽셀 그림체에서 그림 자체가 바뀜(변환 이미지)",
          all(f["src"] != b["src"] for f, b in zip(info["pixel"], info["before"]))
          and all(f["src"].startswith("data:image/") for f in info["pixel"]),
          {"before": info["before"][0]["src"][:32], "pixel": info["pixel"][0]["src"][:32]})
    check("바꾼 그림체가 화면 문구에 표시", "픽셀 월드" in info["pixel_now"], info["pixel_now"])
    check("질감 그림체(동화책)도 장면에 반영", all("tex-storybook" in t["cls"] and float(t["opacity"]) > 0
                                          for t in info["tex"]), info["tex"])
    check("분위기(노을)가 장면에 반영", info["mood"]["attr"] == "dusk" and "sepia" in info["mood"]["filter"],
          info["mood"])
    check("재생 중 그림체 변경해도 재생 계속·타임라인 그대로",
          info["mid"]["playing"] is True and info["tl_after"] == info["tl_before"]
          and [f["style"] for f in info["frames_mid"]] == ["block"] * 3, info["mid"])
    check("재생 중 변경 뒤에도 세 마디 완료", any("재생 완료" in l for l in info["log"]), info["log"][-1:])
    check("그림체·분위기 흐름 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- E. v0.1.4 호환
def run_compat(browser):
    ctx, page, errors, cerrs, _ = new_page(browser)
    page.on("dialog", lambda d: d.accept())
    page.goto(BASE + "/legacy/")
    page.wait_for_timeout(900)
    info = {"legacy_version": page.evaluate("__DOHA.version()"),
            "legacy_has_exp": page.evaluate("!!document.querySelector('#s-exp')"),
            "legacy_brand": page.inner_text(".brand-sub")}
    page.click("#startBtn")
    page.wait_for_timeout(500)
    page.fill("#sayInput", "가상의 v0.1.4 이야기 — 달에 간 공룡")
    page.press("#sayInput", "Enter")
    page.wait_for_timeout(500)
    page.click("#micBtn")
    page.wait_for_function("__DOHA.mic().on")
    page.wait_for_timeout(1300)
    page.click("#micBtn")
    page.wait_for_function("!__DOHA.mic().on && !__DOHA.mic().stopping")
    page.wait_for_timeout(400)
    page.click("#endBtn")
    page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=20000)
    page.wait_for_timeout(700)
    album = page.evaluate("__DOHA.album()")
    info["created"] = [{"id": w["id"], "no": w["no"], "title": w["title"],
                        "scenes": len(w.get("scenes") or []),
                        "clips": sum(len(s.get("clipIds") or []) for s in (w.get("scenes") or []))}
                       for w in album]
    page.screenshot(path=os.path.join(SHOTS, "10-legacy-created.png"))
    # 같은 오리진의 v0.2 검토본으로 이동 — IndexedDB 기록이 그대로 보여야 한다
    page.goto(BASE + "/")
    page.wait_for_timeout(1200)
    page.click("#albumBtn")
    page.wait_for_timeout(900)
    info["album_in_new"] = page.evaluate("__DOHA.album().length")
    no = info["created"][0]["no"] if info["created"] else 0
    card = page.locator("#panel-album .al-card-wrap").filter(has_text="No.%03d" % no).first
    info["card_found"] = card.count() > 0
    card.locator(".al-card").first.click()
    page.wait_for_function("__DOHA.state.screen==='movie'", timeout=10000)
    page.wait_for_timeout(900)
    info["movie"] = page.evaluate("""() => ({
        title: document.querySelector('#introTitle').textContent,
        frames: document.querySelectorAll('#player .frame').length,
        audioCards: document.querySelectorAll('#originalAudio audio').length,
        tc: document.querySelector('#mvTc').textContent,
        one: document.querySelector('#oneLine').textContent})""")
    page.wait_for_timeout(1200)     # v0.1.4 클립 Blob 복원 대기
    info["movie_after_load"] = page.evaluate(
        "({audioCards: document.querySelectorAll('#originalAudio audio').length})")
    page.click("#playBtn")
    page.wait_for_timeout(2600)
    info["playing"] = {"tc": page.inner_text("#mvTc"),
                       "progress": page.evaluate("document.querySelector('#mvProg').style.width"),
                       "icon": page.evaluate("document.querySelector('#playIcon path').getAttribute('d')")}
    page.screenshot(path=os.path.join(SHOTS, "11-legacy-opened-in-v02.png"))
    page.click("#mvAlbumBtn")
    page.wait_for_timeout(800)
    with page.expect_download() as dl:
        card.get_by_text("기록 + 음성 JSON").click()
    path = dl.value.path()
    data = json.loads(open(path, encoding="utf-8").read())
    info["export"] = {"formatVersion": data.get("formatVersion"), "format": data.get("format"),
                      "works": len(data.get("works") or []),
                      "manifest": data.get("manifest"),
                      "id": ((data.get("works") or [{}])[0].get("record") or {}).get("id"),
                      "audio": len(((data.get("works") or [{}])[0].get("audio") or [])),
                      "audioPrefix": ((((data.get("works") or [{}])[0].get("audio") or [{}])[0] or {})
                                      .get("dataUrl") or "")[:22],
                      "note": data.get("note", "")[:40]}
    info["toast"] = page.locator("#toast").text_content() or ""
    # 새로고침 뒤에도 그대로 열리는지
    page.goto(BASE + "/")
    page.wait_for_timeout(1100)
    page.click("#albumBtn")
    page.wait_for_timeout(800)
    info["album_after_reload"] = page.evaluate("__DOHA.album().length")
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_compat(info):
    check("v0.1.4 빌드가 /legacy/에서 실제로 열림(기준 버전 확인)",
          info["legacy_version"] == "0.1.4" and not info["legacy_has_exp"],
          {"version": info["legacy_version"], "has_exp": info["legacy_has_exp"]})
    created = info["created"]
    check("v0.1.4에서 가상 작품 1편 저장", len(created) == 1 and created[0]["clips"] >= 1,
          created)
    check("v0.2 검토본 앨범에서 그 기록이 보임", info["album_in_new"] == 1 and info["card_found"],
          {"album": info["album_in_new"], "card": info["card_found"]})
    m = info["movie"]
    check("v0.1.4 작품이 v0.2에서 그대로 열림(장면·한 줄)",
          m["frames"] == created[0]["scenes"] and "달에 간 공룡" in m["one"], m)
    check("원본 목소리 카드가 그대로 복원", m["audioCards"] >= 1 and info["movie_after_load"]["audioCards"] >= 1,
          {"now": m["audioCards"], "after": info["movie_after_load"]})
    check("v0.2에서도 ▶ 재생이 실제로 진행", info["playing"]["progress"] not in ("", "0%")
          and info["playing"]["tc"] != m["tc"], {"before": m["tc"], "after": info["playing"]})
    ex = info["export"]
    check("v0.1.4 작품 내보내기 파일 정상 생성", ex["format"] == "doha.work/1" and ex["works"] == 1,
          {"format": ex["format"], "works": ex["works"]})
    check("내보낸 파일에 같은 작품 id", ex["id"] == created[0]["id"], {"export": ex["id"], "saved": created[0]["id"]})
    check("내보낸 파일에 원본 음성 포함", ex["audio"] >= 1 and ex["audioPrefix"].startswith("data:audio"),
          {"audio": ex["audio"], "prefix": ex["audioPrefix"]})
    check("내보내기 manifest에 음성 누락 없음", (ex["manifest"] or {}).get("missingAudioClipCount") == 0,
          ex["manifest"])
    check("새로고침 뒤에도 기록 유지", info["album_after_reload"] == 1, info["album_after_reload"])
    check("호환 흐름 런타임·콘솔 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- G. 휴대폰 화면
def run_phone(browser):
    ctx, page, errors, cerrs, _ = new_page(browser, 390, 844, True)
    page.goto(BASE + "/")
    page.wait_for_timeout(900)
    page.click("#expBtn")
    page.wait_for_timeout(500)
    info = {"overflow": page.evaluate(
        "({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,"
        "appSL:document.querySelector('#app').scrollLeft,"
        "expSL:document.querySelector('#s-exp .exp-scroll').scrollLeft,"
        "simRight:Math.round(document.querySelector('#expSimRow button:last-child').getBoundingClientRect().right),"
        "vw:window.innerWidth})")}
    page.screenshot(path=os.path.join(SHOTS, "12-exp-phone-idle.png"))
    page.click("#expPlay")
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(SHOTS, "13-exp-phone-playing.png"))
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    info["done"] = page.evaluate("__DOHA.tiki.state()")
    info["cap"] = page.inner_text("#expCapText")
    page.locator("#expLines").scroll_into_view_if_needed()
    page.wait_for_timeout(250)
    page.screenshot(path=os.path.join(SHOTS, "14-exp-phone-lines.png"))
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_phone(info):
    ov = info["overflow"]
    check("[phone] 실험 화면 가로 밀림 없음(문서·#app·가로스크롤 0)",
          ov["sw"] == ov["cw"] and ov["appSL"] == 0 and ov["expSL"] == 0, ov)
    check("[phone] 시뮬레이션 버튼이 화면 안에 들어옴", ov["simRight"] <= ov["vw"], ov)
    check("[phone] 재생 완료·마지막 자막 표시", info["done"]["done"] and info["cap"] == L3, info["cap"])
    check("[phone] 런타임·콘솔 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


def main():
    os.makedirs(SHOTS, exist_ok=True)
    static_checks()
    ok_legacy, legacy_detail = prepare_legacy()
    check("v0.1.4 원본 빌드 확보(커밋 %s, 실험 화면 없음)" % PORT_LEGACY_COMMIT, ok_legacy, legacy_detail)
    httpd = start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=FAKE)
            print("Chromium", browser.version, flush=True)
            print("--- A. 순서·끊김·모의 자막", flush=True)
            check_play(run_play(browser))
            print("--- C-1. 자막 늦게 도착", flush=True)
            check_late(run_late(browser))
            print("--- C-2. 자막 누락 + 재생 중 계속 말하기", flush=True)
            check_missing(run_missing(browser))
            print("--- B. 그림체·분위기 반영", flush=True)
            check_style(run_style(browser))
            print("--- E. v0.1.4 작품 호환", flush=True)
            check_compat(run_compat(browser))
            print("--- G. 휴대폰", flush=True)
            check_phone(run_phone(browser))
            browser.close()
    finally:
        httpd.shutdown()

    ok = all(c["ok"] for c in CHECKS)
    print("\n=== RESULT:", "ALL PASS" if ok else "FAILED", "=== (%d checks)" % len(CHECKS))
    print("screenshots:", SHOTS)
    print(json.dumps({"shots": sorted(os.listdir(SHOTS))}, ensure_ascii=False)[:1500])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
