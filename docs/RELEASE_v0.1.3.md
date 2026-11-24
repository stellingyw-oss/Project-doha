# RELEASE v0.1.3 — PR #1 통합 + 바로 듣기 + 임시 음성 자막 변환

2026-11-25 · **main 배포 완료** (`4c7b612`) · PR #1 종료 · 라이브 검증 통과

## 1. 한 줄 요약

같은 v0.1.2 기반에서 갈라진 두 작업(저장·녹음 안전 스프린트 = PR #1 / 우리 체험 개선 = v0.1.2+v0.1.3 계획)을
**`src/index.src.html` 하나로 통합**하고, 캔버스 **바로 듣기**와 **임시 음성 자막 변환(기본 OFF)** 을 얹은 뒤
**로컬 빌드 + 158개 자동 검증 ALL PASS**까지 확인했습니다. 푸시·배포는 하지 않았습니다.

## 2. 통합 방식 (재현 가능한 절차)

1. `git fetch origin pull/1/head:pr-1` 로 PR을 로컬에 받아 둔 상태에서 시작(`pr-1` = `7df488c`).
2. PR의 빌드 산출물 `index.html`에서 **base64 data URI 12개를 `{{IMG_*}}`/`{{T_*}}` 자리표시자로 되돌려**
   빌드 소스 형태로 재구성.
3. 재구성한 소스로 다시 빌드한 결과가 **PR 산출물과 바이트 단위로 일치**(699,381 bytes)함을 확인 → 이식 누락 0.
4. 그 소스를 `src/index.src.html`의 새 기준으로 삼고(우리 v0.1.2 변경은 PR base에 이미 포함: `overflow:clip`, 42초 무절단, 삭제 id 방지),
   v0.1.3 기능을 그 위에 추가.
5. `.gitignore`에서 `src/` 제외 해제 → 소스·빌드·검증 스크립트를 저장소가 관리. `assets/*.png`(원본 수 MB)만 계속 제외.
6. `src/check_build.py` 추가 — 소스와 커밋된 `index.html`이 어긋나면 즉시 실패(같은 사고 재발 방지).

## 3. v0.1.3에서 추가한 코드

### 3-1. 캔버스 바로 듣기

- 캔버스 `#stage` 안 `#listenBtn`(왼쪽 아래). 현재 장면(`state.active`)의 **마지막 테이크**를 재생.
- 테이크가 없으면 `hidden`. 녹음이 붙는 즉시 표시(`attachTake` → `syncListenBtn`), 장면 이동 시 갱신(`showFrame`).
- 정지 조건: 다시 누르기 / 재생 종료 / 마이크 재시작 / 캔버스 이탈(`go()`) / 새 이야기 시작 / 다른 장면 이동.
- 영화 화면 `#originalAudio` 와 **상호 배타**(서로 `pauseOriginalAudio()`/`stopListen()`).
- 버튼이 보이면 자막을 54px 위로 올려 겹치지 않게 함(`.stage.has-listen .cap`).
- 자동화 훅: `__DOHA.listen()`, `__DOHA.toggleListen()`, `__DOHA.stopListen()`.

### 3-2. 임시 음성 자막 변환 (기본 OFF)

- UI: 캔버스 안내줄 `#sttBtn`(`role="switch"`, `aria-checked`) — 라벨 `음성 자막 변환 (임시 · 브라우저 서버 전송 가능)`, 옆에 상태 문구 `#sttNote`, 중간 인식 미리보기 `#sttHear`.
- **기본 OFF**: 초기 HTML이 `aria-checked="false"`, 세션 간 저장하지 않음(새로고침하면 다시 OFF). OFF 상태에서는 `SpeechRecognition` **생성조차 하지 않음**.
- ON: `SpeechRecognition || webkitSpeechRecognition`, `ko-KR` · `interimResults` · `continuous`. 중간 결과는 `#sttHear`에만 표시.
- 확정 결과 → `suggestScene(text)` → `runAct()` → `source:"sample"` 장면 + `예시 그림 ·` 라벨. 아이가 말한 문장은 **자막 그대로**.
- 마이크 수명주기와 결합: `startMic()` 성공 시 시작, `stopMic()`에서 종료. 브라우저가 스스로 끊으면 1회 재연결.
- **완전 격리**: `sttFail()`은 `stt` 상태와 토글·문구만 되돌리고 `MediaRecorder`·IndexedDB·장면·저장에는 손대지 않음. 오류·미지원이어도 원본 녹음은 계속.
- 자동화 훅: `__DOHA.stt()`(on/supported/starts/errors/finals/lastText), `__DOHA.setStt()`, `__DOHA.suggestScene()`.

### 3-3. 버전 표기

meta `0.1.3` · 홈 `PROJECT DOHA · v0.1.3` · 내보내기 `formatVersion:"0.1.3"`(개별·전체).
PR 로드맵의 `P1 / v0.2`(정식 음성 인식)와 구분되도록, 이번 STT는 문서·화면 모두 "임시 · 기본 OFF · 예시 그림"으로만 적습니다.

### 3-4. 함께 정리한 UI

- 영화 화면 원본 목소리 카드: 재생기와 `원본 N 다운로드` 버튼이 찌그러지지 않게(`#originalAudio` 전용 규칙).
- 앨범 카드 버튼 3종이 단어 중간에서 끊기지 않게(`white-space:nowrap`).
- 캔버스 안내문(`.cv-deck .hint`)에 작은 글씨 스타일 지정(PR에는 스타일이 없었음).
- 홈 상단 배지 `광고 없음 · 가족만` → **`광고 없음 · 이 브라우저에만`**(캔버스 배지와 같은 정직성 기준. "가족만"은 실제 접근 제어가 없어 오해를 살 수 있음).

## 4. 검증 결과 (전부 로컬)

| 스위트 | 항목 | 결과 |
|---|---|---|
| `tests/verify_safety.py` | 10 (실패 경로 7 + 종합 흐름 3) | **ALL PASS** |
| `src/verify_v012.py` | 65 | **ALL PASS** |
| `src/verify_v013.py` | 51 | **ALL PASS** |
| `src/verify_v011.py` | 32 | **ALL PASS** |
| `src/check_build.py` | 1 | OK (713,117 bytes 일치) |

- Chromium 159.0.8154.6 · 가짜 마이크 · 세션별 런타임/콘솔 에러 **0건**.
- 레이아웃: 1180×820 / 820×1180 / 390×844 모두 `#app.scrollLeft==0`, 문서 폭 = 창 폭.
- 스크린샷: `downloads/doha-v0.1.3-shots/` (홈·캔버스·재생·영화·앨범 × 3해상도).

### v0.1.3에서 새로 넣은 검증(51항목 중 핵심)

- 바로 듣기: 녹음 전 숨김 → 녹음 뒤 표시 → 재생(라벨 `⏸ 멈추기`) → 정지 → 재생 종료 시 라벨 복귀
- 마이크 재시작·캔버스 이탈 시 자동 정지, 테이크 없는 장면에서 숨김, 다시 돌아오면 표시
- STT 기본 OFF: 토글 false, 인식기 생성 0회, 마이크를 켜도 시작 안 함
- STT ON: 확정 문장이 `source=sample`·`space` 장면으로, 자막 접두 `예시 그림 ·`, 원본 녹음은 `SAVED_COMPLETE`
- STT 오류(`network`): 토글 자동 OFF·안내 문구·재연결 안 함, 녹음은 계속 → 중립 장면 테이크 1 → `SAVED_COMPLETE`
- 미지원 브라우저: 켜지지 않고 안내, 원본 녹음·저장 정상
- 새 세션(새로고침) 뒤 다시 기본 OFF

## 5. 기존 스위트를 통합 UX에 맞춰 고친 곳

| 스위트 | 고친 이유 |
|---|---|
| `verify_v012.py` | 대화상자 정책 분리(동의 확인은 수락, 삭제·새 이야기 확인은 테스트가 제어), 중립 시작(첫 테이크는 자막 없는 중립 장면), 내보내기 카드 버튼 3종(`.al-card-actions`가 영화 화면 원본 카드와 겹쳐 범위 축소), `formatVersion 0.1.3`, 자막이 있는 기록을 만들기 위해 직접 입력 한 줄 추가 |
| `verify_v011.py` | 칩이 `예시 장면 둘러보기` 안으로 접혀 있어 펼친 뒤 클릭, 예시 장면만으로는 저장하지 않는 규칙에 맞춰 직접 입력 추가, 음성 전용 중립 장면(빈 자막)을 자막 비교에서 제외 |
| `verify_safety.py` | `CHROMIUM` 하드코딩(`/usr/bin/chromium`) → 환경변수 → 시스템 경로 → Playwright 번들 순으로 유연화(검사 내용은 그대로) |

## 6. 남은 위험 · 미검증

1. **실제 iPhone/iPad Safari 미검증** — 이 컨테이너에서는 불가. 특히 ①`webkitSpeechRecognition` 지원·서버 전송 여부 ②`<audio>` 연속 재생(바로 듣기) ③IndexedDB 용량·저장 실패 동작은 실기기 확인이 필요합니다.
2. **음성인식 품질** — 임시 기능입니다. Chrome 계열은 오디오를 Google 서버로 보내며, 오프라인·권한·정책에 따라 바로 실패할 수 있습니다(그때는 토글이 스스로 꺼지고 원본 녹음은 유지).
3. **STT와 MediaRecorder 동시 사용** — 같은 마이크를 두 소비자가 쓰는 구조입니다. 실기기에서 발열·중복 점유 이슈가 있는지 확인 필요(테스트는 가짜 인식기라 이 부분을 재현하지 않음).
4. **PR #1 처리 결과** — v0.1.3 통합 커밋으로 main에 반영되어 PR #1(`develop/v0.1.2-safety` → `main`)은 2026-11-25에 종료했습니다. PR이 올린 문서·안전성·정직성 개선은 전부 이 커밋에 포함되어 있습니다.
5. **문서 정합성** — `docs/FIRST_SPRINT.md`는 v0.1.2 스프린트 문서로 남겨 두었고, v0.1.3 범위는 이 문서와 README가 설명합니다.

## 7. 배포 기록 (실행 완료)

```bash
python3 src/check_build.py                      # OK 713,117 bytes
git commit -m "feat(v0.1.3): PR #1 통합 + 캔버스 바로 듣기 + 임시 음성 자막 변환(기본 OFF)"   # 4c7b612
git checkout main && git merge --ff-only merge/pr1-v013 && git push origin main
gh pr close 1 --repo stellingyw-oss/Project-doha --comment "v0.1.3 통합 커밋으로 main에 반영되어 닫습니다. …"
```

- GitHub Pages: `main` / 루트, 커밋 `4c7b612` 빌드 `built` → `https://stellingyw-oss.github.io/Project-doha/`
- 라이브 확인: HTTP 200, 서빙 파일이 로컬 `index.html`과 sha256 동일, 화면 표기 `PROJECT DOHA · v0.1.3`,
  `#listenBtn`("▶ 방금 녹음 듣기")은 녹음 전 숨김, `#sttBtn`은 `aria-checked="false"`(기본 OFF, 인식기 생성 0회),
  홈 → 캔버스 → 문장 입력 → 영화 → 저장 → 앨범 흐름에서 uncaught error·unhandledrejection 0건.
  유일한 실패 요청은 HTML이 선언하지 않은 기본 `/favicon.ico`(404)입니다.
