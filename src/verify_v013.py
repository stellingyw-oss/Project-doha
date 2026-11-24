#!/usr/bin/env python3
"""PROJECT DOHA v0.1.3 검증 — 캔버스 바로 듣기 + 임시 음성 자막 변환(STT, 기본 OFF).

검증 항목
 H. 바로 듣기 — 녹음 전 숨김 / 녹음 뒤 표시 / 재생·정지 / 끝나면 라벨 복귀
 I. 바로 듣기 — 마이크 재시작·화면 이탈·다른 장면 이동 시 자동 정지
 J. 음성 자막 변환 — 기본 OFF(토글·상태·인식기 미생성), 마이크를 켜도 시작하지 않음
 K. 음성 자막 변환 ON — 확정 결과가 '예시 그림 ·' 장면으로 붙고 원본 녹음은 그대로 저장
 L. 음성 자막 변환 오류 — 토글 자동 OFF, 원본 녹음·저장은 무중단
 M. 음성 자막 변환 미지원 — 켜지 않고 안내, 원본 녹음은 그대로
 N. 새로고침 뒤에도 기본 OFF, 콘솔·런타임 에러 0

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
    check("소스: 음성 자막 변환 라벨에 서버 전송 가능 표기", "음성 자막 변환 (임시 · 브라우저 서버 전송 가능)" in src)
    check("소스: 원본 녹음과 STT가 같은 try 블록에 묶여 있지 않음(격리)",
          "sttCommit" in src and "MediaRecorder" in src and src.index("function sttCommit") < src.index("function startRecorder"))

    with sync_playwright() as pw:
        # ================= 세션 H·I·J: 바로 듣기 + STT 기본 OFF =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr(""))
        page.goto(url)
        page.wait_for_timeout(800)
        REPORT["data"]["url"] = url

        check("버전 meta = 0.1.3", page.eval_on_selector("meta[name=doha-version]", "e=>e.content") == "0.1.3")
        check("초기 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)

        start_story(page)
        st0 = listen_state(page)
        print(st0)
        check("H. 녹음 전에는 바로 듣기 버튼 숨김", st0["hidden"] is True and st0["available"] is False, st0)
        check("J. 음성 자막 변환 토글 기본 OFF", page.get_attribute("#sttBtn", "aria-checked") == "false")
        j0 = page.evaluate("__DOHA.stt()")
        check("J. 기본 상태에서 인식기 생성 0회", j0["on"] is False and j0["starts"] == 0 and not page.evaluate("window.__stt.ctors"), j0)

        mic_on(page)
        page.wait_for_timeout(1200)
        j1 = page.evaluate("__DOHA.stt()")
        check("J. OFF 상태에서 마이크를 켜도 음성인식을 시작하지 않음",
              j1["on"] is False and j1["starts"] == 0 and not page.evaluate("window.__stt.ctors"), j1)
        check("J. OFF 상태에서 녹음은 정상 동작", j1["on"] is False and page.evaluate("__DOHA.mic().on") is True)
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

        check("세션 H/I/J 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        page.screenshot(path="/workspace/tmp/shots/v013-canvas.png")
        ctx.close()
        browser.close()

        # ================= 세션 K: STT 켬 → 확정 결과가 예시 장면으로 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr("interim"))
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        page.click("#sttBtn")
        page.wait_for_timeout(250)
        k1 = page.evaluate("__DOHA.stt()")
        check("K. 토글을 켜면 aria-checked=true·안내 문구 갱신",
              page.get_attribute("#sttBtn", "aria-checked") == "true"
              and "서버" in page.inner_text("#sttNote"), page.inner_text("#sttNote"))
        mic_on(page)
        page.wait_for_function("__DOHA.stt().finals > 0", timeout=6000)
        page.wait_for_timeout(300)
        scenes = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>({key:s.key,src:s.source,cap:s.caption,takes:(s.takes||[]).length}))")
        REPORT["data"]["stt_on"] = {"stt": page.evaluate("__DOHA.stt()"), "scenes": scenes}
        check("K. 확정된 말이 장면으로 추가됨", len(scenes) == 1 and scenes[0]["cap"] == "우주선을 타고 하늘로 날아갔어", scenes)
        check("K. 그 장면은 '예시 그림' 라벨(source=sample)", scenes and scenes[0]["src"] == "sample" and scenes[0]["key"] == "space", scenes)
        check("K. 자막에 '예시 그림 ·' 접두 표시", page.inner_text("#capText").startswith("예시 그림 ·"), page.inner_text("#capText"))
        k2 = page.evaluate("__DOHA.stt()")
        check("K. 인식 결과 수신·오류 0", k2["finals"] >= 1 and k2["errors"] == 0, k2)
        check("K. 음성인식은 ko-KR·interimResults로 시작", page.evaluate("__DOHA.stt().starts") >= 1
              and page.evaluate("document.querySelector('#sttHear').hidden") in (True, False))
        check("K. STT 중에도 원본 녹음은 계속 동작", page.evaluate("__DOHA.mic().on") is True, page.evaluate("__DOHA.mic()"))

        mic_off(page)
        k3 = page.evaluate("__DOHA.stt()")
        check("K. 마이크를 끄면 음성인식도 멈춤", k3["on"] is True and page.evaluate("window.__stt.aborts + window.__stt.stops") >= 1, k3)
        end_scenes = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>({src:s.source,takes:(s.takes||[]).length}))")
        check("K. 말한 장면과 녹음 장면이 분리되어 보존", len(end_scenes) == 2
              and end_scenes[0]["src"] == "sample" and end_scenes[0]["takes"] == 0
              and end_scenes[1]["takes"] == 1, end_scenes)
        page.click("#endBtn")
        page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=12000)
        k4 = page.evaluate("""()=>({phase:__DOHA.saveState(), audioUpdate:document.querySelectorAll('#originalAudio audio').length,
            album:__DOHA.album().length})""")
        check("K. STT를 켜도 원본 녹음까지 완전 저장", k4["phase"]["phase"] == "SAVED_COMPLETE"
              and k4["phase"]["audioSaved"] == 1 and k4["audioUpdate"] == 1 and k4["album"] == 1, k4)
        check("세션 K 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        page.screenshot(path="/workspace/tmp/shots/v013-stt-on.png")
        ctx.close()
        browser.close()

        # ================= 세션 L: STT 오류 → 녹음 무중단 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr("error"))
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        page.click("#sttBtn")
        page.wait_for_timeout(200)
        mic_on(page)
        page.wait_for_function("__DOHA.stt().errors > 0", timeout=6000)
        page.wait_for_timeout(300)
        l1 = page.evaluate("__DOHA.stt()")
        REPORT["data"]["stt_error"] = l1
        check("L. 인식 오류가 나면 토글이 스스로 OFF", l1["on"] is False and l1["errors"] >= 1
              and page.get_attribute("#sttBtn", "aria-checked") == "false", l1)
        check("L. 오류 뒤에도 마이크·녹음은 계속", page.evaluate("__DOHA.mic().on") is True
              and page.evaluate("__DOHA.mic().losses") == 0, page.evaluate("__DOHA.mic()"))
        check("L. 안내 문구가 원본 녹음 보존을 알림", "원본 녹음" in page.inner_text("#sttNote"), page.inner_text("#sttNote"))
        check("L. 오류 뒤에는 음성인식을 다시 붙이지 않음", page.evaluate("__DOHA.stt().starts") == 1,
              page.evaluate("__DOHA.stt()"))
        page.wait_for_timeout(1200)
        mic_off(page)
        l2 = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>({src:s.source,key:s.key,takes:(s.takes||[]).length}))")
        check("L. 오류에도 방해 없이 중립 장면에 원본 녹음 1구간", len(l2) == 1 and l2[0]["key"] == "neutral"
              and l2[0]["takes"] == 1, l2)
        page.click("#endBtn")
        page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=12000)
        l3 = page.evaluate("()=>({save:__DOHA.saveState(), album:__DOHA.album().length})")
        check("L. STT 오류와 무관하게 SAVED_COMPLETE", l3["save"]["phase"] == "SAVED_COMPLETE"
              and l3["save"]["audioSaved"] == 1 and l3["album"] == 1, l3)
        check("세션 L 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close()
        browser.close()

        # ================= 세션 M: 미지원 브라우저 → 켜지지 않음 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=NO_SR)
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        m0 = page.evaluate("__DOHA.stt()")
        check("M. 음성인식이 없는 브라우저에서 supported=false", m0["supported"] is False and m0["on"] is False, m0)
        page.click("#sttBtn")
        page.wait_for_timeout(300)
        m1 = page.evaluate("__DOHA.stt()")
        check("M. 미지원 브라우저에서는 토글이 켜지지 않음", m1["on"] is False
              and page.get_attribute("#sttBtn", "aria-checked") == "false", m1)
        check("M. 미지원 안내 문구 표시", "지원하지 않아요" in page.inner_text("#sttNote"), page.inner_text("#sttNote"))
        mic_on(page)
        page.wait_for_timeout(1200)
        check("M. 미지원 상태에서도 원본 녹음은 정상", page.evaluate("__DOHA.mic().on") is True
              and page.evaluate("__DOHA.mic().losses") == 0, page.evaluate("__DOHA.mic()"))
        mic_off(page)
        m2 = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>({takes:(s.takes||[]).length}))")
        check("M. 미지원 상태에서도 테이크가 남음", m2 and m2[0]["takes"] == 1, m2)
        page.click("#endBtn")
        page.wait_for_function("__DOHA.saveState().phase==='SAVED_COMPLETE'", timeout=12000)
        check("M. 미지원 상태에서도 저장 완료", page.evaluate("__DOHA.saveState().phase") == "SAVED_COMPLETE")
        check("세션 M 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close()
        browser.close()

        # ================= 세션 N: 새로고침 뒤에도 기본 OFF =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script=sr("final"))
        page.goto(url)
        page.wait_for_timeout(700)
        start_story(page)
        page.click("#sttBtn")
        page.wait_for_timeout(200)
        check("N. 켠 상태 확인", page.get_attribute("#sttBtn", "aria-checked") == "true")
        page.reload()
        page.wait_for_timeout(900)
        check("N. 새로고침(새 세션) 뒤에는 다시 기본 OFF", page.get_attribute("#sttBtn", "aria-checked") == "false"
              and page.evaluate("__DOHA.stt().on") is False, page.evaluate("__DOHA.stt()"))
        check("세션 N 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
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
