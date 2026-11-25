# 테스트 실행 안내 (PROJECT DOHA v0.2 첫 실험 검토본)

모든 검증은 **로컬 headless Chromium + 가짜 마이크**로 실행합니다. 실제 아이 목소리·실제 마이크 없이도
녹음 시작/정지·저장·복원·실패 경로를 확인할 수 있습니다.

## 준비

```bash
python3 -m pip install playwright      # 이미 설치되어 있으면 생략
python3 -m playwright install chromium # 브라우저가 없을 때만
```

## 실행

```bash
cd project-doha

# 0) 빌드가 소스와 어긋나지 않았는지 (반드시 먼저)
python3 src/build.py
python3 src/check_build.py

# 1) PR #1 실패 경로 스위트
python3 tests/verify_safety.py

# 2) 우리 회귀 스위트
python3 src/verify_v012.py   # 저장 4단계·테이크·42초·내보내기·삭제·이관·v0.1.1 호환
python3 src/verify_v013.py   # 바로 듣기 · 음성 자막 변환(기본 OFF)
python3 src/verify_v011.py   # v0.1.1부터 이어진 P0 회귀
python3 src/verify_v014.py   # 톤 리뉴얼·영화 ▶·내보내기 누락

# 3) v0.2 첫 실험 — 가상 티키타카 대화(합성 음성·모의 자막)
python3 src/verify_v02_exp.py

# 4) v0.2-A — 한 번에 이어 녹음(세 마디 나누기·저장·새로고침 뒤 장면 2 재생) + resume 보완
python3 src/verify_v02a.py
```

## Chromium 경로 (환경별)

`tests/verify_safety.py`는 실행 파일을 다음 순서로 찾습니다.

1. 환경변수 `CHROMIUM` (또는 `DOHA_CHROMIUM`)
2. `/usr/bin/chromium`, `/usr/bin/chromium-browser`, `/usr/bin/google-chrome`
3. 위가 없으면 **Playwright가 관리하는 Chromium** (`executable_path`를 넘기지 않음)

`src/verify_v01x.py`는 Playwright 기본 Chromium을 씁니다. 라이브러리 경로가 따로 필요한 환경
(예: 이 저장소의 작업 컨테이너)에서는 아래처럼 실행합니다.

```bash
export LD_LIBRARY_PATH=/workspace/tmp/sysroot/usr/lib/x86_64-linux-gnu
export CHROMIUM=$HOME/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
python3 tests/verify_safety.py
python3 src/verify_v013.py
```

## 도우미 옵션

| 변수 | 뜻 |
|---|---|
| `DOHA_URL` | 서버를 띄우지 않고 주어진 주소(예: 라이브 URL)로 검사 |
| `DOHA_PORT` | 로컬 검사용 HTTP 포트 (기본 8792 / 8793) |
| `CHROMIUM` | 사용할 Chromium 실행 파일 경로 |

`src/verify_v01x.py`는 저장소 루트를 로컬 HTTP로 띄워 검사합니다(`file://`가 아닌 이유는
IndexedDB·다운로드 동작이 오리진에 묶여 있기 때문). `tests/verify_safety.py`는 서버 없이
`page.route()`로 `index.html`을 그대로 내려줍니다.

`src/verify_v02_exp.py`는 `http://127.0.0.1:8796/`에 검토본을, 같은 오리진의 `/legacy/`에
**v0.1.4 빌드**(`git show b11387d:index.html`)를 함께 띄워 교차 버전 호환을 검사합니다.
추출본은 `.legacy-v014/`에 생기며 git에 넣지 않습니다. 얕은 클론처럼 그 커밋이 없으면
이 묶음만 SKIP으로 표시되고 나머지는 그대로 실행됩니다.

## 지금 통과 기준 (2026-11-25, Chromium 159.0.8154.6)

| 스위트 | 항목 | 결과 |
|---|---|---|
| `tests/verify_safety.py` | 10 (실패 경로 7 + 종합 흐름 3) | ALL PASS |
| `src/verify_v012.py` | 65 | ALL PASS |
| `src/verify_v013.py` | 43 (v0.1.4 공개분부터 STT 세션은 '인식기가 시작되지 않음'을 검사) | ALL PASS |
| `src/verify_v014.py` | 114 (톤·대비·빈 무대·영화 ▶ · 내보내기 누락 개별/전체 · STT 비활성) | ALL PASS |
| `src/verify_v011.py` | 32 | ALL PASS |
| `src/verify_v02_exp.py` | 82 (순서·끊김 · 늦은/누락 자막 · 계속 말하기 · 그림체·분위기 · v0.1.4 호환 · 휴대폰) | ALL PASS |
| **합계** | **346** | **ALL PASS** |

`verify_v013.py`는 2026-11-25부터 음성 자막 인식이 비활성(`STT_ENABLED=false`)되었으므로,
가짜 음성인식을 주입해도 토글·`setStt(true)`·마이크 어느 경로로도 인식기 생성 0회임을 검사합니다.

각 스위트는 세션별 **런타임·콘솔 에러 0건**도 함께 확인합니다.
실제 iPhone/iPad Safari 검증은 별도이며, 이 컨테이너에서는 실행할 수 없습니다(미검증으로 표기).

## 테스트 픽스처 규칙

- 실제 아동의 이름·음성·전사·이미지를 넣지 않습니다. 문장은 `가상의 …`, `검증용 …`처럼 가상 문구를 씁니다.
- v0.2 실험(`verify_v02_exp.py`)의 음성은 브라우저가 만든 **합성 음성**(삐- 파형)이며, WAV 파일을 저장소에 두지 않습니다.
- 음성인식은 가짜 생성자(`window.SpeechRecognition`)를 주입해 성공/중간결과/오류/미지원을 흉내 냅니다
  (`src/verify_v013.py`의 `FAKE_SR`). 실제 브라우저 음성인식은 서버·권한이 필요해 자동화하지 않습니다.
