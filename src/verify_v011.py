#!/usr/bin/env python3
"""PROJECT DOHA v0.1.1부터 이어진 P0 회귀 검증 (headless Chromium, 현재 통합 빌드 v0.1.3 대상).

검증 항목
 1) 같은 날 2편 연속 저장 → 두 편 모두 남는가
 2) 새로고침 후 앨범에서 과거 편을 누르면 그 편의 장면·자막·목소리가 복원되는가
 3) 이야기 종료·화면 이탈·탭 숨김 시 마이크 트랙이 즉시 정지되는가
 4) 마이크 권한 거부 시 state.micOn=false / '듣는 중' 표시가 남지 않는가
 5) 런타임 에러 0건
사용: LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu python3 project-doha/src/verify_v011.py
"""
import json
import os
import shutil
import tempfile
from playwright.sync_api import sync_playwright

URL = os.environ.get("DOHA_URL", "file:///workspace/project-doha/index.html")
PROFILE = tempfile.mkdtemp(prefix="doha-verify-")
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
REPORT = {"checks": [], "data": {}}


def check(name, ok, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + ("  · " + str(detail) if detail else ""))


def new_ctx(browser, width=1180, height=820, mobile=False, perms=("microphone",)):
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=2,
        is_mobile=mobile,
        has_touch=True,
        permissions=list(perms),
    )
    page = ctx.new_page()
    errs, cerrs = [], []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: d.accept())   # v0.1.3: 녹음 전 보호자·아이 동의 확인
    return ctx, page, errs, cerrs


def main():
    with sync_playwright() as pw:
        # ---------- 세션 A: 마이크 허용 + 저장/복원 ----------
        browser = pw.chromium.launch(args=FAKE)
        ctx, page, errs, cerrs = new_ctx(browser)
        page.goto(URL)
        page.wait_for_timeout(1000)

        check("초기 화면: 런타임 에러 없음", not errs and not cerrs, errs or cerrs)
        check("초기 상태 문구가 '듣는 중'이 아님",
              "듣는 중" not in page.eval_on_selector("#statusText", "e=>e.textContent"))
        # 실명은 저장소·테스트에 적지 않는다(AGENTS.md). 기본값이 중립 이름인지만 확인한다.
        leftovers = page.evaluate("""() => {
            const t = document.body.innerText.includes('[[NAME]]');
            const ph = Array.from(document.querySelectorAll('[placeholder]')).some(e => (e.getAttribute('placeholder')||'').includes('[[NAME]]'));
            return {token:t, placeholder:ph, defaultName:window.__DOHA.nameOf()};
        }""")
        check("이름 토큰이 화면·placeholder에 남지 않고 기본 이름은 중립값",
              (not leftovers["token"]) and (not leftovers["placeholder"]) and leftovers["defaultName"] == "아이",
              leftovers)

        # 1편
        page.click("#startBtn")
        page.wait_for_timeout(1400)
        page.click("#micBtn")
        page.wait_for_timeout(1200)
        mic_on = page.evaluate("window.__DOHA.mic()")
        REPORT["data"]["mic_after_start"] = mic_on
        check("마이크 켜짐: 트랙 live", mic_on["on"] and mic_on["tracks"] == ["live"], mic_on)

        page.eval_on_selector("#chipRow", "e=>{e.parentElement.open=true;}")   # v0.1.3: 예시 칩은 접힌 목록 안에 있다
        page.wait_for_timeout(200)
        page.query_selector_all("#chipRow .chip")[3].click()   # 하늘이 보라색으로
        page.wait_for_timeout(1100)
        page.query_selector_all("#chipRow .chip")[4].click()   # 우주선
        page.wait_for_timeout(1200)
        caps_a = page.evaluate("window.__DOHA.state.scenes.map(s=>s.caption)")
        page.click("#endBtn")
        page.wait_for_timeout(1600)
        mic_after_end = page.evaluate("window.__DOHA.mic()")
        REPORT["data"]["mic_after_end"] = mic_after_end
        check("이야기 종료 시 마이크 정지(state.micOn=false)",
              mic_after_end["on"] is False, mic_after_end)
        check("이야기 종료 시 트랙이 모두 ended",
              all(t == "ended" for t in mic_after_end["tracks"]) and mic_after_end["tracks"] != [],
              mic_after_end)
        check("종료 후 마이크 버튼에 listening 표시 없음",
              page.eval_on_selector("#micBtn", "e=>!e.classList.contains('listening')"))
        title_a = page.inner_text("#introTitle")
        page.wait_for_timeout(900)
        page.click("#saveAlbumBtn")
        page.wait_for_timeout(700)
        mine_after_first = page.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card:not(.al-add)", "els=>els.length")
        check("1편 저장 후 내 기록 1편", mine_after_first == 1, mine_after_first)

        # 2편 (같은 날)
        page.click("#newStoryBtn")
        page.wait_for_timeout(1500)
        page.eval_on_selector("#chipRow", "e=>{e.parentElement.open=true;}")
        page.wait_for_timeout(200)
        page.query_selector_all("#chipRow .chip")[2].click()   # 더 크게
        page.wait_for_timeout(1200)
        page.fill("#sayInput", "공룡이 라면을 끓였어!")
        page.press("#sayInput", "Enter")
        page.wait_for_timeout(1200)
        caps_b = page.evaluate("window.__DOHA.state.scenes.map(s=>s.caption)")
        page.click("#endBtn")
        page.wait_for_timeout(1500)
        title_b = page.inner_text("#introTitle")
        page.wait_for_timeout(600)
        page.click("#mvAlbumBtn")
        page.wait_for_timeout(800)

        mine_cards = page.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card:not(.al-add)", "els=>els.length")
        sample_cards = page.eval_on_selector_all(".al-grid-samples .al-card", "els=>els.length")
        albums = page.evaluate("window.__DOHA.album().map(e=>({id:e.id,no:e.no,title:e.title,caps:e.scenes.map(s=>s.caption),clips:e.scenes.filter(s=>s.clipId).length}))")
        REPORT["data"]["mine_cards"] = mine_cards
        REPORT["data"]["sample_cards"] = sample_cards
        REPORT["data"]["albums"] = albums
        check("같은 날 2편 저장 → 내 기록 2편 유지", mine_cards == 2, mine_cards)
        check("샘플 3편은 별도 영역", sample_cards == 3, sample_cards)
        check("내 기록 편수 문구에 샘플 미포함",
              page.inner_text("#alCount").startswith("내 상상 영화 2편"), page.inner_text("#alCount"))
        check("예시 카드에 '예시' 배지 표시",
              page.eval_on_selector_all(".al-grid-samples .al-ex", "els=>els.length") == 3)
        check("두 작품의 id가 서로 다름", len({a["id"] for a in albums}) == len(albums), [a["id"] for a in albums])
        # v0.1.3: 목소리는 '예시 그림' 장면에 붙이지 않고 자막 없는 중립 장면에 따로 남는다.
        # 그래서 자막 비교는 빈 자막(음성 전용 장면)을 빼고 한다.
        honest = lambda caps: [c for c in caps if c]
        check("두 작품의 자막이 서로 보존됨",
              honest(albums[0]["caps"]) == honest(caps_b) and honest(albums[1]["caps"]) == honest(caps_a),
              {"expected_b": caps_b, "got_b": albums[0]["caps"], "expected_a": caps_a, "got_a": albums[1]["caps"]})
        check("원본 음성이 장면에 저장됨(clipId)", any(a["clips"] > 0 for a in albums),
              [(a["no"], a["clips"]) for a in albums])

        # 새로고침 후 과거 편(1편) 열기
        page.reload()
        page.wait_for_timeout(1400)
        page.click("#albumBtn")
        page.wait_for_timeout(900)
        after_reload = page.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card:not(.al-add)", "els=>els.length")
        check("새로고침 후에도 내 기록 2편", after_reload == 2, after_reload)
        page.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card:not(.al-add)", "els=>els[1].click()")
        page.wait_for_timeout(1800)
        restored_title = page.inner_text("#introTitle")
        restored = page.evaluate("({caps:window.__DOHA.state.movie.scenes.map(s=>s.caption), audio:window.__DOHA.state.movie.scenes.filter(s=>!!s.audio).length, dots:document.querySelectorAll('#mvDots i').length})")
        REPORT["data"]["restored"] = {"title": restored_title, **restored}
        check("새로고침 후 과거 편이 그 편으로 열림", restored_title == title_a,
              {"clicked": title_a, "opened": restored_title, "second": title_b})
        check("복원된 자막이 저장 당시와 같음", [c for c in restored["caps"] if c] == caps_a,
              {"expected": caps_a, "got": restored["caps"]})
        check("복원된 목소리가 재생 가능", restored["audio"] > 0, restored["audio"])
        check("장면 점 개수 = 인트로+장면+아웃트로",
              restored["dots"] == len(restored["caps"]) + 2, {"dots": restored["dots"], "scenes": len(restored["caps"])})
        check("앨범 카드 클릭 시 '예시' 토스트가 뜨지 않음",
              "/예시" not in page.inner_text("#toast") or "내 기록" in page.inner_text("#toast"),
              page.inner_text("#toast"))

        # 화면 이탈로 마이크 정지
        page.click("#mvBack")
        page.wait_for_timeout(700)
        page.click("#startBtn")
        page.wait_for_timeout(1400)
        page.click("#micBtn")
        page.wait_for_timeout(1100)
        before_leave = page.evaluate("window.__DOHA.mic()")
        page.click("#cvBack")
        page.wait_for_timeout(600)
        after_leave = page.evaluate("window.__DOHA.mic()")
        REPORT["data"]["mic_exit"] = {"before": before_leave, "after": after_leave}
        check("화면 이탈(cvBack) 시 마이크 정지",
              before_leave["on"] and not after_leave["on"] and all(t == "ended" for t in after_leave["tracks"]),
              {"before": before_leave, "after": after_leave})

        # 탭 숨김으로 마이크 정지
        page.click("#albumBtn")
        page.wait_for_timeout(500)
        page.click("#newStoryBtn")
        page.wait_for_timeout(1400)
        page.click("#micBtn")
        page.wait_for_timeout(1100)
        hidden_before = page.evaluate("window.__DOHA.mic()")
        page.evaluate("""() => {
            Object.defineProperty(document, 'hidden', {value:true, configurable:true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.wait_for_timeout(400)
        hidden_after = page.evaluate("window.__DOHA.mic()")
        REPORT["data"]["mic_hidden"] = {"before": hidden_before, "after": hidden_after}
        check("탭 숨김(visibilitychange) 시 마이크 정지",
              hidden_before["on"] and not hidden_after["on"] and all(t == "ended" for t in hidden_after["tracks"]),
              {"before": hidden_before, "after": hidden_after})

        check("세션 A 런타임 에러 0건", not errs, errs)
        check("세션 A 콘솔 에러 0건", not cerrs, cerrs)
        page.screenshot(path="/workspace/tmp/shots/v011-album.png")
        ctx.close()
        browser.close()

        # ---------- 세션 B: 마이크 권한 거부 ----------
        browser2 = pw.chromium.launch()
        ctx2, page2, errs2, cerrs2 = new_ctx(browser2, perms=())
        page2.goto(URL)
        page2.wait_for_timeout(900)
        page2.click("#startBtn")
        page2.wait_for_timeout(1400)
        page2.click("#micBtn")
        page2.wait_for_timeout(1500)
        denied = page2.evaluate("window.__DOHA.mic()")
        ui = page2.evaluate("""() => ({
            listening: document.querySelector('#micBtn').classList.contains('listening'),
            off: document.querySelector('#micBtn').classList.contains('off'),
            status: document.querySelector('#statusText').textContent,
            waveFlat: document.querySelector('#wave').classList.contains('flat'),
            statusIdle: document.querySelector('#status').classList.contains('idle'),
            aria: document.querySelector('#micBtn').getAttribute('aria-label')
        })""")
        REPORT["data"]["denied"] = {"mic": denied, "ui": ui}
        check("권한 거부 시 state.micOn=false", denied["on"] is False, denied)
        check("권한 거부 시 '듣는 중' 표시가 남지 않음",
              (not ui["listening"]) and ("듣는 중" not in ui["status"]), ui)
        check("권한 거부 시 텍스트/대기 모드 문구 표시",
              ("텍스트" in ui["status"] or "대기" in ui["status"]), ui["status"])

        # 거부 상태에서도 저장·복원 정상
        page2.eval_on_selector("#chipRow", "e=>{e.parentElement.open=true;}")
        page2.wait_for_timeout(200)
        page2.query_selector_all("#chipRow .chip")[2].click()
        page2.wait_for_timeout(1100)
        # v0.1.3: 예시 장면만으로는 저장하지 않는다 → 직접 입력한 문장을 하나 남긴다
        page2.fill("#sayInput", "마이크 없이도 상상은 이어져요")
        page2.press("#sayInput", "Enter")
        page2.wait_for_timeout(600)
        page2.click("#endBtn")
        page2.wait_for_timeout(1200)
        mic_end_denied = page2.evaluate("window.__DOHA.mic()")
        check("권한 거부 상태로 종료해도 에러 없이 영화 생성",
              page2.eval_on_selector("#s-movie", "e=>e.classList.contains('on')") and mic_end_denied["on"] is False,
              mic_end_denied)
        page2.click("#mvAlbumBtn")
        page2.wait_for_timeout(700)
        denied_cards = page2.eval_on_selector_all(".al-grid:not(.al-grid-samples) .al-card:not(.al-add)", "els=>els.length")
        check("권한 거부 세션에서도 기록 1편 저장", denied_cards == 1, denied_cards)
        check("세션 B 런타임 에러 0건", not errs2, errs2)
        check("세션 B 콘솔 에러 0건", not cerrs2, cerrs2)
        page2.screenshot(path="/workspace/tmp/shots/v011-denied.png")
        ctx2.close()
        browser2.close()

    ok = all(c["ok"] for c in REPORT["checks"])
    print("\n=== RESULT:", "ALL PASS" if ok else "FAILED", "===")
    print(json.dumps(REPORT["data"], ensure_ascii=False, indent=1, default=str))
    shutil.rmtree(PROFILE, ignore_errors=True)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    os.makedirs("/workspace/tmp/shots", exist_ok=True)
    main()
