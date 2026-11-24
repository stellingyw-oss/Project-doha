"""Run with python3 tests/verify_safety.py and a system Chromium plus Playwright."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

APP = Path(__file__).resolve().parents[1] / "index.html"
URL = "http://localhost:8765/index.html"
MIC = "#micBtn"


def launch_page(browser, fixture=""):
    page = browser.new_page(accept_downloads=True, viewport={"width": 1024, "height": 768})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    if fixture:
        page.add_init_script(fixture)
    page.route(URL, lambda route: route.fulfill(path=APP, content_type="text/html"))
    page.goto(URL)
    return page, errors


def start(page):
    page.click("#startBtn")


def type_line(page, text):
    page.fill("#sayInput", text)
    page.press("#sayInput", "Enter")


def finish(page, expected="SAVED_COMPLETE"):
    page.click("#endBtn")
    expect(page.locator("#s-movie")).to_be_visible()
    assert page.evaluate("__DOHA.saveState().phase") == expected


def begin_capture(page):
    page.click(MIC)
    page.wait_for_function("__DOHA.mic().on")
    page.wait_for_timeout(350)


def verify():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("CHROMIUM", "/usr/bin/chromium"),
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        )
        print("Chromium", browser.version, flush=True)
        page, errors = launch_page(browser)
        start(page)
        assert page.locator("#stage .frame").count() == 0
        expect(page.get_by_text("예시 장면 둘러보기", exact=True)).to_be_visible()
        expect(page.get_by_text("음성 자동 자막", exact=False)).to_be_visible()
        page.get_by_text("예시 장면 둘러보기", exact=True).click()
        page.locator("#chipRow button").nth(1).click()
        expect(page.locator("#capText")).to_contain_text("예시 그림")
        page.get_by_text("예시 장면 둘러보기", exact=True).click()
        type_line(page, "가상의 파란 기차")
        assert page.locator("#stage .frame.on img[src]").count() == 0
        begin_capture(page)
        page.click(MIC)
        page.wait_for_function("!__DOHA.mic().stopping")
        begin_capture(page)
        page.click(MIC)
        finish(page)
        expect(page.locator("#originalAudio audio")).to_have_count(2)
        for link in page.get_by_role("link", name="다운로드").all():
            with page.expect_download() as event:
                link.click()
            assert event.value.path().stat().st_size > 0
        page.click("#againBtn")
        type_line(page, "가상의 두 번째 기록")
        begin_capture(page)
        finish(page)
        page.reload()
        page.click("#albumBtn")
        cards = page.locator(".al-card-wrap")
        expect(cards).to_have_count(2)
        records = page.evaluate("__DOHA.album()")
        assert records[0]["date"] == records[1]["date"] and records[0]["no"] != records[1]["no"]
        with page.expect_download() as event:
            cards.nth(1).get_by_text("기록 + 음성 JSON").click()
        payload = json.loads(event.value.path().read_text())
        assert [part["takeIndex"] for part in payload["works"][0]["audio"]] == [0, 1]
        with page.expect_download() as event:
            cards.nth(1).get_by_text("기록 정보 JSON").click()
        metadata = json.loads(event.value.path().read_text())
        assert not metadata["works"][0]["audio"]
        assert metadata["works"][0]["record"]["one"] == "가상의 파란 기차"
        cards.nth(1).locator(".al-card").click()
        expect(page.locator("#originalAudio audio")).to_have_count(2)
        page.locator("#originalAudio audio").first.evaluate("(audio) => audio.play()")
        assert not page.locator("#originalAudio audio").first.evaluate("(audio) => audio.paused")
        page.click("#mvAlbumBtn")
        cards.nth(1).get_by_text("삭제", exact=True).click()
        expect(cards).to_have_count(1)
        cards.first.locator(".al-card").click()
        expect(page.locator("#originalAudio audio")).to_have_count(1)
        assert not errors, errors
        print("PASS neutral, labels, real MediaRecorder start/stop, immediate end, multiple segments, raw/JSON downloads, same-day records, reload, replay, delete isolation", flush=True)
        page.close()

        cases = {
            "permission denial": "navigator.mediaDevices.getUserMedia=()=>Promise.reject(new DOMException('denied','NotAllowedError'));",
            "late permission": """const get=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                navigator.mediaDevices.getUserMedia=async (...args)=>{const stream=await get(...args);
                window.lateStream=stream; await new Promise(resolve=>window.releasePermission=resolve); return stream;};""",
            "empty blob": """MediaRecorder.prototype.start=function(){};
                Object.defineProperty(MediaRecorder.prototype,'state',{get(){return 'recording';}});
                MediaRecorder.prototype.stop=function(){this.onstop();};""",
            "recorder error": """const start=MediaRecorder.prototype.start;
                MediaRecorder.prototype.start=function(){start.call(this);setTimeout(()=>this.onerror(),150);};""",
            "transaction abort": """const put=IDBObjectStore.prototype.put;
                IDBObjectStore.prototype.put=function(value){const req=put.call(this,value);
                if(this.name==='clips')this.transaction.abort();return req;};""",
            "total storage failure": """Object.defineProperty(window,'indexedDB',{value:null});
                Storage.prototype.setItem=function(){throw new DOMException('test','QuotaExceededError');};""",
            "quota and migration": """const legacy=[{mine:true,title:'가상의 이전 기록',one:'합성 문장'}];
                localStorage.setItem('doha.v01.album',JSON.stringify(legacy));
                const put=IDBObjectStore.prototype.put;
                IDBObjectStore.prototype.put=function(){this.transaction.abort();throw new DOMException('test','QuotaExceededError');};""",
        }
        for name, fixture in cases.items():
            page, errors = launch_page(browser, fixture)
            start(page)
            type_line(page, "검증용 문장")
            if name == "permission denial":
                page.click(MIC)
                page.wait_for_function("__DOHA.mic().denied")
                assert not page.evaluate("__DOHA.mic().on")
            elif name == "late permission":
                page.click(MIC)
                page.wait_for_function("typeof window.releasePermission === \"function\"")
                page.click("#cvBack")
                page.evaluate("window.releasePermission()")
                page.wait_for_function("lateStream.getTracks().every(track=>track.readyState==='ended')")
                assert not page.evaluate("__DOHA.mic().on")
            elif name in ("empty blob", "recorder error"):
                page.click(MIC)
                if name == "empty blob":
                    page.wait_for_function("__DOHA.mic().on")
                    page.click(MIC)
                page.wait_for_function("__DOHA.mic().losses === 1")
                finish(page)
                expect(page.locator("#originalAudio")).to_contain_text("녹음 중 오류")
                assert page.evaluate("__DOHA.mic().tracks.every(track=>track==='ended')")
            elif name == "transaction abort":
                begin_capture(page)
                finish(page, "SAVED_TEXT_ONLY")
                expect(page.locator("#saveNotice")).to_contain_text("원본 음성")
                expect(page.locator("#originalAudio audio")).to_have_count(1)
            elif name == "total storage failure":
                begin_capture(page)
                finish(page, "SAVE_FAILED")
                expect(page.locator("#originalAudio audio")).to_have_count(1)
                assert not page.evaluate("__DOHA.album().length")
                with page.expect_download() as event:
                    page.click("#saveDownloadBtn")
                recovery = json.loads(event.value.path().read_text())
                assert recovery["manifest"]["audioClipCount"] == 1
            else:
                finish(page, "SAVED_TEXT_ONLY")
                assert page.evaluate("!!localStorage.getItem('doha.v01.album')")
            assert not errors, errors
            print("PASS", name, flush=True)
            page.close()

        page, errors = launch_page(browser)
        start(page)
        begin_capture(page)
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        page.wait_for_function("__DOHA.mic().tracks.every(track=>track==='ended')")
        finish(page)
        expect(page.locator("#originalAudio audio")).to_have_count(1)
        assert not errors, errors
        print("PASS page exit stops tracks and preserves final segment", flush=True)
        browser.close()


if __name__ == "__main__":
    verify()
