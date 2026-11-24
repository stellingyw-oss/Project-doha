# 테스트 실행 안내 (PROJECT DOHA v0.1.3)

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

## 지금 통과 기준 (2026-11-25, Chromium 159.0.8154.6)

| 스위트 | 항목 | 결과 |
|---|---|---|
| `tests/verify_safety.py` | 10 (실패 경로 7 + 종합 흐름 3) | ALL PASS |
| `src/verify_v012.py` | 65 | ALL PASS |
| `src/verify_v013.py` | 51 | ALL PASS |
| `src/verify_v011.py` | 32 | ALL PASS |

각 스위트는 세션별 **런타임·콘솔 에러 0건**도 함께 확인합니다.
실제 iPhone/iPad Safari 검증은 별도이며, 이 컨테이너에서는 실행할 수 없습니다(미검증으로 표기).

## 테스트 픽스처 규칙

- 실제 아동의 이름·음성·전사·이미지를 넣지 않습니다. 문장은 `가상의 …`, `검증용 …`처럼 가상 문구를 씁니다.
- 음성인식은 가짜 생성자(`window.SpeechRecognition`)를 주입해 성공/중간결과/오류/미지원을 흉내 냅니다
  (`src/verify_v013.py`의 `FAKE_SR`). 실제 브라우저 음성인식은 서버·권한이 필요해 자동화하지 않습니다.
