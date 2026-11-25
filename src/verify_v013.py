#!/usr/bin/env python3
"""PROJECT DOHA v0.1.3 기능 검증 — 캔버스 바로 듣기 + 음성 자막 변환의 '시작되지 않음' 확인.

v0.1.4 공개분부터 음성 자막 인식(STT)은 안전상 비활성화되었다(녹음 동의 문구는 '이 브라우저에만
저장'인데 브라우저 음성인식은 오디오를 제조사 서버로 보낼 수 있기 때문). 그래서 v0.1.3의
K~N 세션(켜짐·오류·미지원·새 세션)은 **어떤 경로로도 인식기가 생성·시작되지 않는다**를
검사하도록 바뀌었다. 인식 코드는 v0.2를 위해 소스에 남아 있되 STT_ENABLED=false 로 잠겨 있다.

검증 항목
 H. 바로 듣기 — 녹음 전 숨김 / 녹음 뒤 표시 / 재생·정지 / 끝나면 라벨 복귀
 I. 바로 듣기 — 마이크 재시작·화면 이탈·다른 장면 이동 시 자동 정지
 K. 음성 자막 변환 비활성 — 토글·setStt(true)·마이크 어느 경로로도 인식기 0회, 녹음·저장은 정상
 L. 음성인식이 없는 브라우저 — 같은 안내, 녹음·저장은 정상
 M. 새로고침(새 세션) 뒤에도 같은 상태, 콘솔·런타임 에러 0

사용:
  LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu \\
    python3 project-doha/src/verify_v013.py
  (DOHA_URL 을 주면 그 주소로 검사한다. CHROMIUM 으로 실행 파일을 지정할 수 있다.)
"""
import functools
import http.server
import json
import os
import socketserver
import threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("DOHA_PORT", "8793"))
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
REPORT = {"checks": [], "data": {}}


def check(name, ok, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + ("  · " + str(detail)[:300] if detail != "" else ""))


def _start_stt_head(src):
    i = src.find("function startStt()")
    return src[i:i + 240] if i >= 0 else "startStt 없음"


def _start_stt_guard_before_ctor(src):
    """startStt()가 인식기 생성(new C())보다 앞에서 STT_ENABLED 로 끊기는지."""
    i = src.find("function startStt()")
    if i < 0:
        return False
    body = src[i:i + 4000]
    guard = body.find("if(!STT_ENABLED) return;")
    ctor = body.find("new C()")
    return guard >= 0 and ctor > guard and body.find("r.start()") > ctor


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class Reusable(socketserver.TCPServer):
    allow_reuse_address = True


def serve(root, port=0):
    httpd = Reusable(("127.0.0.1", port), functools.partial(Quiet, directory=root))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def new_page(browser, init_script=None):
    ctx = browser.new_context(viewport={"width": 1180, "height": 820},
                              permissions=["microphone"], accept_downloads=True)
    page = ctx.new_page()
    errs, cerrs = [], []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: d.accept())
    if init_script:
        page.add_init_script(init_script)
    return ctx, page, errs, cerrs


# 테스트용 가짜 음성인식 — 실제 브라우저 음성인식은 서버·권한이 필요하므로 동작만 흉내 낸다.
FAKE_SR = """
window.__stt={ctors:0, starts:0, aborts:0, stops:0};
(function(){
  var MODE="__MODE__";
  function FakeSR(){
    window.__stt.ctors++;
    this.onresult=null; this.onerror=null; this.onend=null;
    this.lang=""; this.interimResults=false; this.continuous=false;
    this.__alive=true;
  }
  FakeSR.prototype.start=function(){
    if(!this.__alive) throw new Error("inactive");
    window.__stt.starts++;
    var self=this;
    if(MODE==="final"){
      setTimeout(function(){
        if(!self.onresult) return;
        var r=Object.assign([{transcript:"우주선을 타고 하늘로 날아갔어"}],{isFinal:true});
        self.onresult({resultIndex:0, results:[r]});
      },350);
    } else if(MODE==="interim"){
      setTimeout(function(){
        if(!self.onresult) return;
        var r=Object.assign([{transcript:"어… 그러니까"}],{isFinal:false});
        self.onresult({resultIndex:0, results:[r]});
      },150);
      setTimeout(function(){
        if(!self.onresult) return;
        var r=Object.assign([{transcript:"우주선을 타고 하늘로 날아갔어"}],{isFinal:true});
        self.onresult({resultIndex:0, results:[r]});
      },600);
    } else if(MODE==="error"){
      setTimeout(function(){ if(self.onerror) self.onerror({error:"network"}); },300);
    }
  };
  FakeSR.prototype.abort=function(){ window.__stt.aborts++; this.__alive=false; };
  FakeSR.prototype.stop=function(){ window.__stt.stops++; var s=this; setTimeout(function(){ if(s.onend) s.onend(); },0); };
  window.SpeechRecognition=FakeSR; window.webkitSpeechRecognition=FakeSR;
})();
"""


def sr(mode=""):
    """가짜 음성인식 주입 스크립트. mode="" 이면 아무 결과도 내지 않는다."""
    return FAKE_SR.replace("__MODE__", mode)


NO_SR = """
Object.defineProperty(window,'SpeechRecognition',{value:undefined,configurable:true});
Object.defineProperty(window,'webkitSpeechRecognition',{value:undefined,configurable:true});
"""


def start_story(page):
    page.click("#startBtn")
    page.wait_for_timeout(600)


def mic_on(page):
    page.click("#micBtn")
    page.wait_for_function("__DOHA.mic().on")
    page.wait_for_timeout(200)


def mic_off(page):
    page.click("#micBtn")
    page.wait_for_function("!__DOHA.mic().on && !__DOHA.mic().stopping", timeout=8000)
    page.wait_for_timeout(300)


def listen_state(page):
    return page.evaluate("""() => {
        const b=document.querySelector('#listenBtn');
        return {hidden:!!b.hidden, label:(b.textContent||'').trim(), open:!!__DOHA.listen().playing,
                available:!!__DOHA.listen().available};
    }""")


def main():
    url = os.environ.get("DOHA_URL")
    httpd = None
    if not url:
        httpd = serve(ROOT)
        url = "http://127.0.0.1:%d/index.html" % httpd.server_address[1]

    # ---------- 정적 검사 ----------
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    check("소스: 바로 듣기 버튼 존재", 'id="listenBtn"' in src and "▶ 방금 녹음 듣기" in src)
    check("소스: 음성 자막 변환 토글이 기본 OFF(aria-checked=false)", 'id="sttBtn"' in src and 'aria-checked="false"' in src)
    check("소스: 음성 자막 토글은 비활성 상태·'v0.2 준비 중' 라벨",
          'aria-disabled="true"' in src and "음성 자막 변환 (v0.2 준비 중)" in src)
    check("소스: STT 스위치가 false 이고 startStt 첫 줄에서 끊김(인식기 생성 전)",
          "var STT_ENABLED=false" in src
          and _start_stt_guard_before_ctor(src), _start_stt_head(src))
    check("소스: 원본 녹음과 STT 스위치가 같은 try 블록에 묶여 있지 않음(격리)",
          "sttCommit" in src and "MediaRecorder" in src and src.index("function sttCommit") < src.index("function startRecorder"))

    with sync_playwright() as pw:
        # ================= 세션 H·I: 바로 듣기, 음성 자막은 비활성 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr(""))
        page.goto(url)
        page.wait_for_timeout(800)
        REPORT["data"]["url"] = url

        check("버전 meta = 0.1.4", page.eval_on_selector("meta[name=doha-version]", "e=>e.content") == "0.1.4")
        check("초기 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)

        start_story(page)
        st0 = listen_state(page)
        print(st0)
        check("H. 녹음 전에는 바로 듣기 버튼 숨김", st0["hidden"] is True and st0["available"] is False, st0)
        check("K. 음성 자막 토글 기본 OFF·비활성", page.get_attribute("#sttBtn", "aria-checked") == "false"
              and page.get_attribute("#sttBtn", "aria-disabled") == "true")
        j0 = page.evaluate("__DOHA.stt()")
        check("K. 기본 상태에서 인식기 생성 0회·enabled=false",
              j0["enabled"] is False and j0["on"] is False and j0["starts"] == 0
              and not page.evaluate("window.__stt.ctors"), j0)

        mic_on(page)
        page.wait_for_timeout(1200)
        j1 = page.evaluate("__DOHA.stt()")
        check("K. 마이크를 켜도 음성인식을 시작하지 않음",
              j1["on"] is False and j1["starts"] == 0 and not page.evaluate("window.__stt.ctors"), j1)
        check("K. 마이크 녹음은 정상 동작", page.evaluate("__DOHA.mic().on") is True)
        mic_off(page)

        st1 = listen_state(page)
        check("H. 녹음 뒤 바로 듣기 버튼 표시", st1["hidden"] is False and st1["available"] is True, st1)
        check("H. 기본 라벨은 '▶ 방금 녹음 듣기'", st1["label"] == "▶ 방금 녹음 듣기", st1["label"])

        page.click("#listenBtn")
        page.wait_for_timeout(400)
        st2 = listen_state(page)
        check("H. 버튼을 누르면 즉시 재생", st2["open"] is True and st2["label"] == "⏸ 멈추기", st2)
        page.click("#listenBtn")
        page.wait_for_timeout(250)
        st3 = listen_state(page)
        check("H. 다시 누르면 정지하고 라벨 복귀", st3["open"] is False and st3["label"] == "▶ 방금 녹음 듣기", st3)

        # I-1. 마이크를 다시 켜면 재생 정지
        page.click("#listenBtn")
        page.wait_for_timeout(250)
        check("I. 재생 중 상태 확인", listen_state(page)["open"] is True, listen_state(page))
        mic_on(page)
        page.wait_for_timeout(300)
        check("I. 마이크를 다시 켜면 바로 듣기 정지", listen_state(page)["open"] is False, listen_state(page))
        mic_off(page)

        # I-2. 화면을 떠나면 재생 정지
        page.click("#listenBtn")
        page.wait_for_timeout(250)
        page.click("#cvBack")
        page.wait_for_timeout(400)
        check("I. 캔버스를 떠나면 바로 듣기 정지", listen_state(page)["open"] is False, listen_state(page))

        page.click("#startBtn")  # 이어서 상상하기로 캔버스 복귀
        page.wait_for_timeout(600)
        check("I. 돌아오면 이전 테이크의 바로 듣기 버튼이 다시 보임", listen_state(page)["hidden"] is False, listen_state(page))

        # I-3. 테이크가 없는 장면으로 옮기면 버튼 숨김
        page.fill("#sayInput", "다음엔 달에 가고 싶어")
        page.press("#sayInput", "Enter")
        page.wait_for_timeout(600)
        page.eval_on_selector_all("#strip button", "els=>els[els.length-1].click()")
        page.wait_for_timeout(300)
        st_no = listen_state(page)
        check("I. 녹음이 없는 장면에서는 바로 듣기 버튼 숨김", st_no["hidden"] is True, st_no)
        page.eval_on_selector_all("#strip button", "els=>els[0].click()")
        page.wait_for_timeout(300)
        check("I. 녹음이 있는 장면으로 돌아오면 다시 표시", listen_state(page)["hidden"] is False, listen_state(page))

        # H-2. 재생이 끝나면 라벨이 스스로 돌아온다
        page.click("#listenBtn")
        page.wait_for_timeout(2200)
        st_end = listen_state(page)
        check("H. 재생이 끝나면 라벨이 '▶ 방금 녹음 듣기'로 복귀", st_end["open"] is False and st_end["label"] == "▶ 방금 녹음 듣기", st_end)

        check("세션 H/I/K 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        page.screenshot(path="/workspace/tmp/shots/v013-canvas.png")
        ctx.close()
        browser.close()

        # ================= 세션 K: 토글·setStt(true)로도 인식기가 생기지 않는다 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr("interim"))
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        # 실제 사람이 누르는 좌표 클릭(aria-disabled 라 Playwright의 기본 클릭은 막히므로 force)
        page.locator("#sttBtn").click(force=True)
        page.wait_for_timeout(300)
        k1 = page.evaluate("__DOHA.stt()")
        REPORT["data"]["stt_disabled"] = {"stt": k1, "note": page.inner_text("#sttNote"),
                                         "toast": page.inner_text("#toast")}
        check("K. 토글을 눌러도 켜지지 않음(aria-checked=false·on=false)",
              page.get_attribute("#sttBtn", "aria-checked") == "false" and k1["on"] is False, k1)
        check("K. 토글을 눌러도 인식기 생성·시작 0회",
              not page.evaluate("window.__stt.ctors") and not page.evaluate("window.__stt.starts")
              and k1["starts"] == 0, page.evaluate("window.__stt"))
        check("K. 'v0.2 준비 중' 안내가 화면에 뜸",
              "v0.2" in page.inner_text("#toast") and "이 브라우저에만" in page.inner_text("#sttNote"),
              page.inner_text("#toast") + " / " + page.inner_text("#sttNote"))
        page.locator("#sttBtn").click(force=True)
        page.wait_for_timeout(200)
        check("K. 두 번째로 눌러도 그대로 OFF",
              page.get_attribute("#sttBtn", "aria-checked") == "false"
              and not page.evaluate("window.__stt.ctors"), page.evaluate("__DOHA.stt()"))
        k2 = page.evaluate("__DOHA.setStt(true,true)")
        check("K. 스크립트로 setStt(true) 해도 켜지지 않고 인식기 0회",
              k2 is False and not page.evaluate("window.__stt.ctors")
              and page.evaluate("__DOHA.stt().on") is False, page.evaluate("__DOHA.stt()"))

        mic_on(page)
        page.wait_for_timeout(1200)
        check("K. 마이크를 켜도·녹음 중에도 인식기 0회",
              not page.evaluate("window.__stt.ctors") and page.evaluate("__DOHA.stt().starts") == 0,
              page.evaluate("window.__stt"))
        mic_off(page)
        k3 = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>({src:s.source,takes:(s.takes||[]).length}))")
        check("K. 음성 자막 없이도 원본 녹음 1구간이 중립 장면에 남음",
              len(k3) == 1 and k3[0]["takes"] == 1, k3)
        page.click("#endBtn")
        page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=12000)
        k4 = page.evaluate("""()=>({phase:__DOHA.saveState(), audioUpdate:document.querySelectorAll('#originalAudio audio').length,
            album:__DOHA.album().length})""")
        check("K. 음성 자막 비활성 상태에서도 원본 녹음까지 완전 저장", k4["phase"]["phase"] == "SAVED_COMPLETE"
              and k4["phase"]["audioSaved"] == 1 and k4["audioUpdate"] == 1 and k4["album"] == 1, k4)
        check("세션 K 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        page.screenshot(path="/workspace/tmp/shots/v013-stt-disabled.png")
        ctx.close()
        browser.close()

        # ================= 세션 L: 음성인식이 없는 브라우저 → 같은 안내, 녹음·저장 정상 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=NO_SR)
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        m0 = page.evaluate("__DOHA.stt()")
        check("L. 음성인식이 없는 브라우저에서 supported=false·enabled=false",
              m0["supported"] is False and m0["enabled"] is False and m0["on"] is False, m0)
        page.locator("#sttBtn").click(force=True)
        page.wait_for_timeout(300)
        check("L. 미지원 브라우저에서도 토글이 켜지지 않음", page.evaluate("__DOHA.stt().on") is False
              and page.get_attribute("#sttBtn", "aria-checked") == "false")
        check("L. 안내 문구가 원본 녹음 보존을 알림", "이 브라우저에만" in page.inner_text("#sttNote"),
              page.inner_text("#sttNote"))
        mic_on(page)
        page.wait_for_timeout(1200)
        check("L. 미지원 상태에서도 원본 녹음은 정상", page.evaluate("__DOHA.mic().on") is True
              and page.evaluate("__DOHA.mic().losses") == 0, page.evaluate("__DOHA.mic()"))
        mic_off(page)
        m2 = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>({takes:(s.takes||[]).length}))")
        check("L. 미지원 상태에서도 테이크가 남음", bool(m2) and m2[0]["takes"] == 1, m2)
        page.click("#endBtn")
        page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=12000)
        check("L. 미지원 상태에서도 저장 완료", page.evaluate("__DOHA.saveState().phase") == "SAVED_COMPLETE")
        check("세션 L 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close()
        browser.close()

        # ================= 세션 M: 새로고침(새 세션) 뒤에도 같은 상태 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr("final"))
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        page.locator("#sttBtn").click(force=True)
        page.wait_for_timeout(200)
        page.reload()
        page.wait_for_timeout(900)
        check("M. 새로고침(새 세션) 뒤에도 OFF·비활성", page.get_attribute("#sttBtn", "aria-checked") == "false"
              and page.get_attribute("#sttBtn", "aria-disabled") == "true"
              and page.evaluate("__DOHA.stt().on") is False, page.evaluate("__DOHA.stt()"))
        check("M. 새 세션에서도 인식기 생성 0회", not page.evaluate("window.__stt.ctors"))
        check("세션 M 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close()
        browser.close()

    if httpd:
        httpd.shutdown()
    ok = all(c["ok"] for c in REPORT["checks"])
    print("\n=== RESULT:", "ALL PASS" if ok else "FAILED", "=== (%d checks)" % len(REPORT["checks"]))
    print(json.dumps(REPORT["data"], ensure_ascii=False, indent=1, default=str)[:4000])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    os.makedirs("/workspace/tmp/shots", exist_ok=True)
    main()
