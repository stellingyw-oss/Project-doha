#!/usr/bin/env python3
"""PROJECT DOHA 통합 빌드(v0.1.3) 검증 (headless Chromium).

v0.1.2 저장·녹음 스프린트의 회귀 스위트를 PR #1 통합 UX(녹음 전 동의 확인, 중립 시작,
수동 재생, 3종 카드 버튼)에 맞춰 정합성 업데이트한 판.

검증 항목
 A. 저장 상태 4단계 — SAVING 중 앨범 반영·화면 전환 차단, 저장 확인 뒤 SAVED_COMPLETE
 B. 녹음 덮어쓰기/경쟁 상태 — 한 장면 여러 테이크 보존, 40초 상한 없음, 종료·저장 순서 보장
 C. IndexedDB 불가 → SAVED_TEXT_ONLY (완전 성공으로 표시하지 않음)
 D. 저장 완전 실패 → SAVE_FAILED (앨범 미반영 + 파일 내려받기·재시도 안내)
 E. v0.1 localStorage 이관 — 확인 뒤에만 원본 삭제 / 실패하면 원본 보존
 F. 기록 내보내기(개별·전체) · 개별 삭제 · 새로고침 뒤 복원
 G. 런타임·콘솔 에러 0건

사용:
  LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu \
    python3 project-doha/src/verify_v012.py
  (DOHA_URL 을 주면 그 주소로 검사한다. 예: 라이브 URL)
"""
import functools
import http.server
import json
import os
import socketserver
import threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("DOHA_PORT", "8792"))
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


def new_page(browser, init_script=None, perms=("microphone",)):
    """페이지 하나 + 대화상자 정책.

    v0.1.3은 마이크를 켤 때 보호자·아이 동의 confirm을 띄운다. 테스트는 이 대화상자를
    자동 수락하되, 삭제·새 이야기 확인창은 정책으로 따로 제어한다.
    """
    ctx = browser.new_context(viewport={"width": 1180, "height": 820}, permissions=list(perms),
                              accept_downloads=True)
    page = ctx.new_page()
    errs, cerrs = [], []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    policy = {"consent": True, "confirm": True}

    def on_dialog(dialog):
        msg = dialog.message or ""
        consent = ("동의" in msg and "녹음" in msg)
        allow = policy["consent"] if consent else policy["confirm"]
        dialog.accept() if allow else dialog.dismiss()

    page.on("dialog", on_dialog)
    if init_script:
        page.add_init_script(init_script)
    page.dialog_policy = policy
    return ctx, page, errs, cerrs


IDB_DUMP = """() => new Promise((res)=>{
  const rq=indexedDB.open('doha-universe',1);
  rq.onerror=()=>res({error:'open'});
  rq.onsuccess=()=>{
    const db=rq.result, out={works:[],clips:[]};
    const t=db.transaction(['works','clips'],'readonly');
    const ws=t.objectStore('works').getAll(), cs=t.objectStore('clips').getAll();
    let n=0; const done=()=>{ if(++n>=2) res(out); };
    ws.onsuccess=()=>{ out.works=ws.result.map(w=>({id:w.id,no:w.no,
      caps:(w.scenes||[]).map(s=>s.caption),
      clipIds:(w.scenes||[]).map(s=>s.clipIds||[]),
      durs:(w.scenes||[]).map(s=>s.audioDur||0)})); done(); };
    cs.onsuccess=()=>{ out.clips=cs.result.map(c=>({id:c.id,workId:c.workId,bytes:c.blob?c.blob.size:0})); done(); };
  };
})"""

CARD_SEL = ".al-grid:not(.al-grid-samples) .al-card:not(.al-add)"
# 영화 화면의 원본 목소리 카드도 .al-card-btn 을 쓰므로, 앨범 그리드 안으로 범위를 좁힌다
BTN_SEL = ".al-grid:not(.al-grid-samples) .al-card-actions .al-card-btn"


def cards(page):
    return page.eval_on_selector_all(CARD_SEL, "els=>els.length")


def end_and_capture(page):
    """이야기 끝내기 클릭 직후(=SAVING 진입 시점)의 화면·저장 상태를 잰다."""
    return page.evaluate("""() => {
        document.querySelector('#endBtn').click();
        return {
          screen: window.__DOHA.state.screen,
          phase: window.__DOHA.saveState().phase,
          overlay: document.querySelector('#saveOverlay').classList.contains('on'),
          album: window.__DOHA.album().length,
          saveBtn: (document.querySelector('#saveAlbumBtn').textContent||'').trim(),
          saveBtnDisabled: document.querySelector('#saveAlbumBtn').disabled
        };
    }""")


def wait_phase(page, phase, timeout=8000):
    page.wait_for_function("(p)=>window.__DOHA.saveState().phase===p", arg=phase, timeout=timeout)


def main():
    url = os.environ.get("DOHA_URL")
    httpd = None
    if not url:
        httpd = serve(ROOT)
        url = "http://127.0.0.1:%d/index.html" % httpd.server_address[1]

    # ---------- 정적 검사: 소스에 40초 상한·잘못된 성공 반환이 남아있지 않은가 ----------
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    check("소스: 40초 강제 상한(Math.min(...,40)) 제거", "duration||2,1),40" not in src and "1),40)" not in src)
    check("소스: 음성 없이 true 반환하는 폴백 제거", "lsPutWork(rec); return true" not in src)
    check("소스: 저장 상태 4단계 이름 존재",
          all(k in src for k in ("SAVED_COMPLETE", "SAVED_TEXT_ONLY", "SAVE_FAILED", "SAVING")))

    with sync_playwright() as pw:
        # ================= 세션 A: 정상 저장·녹음·내보내기·삭제 =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser)
        page.goto(url)
        page.wait_for_timeout(900)
        REPORT["data"]["url"] = url

        check("버전 meta = 0.1.4", page.eval_on_selector("meta[name=doha-version]", "e=>e.content") == "0.1.4")
        check("홈 표기에 v0.1.4", "v0.1.4" in page.inner_text(".brand-sub"), page.inner_text(".brand-sub"))
        check("음성 자막 변환 토글 기본 OFF", page.get_attribute("#sttBtn", "aria-checked") == "false",
              page.get_attribute("#sttBtn", "aria-checked"))
        check("초기 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)

        # --- 1편: 마이크 켜고 녹음한 뒤 이야기 끝내기 ---
        page.click("#startBtn")
        page.wait_for_timeout(1300)
        check("강제 첫 장면 없이 중립 화면에서 시작", page.locator("#stage .frame").count() == 0,
              page.locator("#stage .frame").count())
        check("녹음 전 바로 듣기 버튼은 숨김", page.is_hidden("#listenBtn") is True)
        page.click("#micBtn")
        page.wait_for_timeout(1500)
        check("마이크 켜짐: 트랙 live", page.evaluate("window.__DOHA.mic()")["tracks"] == ["live"])

        cap = end_and_capture(page)
        REPORT["data"]["at_end_click"] = cap
        check("종료 클릭 직후 SAVING 상태", cap["phase"] == "SAVING", cap)
        check("SAVING 중에는 화면이 캔버스에 머문다", cap["screen"] == "canvas", cap["screen"])
        check("SAVING 중 저장 오버레이 표시", cap["overlay"] is True)
        check("SAVING 중 앨범에 아직 반영되지 않음", cap["album"] == 0, cap["album"])
        check("SAVING 중 저장 버튼 비활성·'저장하는 중'", cap["saveBtnDisabled"] and "저장하는 중" in cap["saveBtn"], cap["saveBtn"])

        wait_phase(page, "SAVED_COMPLETE", 10000)
        page.wait_for_timeout(700)
        after = page.evaluate("""()=>({screen:window.__DOHA.state.screen,
            overlay:document.querySelector('#saveOverlay').classList.contains('on'),
            album:window.__DOHA.album().length,
            noticeHidden:document.querySelector('#saveNotice').hidden,
            takes:window.__DOHA.state.scenes.map(s=>(s.takes||[]).length),
            durs:window.__DOHA.state.scenes.map(s=>s.audioDur)})""")
        REPORT["data"]["after_save"] = after
        check("저장 완료 뒤 영화 화면으로 전환", after["screen"] == "movie", after["screen"])
        check("저장 완료 뒤 SAVED_COMPLETE·오버레이 해제", after["overlay"] is False)
        check("저장 완료 뒤 앨범 1편 반영", after["album"] == 1, after["album"])
        check("완전 저장이면 안내 배너 없음", after["noticeHidden"] is True)
        check("마이크 트랙 종료(micOn=false, ended)",
              page.evaluate("window.__DOHA.mic()")["tracks"] in ([], ["ended"]), page.evaluate("window.__DOHA.mic()"))

        dump = page.evaluate(IDB_DUMP)
        REPORT["data"]["idb_1"] = dump
        check("IndexedDB works 1건·clips 1건", len(dump["works"]) == 1 and len(dump["clips"]) == 1,
              {"works": len(dump["works"]), "clips": len(dump["clips"])})
        check("원본 음성 Blob이 실제로 저장됨", dump["clips"] and dump["clips"][0]["bytes"] > 0,
              dump["clips"][0] if dump["clips"] else None)

        # --- 2편: 같은 장면에서 두 번 녹음 + 재시작 경쟁 ---
        page.click("#mvAlbumBtn")
        page.wait_for_timeout(600)
        page.click("#newStoryBtn")
        page.wait_for_timeout(1300)
        # 중립 시작이므로 자막·장면을 남기려면 직접 입력한 문장이 필요하다(내보내기 자막 검증용)
        page.fill("#sayInput", "우주선을 타고 하늘로 날아갔어")
        page.press("#sayInput", "Enter")
        page.wait_for_timeout(500)
        page.click("#micBtn"); page.wait_for_timeout(1200)
        page.click("#micBtn"); page.wait_for_timeout(900)
        page.click("#micBtn"); page.wait_for_timeout(1200)
        page.click("#micBtn"); page.wait_for_timeout(900)
        takes = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>(s.takes||[]).length)")
        durs = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>s.audioDur)")
        ids = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>(s.takes||[]).map(t=>t.clipId))")
        REPORT["data"]["multi_take"] = {"takes": takes, "durs": durs}
        check("같은 장면 두 번 녹음 → 테이크 2개 보존(덮어쓰지 않음)", takes and takes[0] == 2, takes)
        check("장면 음성 길이 = 테이크 합(상한 없음)", durs and durs[0] >= 2.0, durs)

        # 빠른 켜기/끄기 3회 → 세션 섞임 없이 3개 더 쌓이는가
        for _ in range(3):
            page.click("#micBtn"); page.wait_for_timeout(500)
            page.click("#micBtn"); page.wait_for_timeout(700)
        tight = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>(s.takes||[]).length)")
        REPORT["data"]["tight_takes"] = tight
        check("빠른 재시작에도 테이크가 모두 따로 남음", tight and tight[0] >= 4, tight)

        # 녹음 중에 종료 → 마지막 목소리까지 저장되는가
        page.click("#micBtn"); page.wait_for_timeout(1300)
        cap2 = end_and_capture(page)
        check("녹음 중 종료도 즉시 SAVING 표시", cap2["phase"] == "SAVING" and cap2["overlay"], cap2)
        wait_phase(page, "SAVED_COMPLETE", 12000)
        page.wait_for_timeout(600)
        mic_end = page.evaluate("window.__DOHA.mic()")
        rec2 = page.evaluate("()=>{const a=window.__DOHA.album(); return a.map(w=>({id:w.id,no:w.no,caps:w.scenes.map(s=>s.caption),clipIds:w.scenes.map(s=>s.clipIds||[]),durs:w.scenes.map(s=>s.audioDur||0)}));}")
        dump2 = page.evaluate(IDB_DUMP)
        REPORT["data"]["rec2"] = rec2
        check("녹음 중 종료: 마이크 정지·유실 0", mic_end["on"] is False and mic_end["losses"] == 0, mic_end)
        check("녹음 중 종료: 마지막 테이크까지 첫 장면에 붙음",
              len(rec2[0]["clipIds"][0]) >= 5, rec2[0]["clipIds"][0])
        own_clips = [c for c in dump2["clips"] if c["workId"] == rec2[0]["id"]]
        check("저장된 테이크 수만큼 clips 저장",
              len(own_clips) == sum(len(x) for x in rec2[0]["clipIds"]),
              {"clips": len(own_clips), "takes": sum(len(x) for x in rec2[0]["clipIds"])})

        # --- 새로고침 후 복원 ---
        page.reload()
        page.wait_for_timeout(1300)
        page.click("#albumBtn")
        page.wait_for_timeout(800)
        n_after_reload = cards(page)
        check("새로고침 뒤 내 기록 2편", n_after_reload == 2, n_after_reload)
        page.eval_on_selector_all(CARD_SEL, "els=>els[0].click()")
        page.wait_for_timeout(1800)
        restored = page.evaluate("""()=>({title:document.querySelector('#introTitle').textContent,
            takes:window.__DOHA.state.movie.scenes.map(s=>(s.takes||[]).length),
            audio:window.__DOHA.state.movie.scenes.filter(s=>!!s.audio).length})""")
        REPORT["data"]["restored"] = restored
        check("복원된 기록의 테이크가 모두 되살아남", sum(restored["takes"]) >= 5 and restored["audio"] >= 1, restored)

        # --- 내보내기: 개별 ---
        page.click("#mvAlbumBtn")
        page.wait_for_timeout(700)
        with page.expect_download() as dl:
            page.click(BTN_SEL)
        d = dl.value
        path = d.path()
        data = json.load(open(path, encoding="utf-8"))
        REPORT["data"]["export_one"] = {"file": d.suggested_filename, "manifest": data.get("manifest")}
        rec0 = data["works"][0]["record"]
        check("개별 내보내기 파일명 규칙", d.suggested_filename.startswith("PROJECT-DOHA_No") and d.suggested_filename.endswith(".json"),
              d.suggested_filename)
        check("내보내기 형식/버전 표기", data.get("app") == "PROJECT DOHA" and data.get("formatVersion") == "0.1.4", data.get("formatVersion"))
        check("내보내기에 장면·자막 포함", len(rec0["scenes"]) == 1 and all(s["caption"] for s in rec0["scenes"]),
              rec0["scenes"][0]["caption"] if rec0["scenes"] else None)
        check("내보내기에 원본 음성 데이터 포함(data:audio)",
              len(data["works"][0]["audio"]) > 0 and all(a["dataUrl"].startswith("data:audio") for a in data["works"][0]["audio"]),
              len(data["works"][0]["audio"]))
        check("manifest 음성 개수 = 실제 음성 개수",
              data["manifest"]["audioClipCount"] == len(data["works"][0]["audio"]), data["manifest"])

        # --- 내보내기: 전체 ---
        with page.expect_download() as dl2:
            page.eval_on_selector_all(".al-tools .al-name", "els=>els[els.length-1].click()")
        d2 = dl2.value
        all_data = json.load(open(d2.path(), encoding="utf-8"))
        REPORT["data"]["export_all"] = {"file": d2.suggested_filename, "manifest": all_data.get("manifest")}
        check("전체 내보내기 파일명", d2.suggested_filename.startswith("PROJECT-DOHA_all_"), d2.suggested_filename)
        check("전체 내보내기 = 내 기록 전부", all_data["manifest"]["workCount"] == n_after_reload and len(all_data["works"]) == n_after_reload,
              all_data["manifest"])

        # --- 삭제: 취소하면 그대로 ---
        page.dialog_policy["confirm"] = False
        before = cards(page)
        page.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card-actions .al-card-btn.del", "els=>els[0].click()")
        page.wait_for_timeout(600)
        check("삭제 확인을 취소하면 기록 유지", cards(page) == before, {"before": before, "after": cards(page)})

        # --- 삭제: 확인하면 기록·음성 함께 삭제 ---
        victim = page.evaluate("()=>window.__DOHA.album()[0]")
        page.dialog_policy["confirm"] = True
        page.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card-actions .al-card-btn.del", "els=>els[0].click()")
        page.wait_for_timeout(900)
        after_del = cards(page)
        dump3 = page.evaluate(IDB_DUMP)
        REPORT["data"]["delete"] = {"victim": victim["id"], "cards_after": after_del,
                                    "works": [w["id"] for w in dump3["works"]],
                                    "clips_left": [c for c in dump3["clips"] if c["workId"] == victim["id"]]}
        check("삭제하면 카드가 줄어든다", after_del == before - 1, {"before": before, "after": after_del})
        check("삭제한 기록이 IndexedDB works에서 사라짐", all(w["id"] != victim["id"] for w in dump3["works"]),
              [w["id"] for w in dump3["works"]])
        check("삭제한 기록의 원본 음성도 함께 삭제", all(c["workId"] != victim["id"] for c in dump3["clips"]))

        # --- 지운 작품을 다시 저장하면 지운 id가 아니라 새 기록으로 남는다 ---
        before_ids = page.evaluate("()=>window.__DOHA.album().map(w=>w.id)")
        page.evaluate("()=>window.__DOHA.saveEntry(true)")
        page.wait_for_timeout(900)
        after_ids = page.evaluate("()=>window.__DOHA.album().map(w=>w.id)")
        check("지운 작품을 다시 저장해도 지운 id는 되살아나지 않고 새 기록으로 남음",
              victim["id"] not in after_ids and len(after_ids) == len(before_ids) + 1,
              {"before": before_ids, "after": after_ids, "victim": victim["id"]})

        # --- 40초 상한: 42초 녹음도 잘리지 않는가 ---
        page.click("#newStoryBtn")
        page.wait_for_timeout(1300)
        page.click("#micBtn")
        page.wait_for_timeout(42000)
        page.click("#micBtn")
        page.wait_for_timeout(2500)
        long_dur = page.evaluate("()=>window.__DOHA.state.scenes.map(s=>s.audioDur)")
        REPORT["data"]["long_take"] = long_dur
        check("42초 녹음이 40초로 잘리지 않음", long_dur and long_dur[0] > 40, long_dur)

        check("세션 A 런타임 에러 0건", not errs, errs)
        check("세션 A 콘솔 에러 0건", not cerrs, cerrs)
        page.screenshot(path="/workspace/tmp/shots/v012-main.png")
        ctx.close()
        browser.close()

        # ================= 세션 C: IndexedDB 불가 → SAVED_TEXT_ONLY =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script="""
            Object.defineProperty(window,'indexedDB',{get:function(){return undefined;}});
        """)
        page.goto(url); page.wait_for_timeout(800)
        page.click("#startBtn"); page.wait_for_timeout(1200)
        page.click("#micBtn"); page.wait_for_timeout(1500)
        end_and_capture(page)
        wait_phase(page, "SAVED_TEXT_ONLY", 10000)
        page.wait_for_timeout(700)
        c = page.evaluate("""()=>({phase:window.__DOHA.saveState().phase,
            noticeHidden:document.querySelector('#saveNotice').hidden,
            noticeClass:document.querySelector('#saveNotice').className,
            noticeText:document.querySelector('#saveNoticeText').textContent,
            screen:window.__DOHA.state.screen, album:window.__DOHA.album().length})""")
        REPORT["data"]["text_only"] = c
        check("IndexedDB 불가 → SAVED_TEXT_ONLY", c["phase"] == "SAVED_TEXT_ONLY", c["phase"])
        check("SAVED_TEXT_ONLY는 완전 저장으로 표시하지 않음(안내 배너)", c["noticeHidden"] is False and "음성" in c["noticeText"], c["noticeText"][:120])
        check("기록(장면·자막)은 앨범에 남음", c["album"] == 1 and c["screen"] == "movie", c)
        with page.expect_download() as dl3:
            page.click("#saveDownloadBtn")
        tdata = json.load(open(dl3.value.path(), encoding="utf-8"))
        check("음성 저장 실패 시 파일 내려받기로 원본 보존 가능", len(tdata["works"][0]["audio"]) >= 1,
              tdata["manifest"])
        page.reload(); page.wait_for_timeout(1200)
        page.click("#albumBtn"); page.wait_for_timeout(600)
        check("IndexedDB 불가 환경에서도 새로고침 뒤 기록 유지(localStorage)", cards(page) == 1, cards(page))
        check("세션 C 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close(); browser.close()

        # ================= 세션 D: 저장 완전 실패 → SAVE_FAILED =================
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_page(browser, init_script="""
            Object.defineProperty(window,'indexedDB',{get:function(){return undefined;}});
            Storage.prototype.setItem=function(){ throw new Error('QuotaExceededError'); };
        """)
        page.goto(url); page.wait_for_timeout(800)
        page.click("#startBtn"); page.wait_for_timeout(1200)
        page.fill("#sayInput", "저장 실패 검증용 문장")
        page.press("#sayInput", "Enter")
        page.wait_for_timeout(400)
        page.click("#micBtn"); page.wait_for_timeout(1500)
        end_and_capture(page)
        wait_phase(page, "SAVE_FAILED", 8000)
        page.wait_for_timeout(600)
        f = page.evaluate("""()=>({phase:window.__DOHA.saveState().phase, reason:window.__DOHA.saveState().reason,
            album:window.__DOHA.album().length, screen:window.__DOHA.state.screen,
            noticeHidden:document.querySelector('#saveNotice').hidden,
            noticeClass:document.querySelector('#saveNotice').className,
            noticeText:document.querySelector('#saveNoticeText').textContent})""")
        REPORT["data"]["save_failed"] = f
        check("저장 완전 실패 → SAVE_FAILED", f["phase"] == "SAVE_FAILED", f)
        check("실패한 기록을 앨범(내 기록)에 넣지 않음", f["album"] == 0, f["album"])
        check("실패해도 영화 화면은 열리고 실패 배너 표시", f["screen"] == "movie" and f["noticeHidden"] is False and "failed" in f["noticeClass"], f["noticeText"][:120])
        with page.expect_download() as dl4:
            page.click("#saveDownloadBtn")
        fdata = json.load(open(dl4.value.path(), encoding="utf-8"))
        check("실패 직후 파일로 내려받기 가능(기록 보존)", fdata["works"][0]["record"]["scenes"][0]["caption"] != "",
              fdata["manifest"])
        check("실패해도 내려받은 파일에 메모리 원본 음성 포함", len(fdata["works"][0]["audio"]) >= 1, fdata["manifest"])
        check("세션 D 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close(); browser.close()

        # ================= 세션 E: v0.1 localStorage 이관 안전성 =================
        seed = """
            localStorage.setItem('doha.v01.album', JSON.stringify([
              {mine:true,id:'old-1',date:'2026-11-01',title:'옛 기록 하나',one:'공룡이 왔어',captions:['공룡이 왔어','더 커졌어'],tags:['공룡'],dur:30,note:'옛 메모'}
            ]));
        """
        browser = pw.chromium.launch()
        ctx, page, errs, cerrs = new_page(browser, init_script=seed, perms=())
        page.goto(url); page.wait_for_timeout(1500)
        legacy_after = page.evaluate("()=>({legacy:localStorage.getItem('doha.v01.album'), album:window.__DOHA.album().map(w=>({id:w.id,caps:w.scenes.map(s=>s.caption)}))})")
        REPORT["data"]["migrate_ok"] = legacy_after
        check("v0.1 기록이 IndexedDB로 이관됨", any(w["id"] == "legacy-old-1" for w in legacy_after["album"]), legacy_after["album"])
        check("이관 확인 뒤에만 v0.1 원본 삭제", legacy_after["legacy"] in (None, "[]"), legacy_after["legacy"])
        ctx.close(); browser.close()

        # 이관이 실패하는 환경(IndexedDB·localStorage 모두 불가)에서는 원본을 지우지 않는다
        browser = pw.chromium.launch()
        ctx, page, errs, cerrs = new_page(browser, init_script=seed + """
            Object.defineProperty(window,'indexedDB',{get:function(){return undefined;}});
            Storage.prototype.setItem=function(){ throw new Error('QuotaExceededError'); };
        """, perms=())
        page.goto(url); page.wait_for_timeout(1500)
        kept = page.evaluate("()=>localStorage.getItem('doha.v01.album')")
        REPORT["data"]["migrate_fail_kept"] = kept
        check("이관 저장이 확인되지 않으면 v0.1 원본을 지우지 않음", kept and "옛 기록 하나" in kept, (kept or "")[:120])
        check("세션 E 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close(); browser.close()

        # ================= 세션 F: v0.1.1이 저장한 모양(clipId 단일)의 기록도 열리는가 =================
        browser = pw.chromium.launch()
        ctx, page, errs, cerrs = new_page(browser, perms=())
        page.goto(url); page.wait_for_timeout(900)
        page.evaluate("""() => new Promise((res,rej)=>{
            const rq=indexedDB.open('doha-universe',1);
            rq.onupgradeneeded=()=>{ const db=rq.result;
              if(!db.objectStoreNames.contains('works')){ const w=db.createObjectStore('works',{keyPath:'id'}); w.createIndex('createdAt','createdAt'); }
              if(!db.objectStoreNames.contains('clips')) db.createObjectStore('clips',{keyPath:'id'}); };
            rq.onerror=()=>rej(String(rq.error));
            rq.onsuccess=()=>{
              const db=rq.result, id='v011-1';
              const t=db.transaction(['works','clips'],'readwrite');
              t.objectStore('works').put({id:id,no:7,createdAt:Date.now()-86400000,date:'2026-11-24',
                title:'어제 저장한 기록',styleId:'3d',tags:['공룡'],one:'옛 자막 2',note:'',dur:12,
                scenes:[{key:'living',caption:'옛 자막 1',tint:false,at:0,styleId:'3d',audioDur:2.5,clipId:id+'-s0'},
                        {key:'giant',caption:'옛 자막 2',tint:false,at:5,styleId:'3d',audioDur:0,clipId:null}],
                obs:[],questions:[]});
              t.objectStore('clips').put({id:id+'-s0',workId:id,type:'audio/mp4',blob:new Blob([new Uint8Array(8000)],{type:'audio/mp4'})});
              t.oncomplete=()=>res(true); t.onerror=()=>rej(String(t.error));
            };
        })""")
        page.reload(); page.wait_for_timeout(1400)
        page.click("#albumBtn"); page.wait_for_timeout(700)
        legacy_cards = cards(page)
        page.eval_on_selector_all(CARD_SEL, "els=>els[0].click()")
        page.wait_for_timeout(1600)
        old = page.evaluate("""()=>({title:document.querySelector('#introTitle').textContent,
            caps:window.__DOHA.state.movie.scenes.map(s=>s.caption),
            audio:window.__DOHA.state.movie.scenes.filter(s=>!!s.audio).length,
            dur:window.__DOHA.state.movie.scenes.map(s=>s.audioDur)})""")
        REPORT["data"]["legacy_v011"] = old
        check("v0.1.1 기록이 앨범에 보임", legacy_cards == 1, legacy_cards)
        check("v0.1.1 모양(clipId 단일) 기록도 열리고 목소리·길이 복원",
              old["caps"] == ["옛 자막 1", "옛 자막 2"] and old["audio"] == 1 and old["dur"][0] >= 2.5, old)
        check("세션 F 런타임·콘솔 에러 0건", not errs and not cerrs, errs or cerrs)
        ctx.close(); browser.close()

    if httpd:
        httpd.shutdown()
    ok = all(c["ok"] for c in REPORT["checks"])
    print("\n=== RESULT:", "ALL PASS" if ok else "FAILED", "===")
    print(json.dumps(REPORT["data"], ensure_ascii=False, indent=1, default=str)[:6000])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    os.makedirs("/workspace/tmp/shots", exist_ok=True)
    main()
