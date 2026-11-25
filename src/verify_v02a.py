#!/usr/bin/env python3
"""PROJECT DOHA v0.2-A 검증 — 성인이 세 문장을 '한 번에 이어' 녹음하고 세 마디로 나눠 보관(검토용).

실제 아동 목소리·실제 대화·외부 API·유료 호출 없이, 브라우저 안에서만 확인한다.
(가짜 마이크 장치 + 브라우저가 만든 합성 음성. 저장소·스크린샷에 실제 아이 데이터 없음)

검증 항목
  A. AudioContext.resume() 보완 — resume 완료·실제 running 전에는 '재생 중'으로 바뀌지 않고,
     실패하면 '재생 준비 실패'로 남아 다시 누를 수 있는가 (지연·실패·재시도·중복 클릭)
  B. 한 번에 이어 녹음 — 한 덩어리 원본에서 세 마디를 나누고(조용한 구간), 원본을 자르지 않고 보관하는가
  C. 두 번째 모의 자막만 늦게 보내도 두 번째 마디에만 붙고, 마디 오디오·원본이 그대로인가
  D. 새로고침 뒤 — 두 번째 장면을 누르면 실제 두 번째 발화 구간이 재생되고,
     원본에는 세 마디가 순서대로 남아 있는가 (주파수 분석으로 발화 구간 확인)
  E. 실제 마이크 경로(가짜 장치) — 녹음 시작·끝·저장·재생이 되고 실패를 성공으로 꾸미지 않는가
  F. 휴대폰 390×844 가로 밀림·콘솔 에러 0
  G. 시연 스크린샷(downloads/doha-v0.2a-preview)

사용:
  python3 src/build.py && python3 src/check_build.py
  LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu python3 src/verify_v02a.py
"""
import functools
import http.server
import json
import os
import threading
import urllib.parse

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
SHOTS = "/workspace/downloads/doha-v0.2a-preview"
PORT = 8797
BASE = "http://127.0.0.1:%d" % PORT
CHECKS = []
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
L1, L2, L3 = "달이 치즈야", "그럼 한입 먹어도 돼?", "안 돼, 그건 달의 귀야!"
PITCH = {"l1": 440, "l2": 660, "l3": 880}   # 예시 음성(합성)에서 마디를 표시하는 높이


def check(name, ok, detail=""):
    CHECKS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + ("  · " + str(detail)[:300] if detail != "" else ""))


# ---------------------------------------------------------------- 정적 검사
def static_checks():
    src = open(SRC, encoding="utf-8").read()
    check("기준 버전 meta = 0.1.4 유지(v0.1.4 동작 그대로)", 'name="doha-version" content="0.1.4"' in src)
    check("실험 표식 meta = 0.2-a", 'name="doha-experiment-a" content="0.2-a"' in src)
    check("홈에 v0.2-A 진입 버튼", 'id="expABtn"' in src and "v0.2-A 한 번에 이어 녹음" in src)
    check("A 화면 존재(#s-expa, 한 번에 이어 녹음)",
          'id="s-expa"' in src and "한 번에 이어 녹음 · 세 문장" in src)
    check("안내문: 한 번에 이어·조용한 구간·원본 미절단·모의 자막·외부 API 없음",
          all(k in src for k in ("한 번에 이어", "조용한 구간", "원본 녹음은 자르지 않고",
                                 "모의 자막", "외부 API·유료 호출")) )
    check("세 문장 대본 그대로", all(t in src for t in (L1, L2, L3)))
    check("정직성 라벨(예시 합성 음성·성인 실제 녹음·경계 자동 추정)",
          all(k in src for k in ("예시 합성 음성", "성인 실제 녹음", "경계 자동 추정")))
    check("저장은 별도 DB(doha-exp-a) · 기존 아이 기록 스키마 무변경",
          'var EXPA_DB="doha-exp-a"' in src and 'DB_NAME="doha-universe", DB_VER=1' in src)
    check("resume 대기 코드(tikiResume·phase starting·재생 준비 실패) 존재",
          all(k in src for k in ("function tikiResume", 'TIKI.phase="starting"', "재생 준비 실패",
                                 "실제 실행 상태가 된 뒤에")))
    check("재시도 안내 요소(#expRetry) · 다시 시도 버튼 문구",
          'id="expRetry"' in src and "▶ 다시 시도 (합성 음성)" in src)
    check("장면 1/2/3 다시 듣기 버튼 생성 코드", 'data-act","play' in src or 'setAttribute("data-act","play' in src)
    check("외부 API·fetch·XHR 없음", "fetch(" not in src and "XMLHttpRequest" not in src
          and "api.openai" not in src.lower() and "openai" not in src.lower())


# ---------------------------------------------------------------- 로컬 서버
def make_handler():
    class H(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            p = urllib.parse.urlparse(path).path
            return os.path.join(ROOT, p.lstrip("/") or "index.html")

        def log_message(self, *a):
            pass
    return functools.partial(H, directory=ROOT)


def start_server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def new_page(browser, w=1180, h=900, mobile=False):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1,
                              is_mobile=mobile, has_touch=mobile,
                              permissions=["microphone"], accept_downloads=True)
    page = ctx.new_page()
    errors, cerrs, reqs = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: reqs.append(r.url))
    page.on("dialog", lambda d: d.accept())
    return ctx, page, errors, cerrs, reqs


# 가짜 오디오 컨텍스트: resume() 이 늦게 끝나거나 실패하는 Safari 상황을 흉내 낸다.
FAKE_AC = """
(opts) => {
  const Real = window.AudioContext || window.webkitAudioContext;
  const M = window.__ACMODE = {delay: opts.delay || 0, fail: !!opts.fail, resumed: false, calls: 0};
  let realGet = null;
  (function findGet(p) {                 // 실제 state 게터(우리 가짜 게터는 건너뛴다)
    while (p && !realGet) {
      const d = Object.getOwnPropertyDescriptor(p, "state");
      if (d && d.get) realGet = d.get;
      p = Object.getPrototypeOf(p);
    }
  })(Real.prototype);
  class FakeAC extends Real {
    get state() { return M.resumed ? (realGet ? realGet.call(this) : "running") : "suspended"; }
    resume() {
      M.calls++;
      if (M.fail) return new Promise((_, rej) => setTimeout(() => rej(new Error("blocked")), 120));
      return new Promise((res, rej) => setTimeout(() => {
        Real.prototype.resume.call(this).then(() => { M.resumed = true; res(); }, rej);
      }, M.delay));
    }
  }
  window.AudioContext = FakeAC;
  window.webkitAudioContext = FakeAC;
  return true;
}
"""

TONES = """
async ([url, from, to]) => {
  const r = await fetch(url);
  const b = await r.arrayBuffer();
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const audio = await new Promise((res, rej) => ac.decodeAudioData(b.slice(0), res, rej));
  const d = audio.getChannelData(0), sr = audio.sampleRate;
  const s = Math.max(0, Math.floor(((from || 0) + 0.05) * sr));
  const e = Math.min(d.length, Math.floor((to || audio.duration) * sr));
  const seg = d.subarray(s, e);
  const N = Math.min(4096, seg.length);
  let bi = 0, bE = -1;                       /* 가장 소리가 큰 4096 샘플 창에서 잰다(쉼 구간 회피) */
  for (let off = 0; off + N <= seg.length; off += 256) {
    let en = 0;
    for (let i = 0; i < N; i++) en += seg[off + i] * seg[off + i];
    if (en > bE) { bE = en; bi = off; }
  }
  const win = seg.subarray(bi, bi + N);
  let best = 0, bv = -1;
  for (let f = 300; f <= 1000; f += 5) {
    const w = 2 * Math.PI * f / sr, c = 2 * Math.cos(w);
    let s1 = 0, s2 = 0;
    for (let i = 0; i < win.length; i++) { const s0 = win[i] + c * s1 - s2; s2 = s1; s1 = s0; }
    const p = s1 * s1 + s2 * s2 - c * s1 * s2;
    if (p > bv) { bv = p; best = f; }
  }
  try { ac.close(); } catch (e2) {}
  return {peak: best, power: Math.round(bv), dur: Math.round(audio.duration * 1000) / 1000,
          sr: sr, at: Math.round((s + bi) / sr * 1000) / 1000};
}
"""


def tone(page, url, a=0.0, b=0.0):
    return page.evaluate(TONES, [url, a, b])


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


# ---------------------------------------------------------------- A-1. resume 지연
def run_resume(browser):
    ctx, page, errors, cerrs, reqs = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(800)
    page.screenshot(path=os.path.join(SHOTS, "01-home-a-button.png"))
    info = {"homeButtons": page.evaluate(
        "Array.prototype.map.call(document.querySelectorAll('.home-cta .btn'), e=>e.textContent.trim())")}
    page.click("#expBtn")                     # 재생 경로가 있는 실험 화면
    page.wait_for_timeout(400)
    page.evaluate(FAKE_AC, {"delay": 900})
    page.click("#expPlay")
    page.wait_for_timeout(300)
    info["during"] = page.evaluate("__DOHA.tiki.state()")
    page.screenshot(path=os.path.join(SHOTS, "03-exp-resume-waiting.png"))
    page.wait_for_function("__DOHA.tiki.state().phase === 'playing'", timeout=8000)
    info["after"] = page.evaluate("__DOHA.tiki.state()")
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(SHOTS, "03b-exp-resume-playing.png"))
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    info["end"] = page.evaluate("__DOHA.tiki.state()")
    info["log"] = page.evaluate("__DOHA.tiki.log()")
    info["acmode"] = page.evaluate("window.__ACMODE")
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_resume(info):
    check("홈에 v0.2와 v0.2-A 진입 버튼이 함께 있음",
          any("v0.2 A" in t or "v0.2-A" in t for t in info["homeButtons"])
          and any("티키타카" in t for t in info["homeButtons"]), info["homeButtons"])
    d = info["during"]
    check("resume 대기 중에는 '재생 중'이 아니라 '소리 준비 중…'", d["stateLabel"] == "소리 준비 중…", d)
    check("resume 대기 중 playing=false (무음인데 재생 중으로 두지 않음)",
          d["playing"] is False and d["phase"] == "starting", d)
    a = info["after"]
    check("resume 완료 뒤에만 '재생 중'", a["stateLabel"] == "재생 중" and a["playing"] is True, a)
    check("재개 호출이 실제로 일어남(resume 호출 1회 이상, resumed=true)",
          info["acmode"]["calls"] >= 1 and info["acmode"]["resumed"] is True, info["acmode"])
    check("재개 뒤 세 마디 끝까지 재생", info["end"]["done"] is True and info["end"]["phase"] == "done", info["end"])
    check("로그에 '실제 실행 상태를 확인한 뒤' 시작했다는 기록",
          any("실제 실행 상태를 확인한 뒤" in l for l in info["log"]),
          [l for l in info["log"] if "오디오 상태" in l][:2])
    check("지연 시나리오 에러 0", not info["errors"] and not info["console_errors"], info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- A-2. resume 실패·재시도
def run_resume_fail(browser):
    ctx, page, errors, cerrs, _ = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(800)
    page.click("#expBtn")
    page.wait_for_timeout(400)
    page.evaluate(FAKE_AC, {"fail": True})
    page.click("#expPlay")
    page.wait_for_timeout(600)
    info = {"failed": page.evaluate("__DOHA.tiki.state()"),
            "playBtn": page.inner_text("#expPlay"),
            "log": page.evaluate("__DOHA.tiki.log()")}
    page.screenshot(path=os.path.join(SHOTS, "04-a-resume-failed.png"))
    page.evaluate("window.__ACMODE.fail = false; window.__ACMODE.delay = 200;")
    page.click("#expPlay")
    page.wait_for_timeout(500)
    info["retried"] = page.evaluate("__DOHA.tiki.state()")
    page.wait_for_function("__DOHA.tiki.state().done === true", timeout=20000)
    info["end"] = page.evaluate("__DOHA.tiki.state()")
    info["log2"] = page.evaluate("__DOHA.tiki.log()")
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_resume_fail(info):
    f = info["failed"]
    check("resume 실패 시 '재생 준비 실패'", f["stateLabel"] == "재생 준비 실패" and f["phase"] == "error", f)
    check("resume 실패 시 재생 중으로 표시하지 않음", f["playing"] is False, f)
    check("실패 안내문이 화면에 남음(다시 누를 수 있음)", f["retryVisible"] and "다시 시도" in f["retryText"], f["retryText"])
    check("재시도 버튼 문구로 바뀜", "다시 시도" in info["playBtn"], info["playBtn"])
    check("실패 이유를 로그에 남김", any("재개 실패" in l for l in info["log"]), info["log"][-2:])
    r = info["retried"]
    check("다시 눌러 재개되면 '재생 중'", r["stateLabel"] == "재생 중" and r["playing"] is True, r)
    check("재시도 뒤 세 마디 완주·안내문 사라짐",
          info["end"]["done"] is True and info["end"]["retryVisible"] is False, info["end"])
    check("실패/재시도 시나리오 에러 0", not info["errors"] and not info["console_errors"],
          info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- B·C·D. 일괄 이어 녹음 + 늦은 자막 + 새로고침
SAMPLER = """
window.__A_SAMPLES = [];
window.__A_IV = setInterval(function(){
  var cards = Array.prototype.map.call(document.querySelectorAll('#expaTakes .expa-line'), function(li){
    return {id: li.getAttribute('data-line'), txt: (li.querySelector('.txt')||{}).textContent,
            st: (li.querySelector('.st')||{}).textContent};
  });
  var s = (window.__DOHA && __DOHA.expa) ? __DOHA.expa.state() : {};
  __A_SAMPLES.push({playing: !!s.playing, seg: (s.cur||{}).idx, cards: cards,
                    player: (s.player||{}).currentTime});
}, 60);
"""


def run_batch(browser):
    ctx, page, errors, cerrs, reqs = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(900)
    page.click("#expABtn")
    page.wait_for_timeout(400)
    page.evaluate("window.__A_SCRIPT = Array.prototype.map.call(document.querySelectorAll('#expaScript li .t'), e=>e.textContent)")
    info0 = {"screen": page.evaluate("__DOHA.state.screen"),
             "labels": page.evaluate("__DOHA.expa.labels()"),
             "script": page.evaluate("window.__A_SCRIPT"),
             "cmp": page.evaluate("__DOHA.expa.version")}
    page.screenshot(path=os.path.join(SHOTS, "02-a-idle.png"))
    page.click("#expaDemoBtn")
    page.wait_for_function("__DOHA.expa.state().takes === 1", timeout=25000)
    page.wait_for_timeout(400)
    takes = page.evaluate("__DOHA.expa.takes()")
    take = takes[0]
    info = {"entry": info0, "take": take, "log": page.evaluate("__DOHA.expa.log()"),
            "ui": page.evaluate("__DOHA.expa.labels()"),
            "orig": wav_info(page, take["origUrl"])}
    info["segs"] = [wav_info(page, l["segUrl"]) for l in take["lines"]]
    info["tones"] = [tone(page, l["segUrl"]) for l in take["lines"]]
    page.screenshot(path=os.path.join(SHOTS, "05-a-batch-saved.png"))
    # 원본의 각 구간에 실제로 그 발화가 있는가(순서 확인)
    info["orig_tones"] = [tone(page, take["origUrl"], l["start"] + 0.2, l["end"])
                          for l in take["lines"]]
    # 늦은 두 번째 자막 실험
    page.click("#expaLateBtn")
    info["late_label"] = page.inner_text("#expaLateBtn")
    page.evaluate(SAMPLER)
    page.click('[data-take="%s"] [data-act="playall"]' % take["id"])
    page.wait_for_timeout(1400)
    info["mid"] = page.evaluate("__DOHA.expa.state()")
    page.screenshot(path=os.path.join(SHOTS, "06-a-playing-all.png"))
    page.wait_for_function("__DOHA.expa.state().playing === false", timeout=30000)
    page.wait_for_timeout(300)
    page.evaluate("clearInterval(window.__A_IV)")
    info["samples"] = page.evaluate("window.__A_SAMPLES")
    info["subs"] = page.evaluate("__DOHA.expa.takes()[0].lines.map(l=>l.sub)")
    info["after_sub"] = page.evaluate("__DOHA.expa.takes()")[0]
    info["log2"] = page.evaluate("__DOHA.expa.log()")
    page.locator("#expaTakes").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS, "07-a-late-subtitle.png"))
    # 새로고침 → 저장 유지
    page.reload()
    page.wait_for_timeout(1200)
    page.click("#expABtn")
    page.wait_for_timeout(900)
    info["reload_takes"] = page.evaluate("__DOHA.expa.takes()")
    info["reload_labels"] = page.evaluate("__DOHA.expa.labels()")
    page.screenshot(path=os.path.join(SHOTS, "08-a-after-reload.png"))
    rt = info["reload_takes"][0]
    # 두 번째 장면 재생
    page.click('[data-take="%s"] [data-act="play2"]' % rt["id"])
    page.wait_for_timeout(500)
    info["play2_start"] = page.evaluate("__DOHA.expa.state().player")
    page.wait_for_timeout(900)
    info["play2_mid"] = page.evaluate("__DOHA.expa.state().player")
    page.screenshot(path=os.path.join(SHOTS, "09-a-scene2-after-reload.png"))
    page.wait_for_timeout(2200)
    info["play2_end"] = page.evaluate("__DOHA.expa.state().player")
    info["play2_now"] = page.inner_text("#expaNow")
    info["play2_subs"] = page.evaluate("__DOHA.expa.takes()[0].lines.map(l=>l.sub)")
    # 두 번째 마디 WAV·원본 주파수 재확인 (새로고침 뒤에도 같은 오디오인지)
    info["reload_tones"] = [tone(page, l["segUrl"]) for l in rt["lines"]]
    info["reload_orig_tones"] = [tone(page, rt["origUrl"], l["start"] + 0.2, l["end"])
                                 for l in rt["lines"]]
    info["reload_orig"] = wav_info(page, rt["origUrl"])
    info["dl"] = page.get_attribute('[data-take="%s"] [data-act="dl"]' % rt["id"], "href")
    info["external_requests"] = [u for u in reqs if u.startswith("http") and not u.startswith(BASE)]
    # 지우기: 녹음을 하나 더 만든 뒤 그 하나만 지운다(다른 기록 보존 확인)
    page.click("#expaDemoBtn")
    page.wait_for_function("__DOHA.expa.state().takes === 2", timeout=25000)
    info["two"] = [t["id"] for t in page.evaluate("__DOHA.expa.takes()")]
    page.click('[data-take="%s"] [data-act="delete"]' % info["two"][0])
    page.wait_for_timeout(1200)
    info["after_delete"] = [t["id"] for t in page.evaluate("__DOHA.expa.takes()")]
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_batch(info):
    t = info["take"]
    e = info["entry"]
    check("A 화면 진입·실험 버전 0.2-a", e["screen"] == "expa" and e["cmp"] == "0.2-a", e["cmp"])
    check("대본 세 문장이 화면에 그대로", e["script"] == [L1, L2, L3], e["script"])
    check("A 화면 정직성 표시(이 브라우저에만·모의 자막)",
          "이 브라우저에만" in " ".join(e["labels"]["flag"]) and "모의 자막" in e["labels"]["notice"],
          e["labels"]["flag"])
    check("한 번에 이어 녹음 1건이 저장됨(원본 1개)", t["segCount"] == 3 and t["source"] == "demo", t["source"])
    check("세 마디가 l1→l2→l3 순서", [l["id"] for l in t["lines"]] == ["l1", "l2", "l3"], [l["id"] for l in t["lines"]])
    starts = [l["start"] for l in t["lines"]]
    ends = [l["end"] for l in t["lines"]]
    check("마디 구간이 겹치지 않고 이어짐", all(abs(ends[i] - starts[i + 1]) < 0.02 for i in range(2))
          and all(ends[i] > starts[i] for i in range(3)), {"starts": starts, "ends": ends})
    check("경계를 '조용한 구간'으로 찾음", all(l["method"] == "silence" for l in t["lines"]),
          [l["method"] for l in t["lines"]])
    check("원본은 자르지 않고 한 덩어리로 보관(WAV·길이·용량)",
          info["orig"]["riff"] == "RIFF" and info["orig"]["bytes"] > 200000
          and abs(info["orig"]["dur"] - (t["dur"])) < 0.05, info["orig"])
    check("마디는 원본에서 잘라 만든 WAV 사본(3개·규격 일치)",
          all(s["riff"] == "RIFF" and s["wave"] == "WAVE" and s["ch"] == 1 and s["bits"] == 16 for s in info["segs"]),
          [s["bytes"] for s in info["segs"]])
    check("마디 길이 합 + 쉼 = 원본 길이",
          abs(sum(l["dur"] for l in t["lines"]) - t["dur"]) < 0.35,
          {"sum": round(sum(l["dur"] for l in t["lines"]), 2), "orig": t["dur"]})
    check("각 마디 오디오가 제 마디 표시음과 일치(±20Hz)",
          all(abs(x["peak"] - PITCH[l["id"]]) <= 20 for x, l in zip(info["tones"], t["lines"])),
          [(x["peak"], PITCH[l["id"]]) for x, l in zip(info["tones"], t["lines"])])
    check("원본의 세 구간에 세 마디가 순서대로 들어 있음(±20Hz)",
          all(abs(x["peak"] - PITCH[l["id"]]) <= 20 for x, l in zip(info["orig_tones"], t["lines"])),
          [(x["peak"], PITCH[l["id"]]) for x, l in zip(info["orig_tones"], t["lines"])])
    check("화면에 마디 카드 3개·저장 안내", info["ui"]["lineCards"] == 3 and info["ui"]["takeCards"] == 1, info["ui"])
    check("늦은 자막 스위치가 켜짐으로 표시", "켜짐" in info["late_label"], info["late_label"])
    check("외부 요청 0건", not info["external_requests"], info["external_requests"][:3])


def check_late(info):
    subs = {s["text"]: s for s in info["subs"]}
    check("첫·세 번째 자막은 제자리 도착",
          info["subs"][0]["status"] == "shown" and info["subs"][2]["status"] == "shown", info["subs"])
    s2 = info["subs"][1]
    check("두 번째 자막만 늦게 도착(status=late, during=l3)",
          s2["status"] == "late" and s2["during"] == "l3", s2)
    check("늦은 자막도 두 번째 마디 문장 그대로", s2["text"] == L2 and s2["during"] == "l3", s2)
    during_l3 = [s for s in info["samples"] if s["seg"] == 2]
    l3_cards = [c for s in during_l3 for c in s["cards"] if c["id"] == "l3"]
    l2_cards = [c for s in during_l3 for c in s["cards"] if c["id"] == "l2"]
    check("세 번째 마디가 흐르는 동안 세 번째 카드에 두 번째 문장이 붙지 않음",
          bool(l3_cards) and all(L2 not in (c["txt"] or "") for c in l3_cards), {"n": len(l3_cards)})
    check("세 번째 마디가 흐르는 동안 두 번째 카드는 '자막 대기'로 남아 있다가 늦게 도착",
          any((c["txt"] or "") == "자막 대기 중" for c in l2_cards)
          and any(c["st"] == "늦게 도착" for c in l2_cards),
          {"pending": sum(1 for c in l2_cards if (c["txt"] or "") == "자막 대기 중"),
           "late": sum(1 for c in l2_cards if c["st"] == "늦게 도착")})
    before = {l["id"]: (l["start"], l["end"], l["dur"], l["segBytes"]) for l in info["take"]["lines"]}
    after = {l["id"]: (l["start"], l["end"], l["dur"], l["segBytes"]) for l in info["after_sub"]["lines"]}
    check("늦은 자막이 마디 구간·오디오를 바꾸지 않음", before == after, {"before": before, "after": after})
    check("전체 이어 듣기가 세 마디를 모두 재생",
          sum(1 for l in info["log2"] if "모의 자막 도착" in l) >= 2
          and len([s for s in info["samples"] if s["seg"] is not None]) > 20,
          len(info["samples"]))
    check("자막 상태가 저장됨(로그에 저장 확인)", any("자막 상태 저장" in l and "저장 확인" in l for l in info["log2"]),
          [l for l in info["log2"] if "자막 상태" in l][:2])


def check_reload(info):
    rt = info["reload_takes"]
    check("새로고침 뒤에도 녹음 1건이 남아 있음", len(rt) == 1, len(rt))
    if not rt:
        return
    t = rt[0]
    subs = [l["sub"]["status"] for l in t["lines"]]
    check("새로고침 뒤에도 자막 귀속이 유지(shown·late·shown)", subs == ["shown", "late", "shown"], subs)
    check("늦은 자막의 '지금 재생' 마디도 유지(l3)", t["lines"][1]["sub"]["during"] == "l3", t["lines"][1]["sub"])
    check("마디 3개·구간 순서 유지", [l["id"] for l in t["lines"]] == ["l1", "l2", "l3"]
          and t["lines"][0]["start"] < t["lines"][1]["start"] < t["lines"][2]["start"], t["lines"])
    p0, p1, p2 = info["play2_start"], info["play2_mid"], info["play2_end"]
    check("장면 2를 누르면 두 번째 마디 오디오가 재생됨",
          p0["src"] == t["lines"][1]["segUrl"] and p0["seg"] == 1, {"src": p0["src"][:40], "seg": p0["seg"]})
    check("장면 2 재생이 실제로 진행됨(0 → 중간 → 끝)",
          p0["currentTime"] < 0.6 and p1["currentTime"] > p0["currentTime"]
          and abs(p2["currentTime"] - t["lines"][1]["dur"]) < 0.2, {"p0": p0["currentTime"], "p1": p1["currentTime"], "p2": p2["currentTime"]})
    check("장면 2만 재생하고 세 번째 마디로 넘어가지 않음", p2["seg"] == 1 and p2["paused"] is True, p2)
    check("재생한 마디가 실제 두 번째 마디 구간(표시음 ±20Hz)",
          abs(info["reload_tones"][1]["peak"] - PITCH["l2"]) <= 20, [x["peak"] for x in info["reload_tones"]])
    check("원본의 세 구간에도 세 마디가 순서대로 남음(±20Hz)",
          all(abs(x["peak"] - PITCH[k]) <= 20 for x, k in zip(info["reload_orig_tones"], ["l1", "l2", "l3"])),
          [x["peak"] for x in info["reload_orig_tones"]])
    check("원본 전체 길이 유지", abs(info["reload_orig"]["dur"] - t["dur"]) < 0.05,
          {"orig": info["reload_orig"]["dur"], "take": t["dur"]})
    check("장면 다시 듣기는 자막 상태를 바꾸지 않음",
          [s["status"] for s in info["play2_subs"]] == ["shown", "late", "shown"], info["play2_subs"])
    check("원본 전체 저장 링크 제공", bool(info["dl"]) and info["dl"].startswith("blob:"), info["dl"][:40])
    check("한 녹음만 지우고 다른 녹음은 남음",
          len(info["two"]) == 2 and info["after_delete"] == [info["two"][1]], info["after_delete"])


# ---------------------------------------------------------------- E. 실제 마이크(가짜 장치)
def run_mic(browser):
    ctx, page, errors, cerrs, _ = new_page(browser)
    page.goto(BASE + "/")
    page.wait_for_timeout(900)
    page.click("#expABtn")
    page.wait_for_timeout(400)
    page.click("#expaRecBtn")
    page.wait_for_function("__DOHA.expa.state().recOn === true", timeout=15000)
    page.wait_for_timeout(2600)
    info = {"rec_label": page.inner_text("#expaState"), "rec_timer": page.inner_text("#expaTimer")}
    page.screenshot(path=os.path.join(SHOTS, "10-a-mic-recording.png"))
    page.click("#expaStopRecBtn")
    page.wait_for_function("__DOHA.expa.state().takes === 1", timeout=25000)
    page.wait_for_timeout(500)
    t = page.evaluate("__DOHA.expa.takes()")[0]
    info.update({"take": t, "log": page.evaluate("__DOHA.expa.log()"),
                 "ui": page.evaluate("__DOHA.expa.labels()"),
                 "badges": page.evaluate("Array.prototype.map.call(document.querySelectorAll('#expaTakes .expa-line .expa-seg'), e=>e.textContent)"),
                 "orig": wav_info(page, t["origUrl"])})
    page.locator("#expaTakes").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS, "11-a-mic-saved.png"))
    page.click('[data-take="%s"] [data-act="play2"]' % t["id"])
    page.wait_for_timeout(600)
    info["player"] = page.evaluate("__DOHA.expa.state().player")
    page.wait_for_timeout(1500)
    info["now"] = page.inner_text("#expaNow")
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_mic(info):
    t = info["take"]
    check("마이크 녹음 중 상태·시간 표시", info["rec_label"] == "녹음 중" and ":" in info["rec_timer"],
          {"label": info["rec_label"], "timer": info["rec_timer"]})
    check("녹음 한 번으로 원본 1개 + 마디 3개 저장", t["segCount"] == 3 and t["source"] == "mic" and t["bytes"] > 5000,
          {"source": t["source"], "bytes": t["bytes"], "segs": t["segCount"]})
    check("녹음 형식(MIME)을 그대로 보관", "audio" in (t["mime"] or ""), t["mime"])
    check("원본 길이·용량이 기록됨", t["dur"] > 1.0 and info["orig"]["bytes"] > 5000, {"dur": t["dur"], "bytes": info["orig"]["bytes"]})
    check("경계를 못 찾으면 '경계 자동 추정'으로 정직하게 표시",
          all(l["method"] in ("silence", "estimate") for l in t["lines"])
          and (all(l["method"] == "silence" for l in t["lines"])
               or all("경계 자동 추정" in b for b in info["badges"])),
          {"methods": [l["method"] for l in t["lines"]], "badges": info["badges"]})
    check("마이크로 녹음한 마디도 다시 재생됨", info["player"]["seg"] == 1 and info["player"]["src"] == t["lines"][1]["segUrl"],
          {"seg": info["player"]["seg"], "now": info["now"]})
    check("마이크 경로 에러 0", not info["errors"] and not info["console_errors"], info["errors"] or info["console_errors"])


# ---------------------------------------------------------------- F. 휴대폰
def run_phone(browser):
    ctx, page, errors, cerrs, _ = new_page(browser, 390, 844, True)
    page.goto(BASE + "/")
    page.wait_for_timeout(900)
    page.click("#expABtn")
    page.wait_for_timeout(500)
    info = {"overflow": page.evaluate(
        "({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,"
        "appSL:document.querySelector('#app').scrollLeft,"
        "expSL:document.querySelector('#s-expa .exp-scroll').scrollLeft,"
        "btnRight:Math.round(document.querySelector('#expaDemoBtn').getBoundingClientRect().right),"
        "vw:window.innerWidth})")}
    page.screenshot(path=os.path.join(SHOTS, "12-a-phone-idle.png"))
    page.click("#expaDemoBtn")
    page.wait_for_function("__DOHA.expa.state().takes === 1", timeout=25000)
    page.wait_for_timeout(500)
    info["take"] = page.evaluate("__DOHA.expa.takes()")[0]
    info["cards"] = page.evaluate("document.querySelectorAll('#expaTakes .expa-line').length")
    page.locator("#expaTakes").scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS, "13-a-phone-lines.png"))
    page.click('[data-take="%s"] [data-act="play3"]' % info["take"]["id"])
    page.wait_for_timeout(700)
    info["player"] = page.evaluate("__DOHA.expa.state().player")
    info["errors"], info["console_errors"] = errors, cerrs
    ctx.close()
    return info


def check_phone(info):
    ov = info["overflow"]
    check("[phone] A 화면 가로 밀림 없음", ov["sw"] == ov["cw"] and ov["appSL"] == 0 and ov["expSL"] == 0, ov)
    check("[phone] 녹음·예시 버튼이 화면 안에 들어옴", ov["btnRight"] <= ov["vw"], ov)
    check("[phone] 마디 카드 3개 표시", info["cards"] == 3, info["cards"])
    check("[phone] 마디 재생·에러 0",
          info["player"]["seg"] == 2 and not info["errors"] and not info["console_errors"],
          {"seg": info["player"]["seg"], "errors": info["errors"] or info["console_errors"]})


def main():
    os.makedirs(SHOTS, exist_ok=True)
    static_checks()
    httpd = start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=FAKE)
            print("Chromium", browser.version, flush=True)
            print("--- A-1. resume 지연(재생 중 표시 보완)", flush=True)
            check_resume(run_resume(browser))
            print("--- A-2. resume 실패·재시도", flush=True)
            check_resume_fail(run_resume_fail(browser))
            print("--- B·C·D. 한 번에 이어 녹음·늦은 자막·새로고침", flush=True)
            info = run_batch(browser)
            check_batch(info)
            check_late(info)
            check_reload(info)
            print("--- E. 실제 마이크(가짜 장치)", flush=True)
            check_mic(run_mic(browser))
            print("--- F. 휴대폰", flush=True)
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
