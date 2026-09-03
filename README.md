# BITBOX

**정류장에서 큰 글씨와 음성만으로 버스를 찾는 고령친화 안내 기기입니다.**

목적지를 말하면 실시간 도착 정보와 버스 경로를 화면과 음성으로 안내합니다.
타이핑도, 앱 설치도 필요하지 않습니다.

---

## 왜 만들었나

65세 이상이 인구의 **20.3%**입니다. 그런데 70대 이상의 디지털 조작 역량은
일반국민 대비 **29.4%**에 그칩니다. 접근 수준이 90.7%인 것과 대비됩니다.

기기가 없는 것이 문제가 아니라, **작은 글씨와 복잡한 절차를 다루기 어렵다**는 것이
문제입니다. 그래서 입력 단계와 정보 구조 자체를 단순하게 만들었습니다.

> 출처: 통계청 2025 고령자 통계 · NIA 2025 디지털정보격차 실태조사 84쪽 표 1
> (일반국민을 100으로 둔 상대 비율입니다. 100점 만점 점수가 아닙니다.)
> 근거 자료 전문은 [`docs/ELDERLY_DIFFERENTIATION_EVIDENCE.md`](docs/ELDERLY_DIFFERENTIATION_EVIDENCE.md)

## 무엇이 다른가

| | 내용 |
|---|---|
| **오안내 방지** | 비슷한 지명은 임의로 안내하지 않고 되묻습니다. 없는 노선 번호를 비슷한 번호로 바꾸지 않습니다. |
| **타기 편한 차 우선** | 저상버스·비만차·저혼잡 차량을 앞세웁니다. 가장 빨리 오는 차가 아니라 타기 쉬운 차를 먼저 보여 줍니다. |
| **읽고 듣는 두 경로** | 큰 글씨·고대비 전환과 음성 안내를 함께 제공합니다. 기기에 한국어 음성 엔진이 없으면 서버 합성으로 자동 대체합니다. |
| **이용자가 조절** | 글씨 크기와 안내 음량을 직접 바꿉니다. 무인정보단말기 접근성 기준을 따릅니다. |
| **공용 환경 배려** | 음성 처리 사전 동의, 최근 목적지 제한, 90초 무활동 초기화로 개인정보가 남지 않게 합니다. |

## 어떻게 동작하나

```
정류장 전광판   GET  /api/bus/default     공공데이터포털 실시간 도착정보
목적지 자동완성  GET  /api/places/suggest  Kakao Local
텍스트 길찾기   POST /api/route           Kakao 좌표 → ODsay 버스 경로
음성 길찾기     POST /api/upload          STT → 의도 분석 → 좌표 → 경로 → TTS
라즈베리파이    POST /api/process         원시 클라이언트용 (WAV 업로드)
```

`/api/route`와 `/api/upload`는 같은 응답 구조를 씁니다. 말로 찾든 눌러서 찾든
같은 결과 화면으로 이어집니다. 지도는 경로에 좌표가 있을 때만 불러옵니다.

**사용 API** — OpenAI(STT·의도 분석·TTS) · Kakao Local(좌표) · ODsay(버스 경로) ·
공공데이터포털(실시간 도착)

## 빠르게 실행하기

```bash
cp .env.example .env          # API 키를 채웁니다
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-backend.txt
cd frontend && npm install && cd ..
```

터미널 두 개에서 각각 실행합니다.

```bash
uvicorn app.main:app --reload          # http://127.0.0.1:8000
cd frontend && npm run dev             # http://127.0.0.1:5173
```

개발 서버가 `/api` 요청을 백엔드로 넘기므로 브라우저 코드에 토큰을 넣지 않습니다.
상태 확인은 `/health`, API 문서는 `/docs`입니다.

> **지도를 보려면** Kakao Developers → 내 애플리케이션 → 플랫폼 → Web의
> JavaScript SDK 도메인에 `http://127.0.0.1:5173`을 등록합니다. 스킴·호스트·포트를
> 그대로 대조하므로 `https://`로 등록하면 맞지 않습니다. 등록하지 않아도 앱은
> 동작하며, 지도 탭만 정류장 순서 목록으로 안전하게 대체됩니다.

## 검증

```bash
python -m pytest -q                    # 백엔드
cd frontend && npm run test            # 프론트 단위
cd frontend && npm run typecheck
cd frontend && npm run e2e             # 브라우저 (desktop + mobile)
```

CI가 매 푸시마다 위 전부와 `ruff`·`bandit`·`pip-audit`을 실행합니다.
배포 워크플로의 검증은 CI 검증의 상위 집합이며, 그 관계를
[`tests/test_workflow_definitions.py`](tests/test_workflow_definitions.py)가 고정합니다.

접근성은 주요 화면 여섯 곳에 axe-core 기반 WCAG 2.1 A/AA 자동 검사를 돌립니다
([`frontend/e2e/accessibility.spec.ts`](frontend/e2e/accessibility.spec.ts)).
스크린리더가 실제로 받는 aria 트리도 함께 확인합니다.

## 알아 둘 한계

정직하게 적습니다. 아래는 **아직 확인하지 않았거나, 원리상 완전하지 않은** 부분입니다.

- **실제 스크린리더 낭독은 확인하지 않았습니다.** 자동 검사는 기계가 판정할 수 있는
  규칙만 봅니다. NVDA·VoiceOver·TalkBack의 낭독 순서와 체감은 사람이 들어야 합니다.
- **고령 이용자 대상 실측이 없습니다.** "고령 이용자를 고려해 설계했다"까지가 사실이며,
  효과가 입증됐다고 말할 수 없습니다. 측정 절차는 [`docs/EVALUATION.md`](docs/EVALUATION.md)에
  준비돼 있습니다.
- **지도 선은 예상 경로입니다.** ODsay 정류장 순서와 구간 좌표를 이은 것이라 도로
  중심선과 완전히 같지 않습니다.
- **도착 알림은 15초 주기 갱신**이며 GPS 연속 추적이 아닙니다.
- **저상·여유 우선은 현재 정류장의 도착 차량에만** 적용되며 목적지 경로를 다시
  계산하지 않습니다.
- **지역명과 실제 역명이 다른 곳**(예: 상암 → 디지털미디어시티역)은 이름 기반
  검색으로 잡지 못합니다.

## 더 읽을 것

| 문서 | 내용 |
|---|---|
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | 배포 전제조건, 상태 점검, 장애 대응, 롤백, 서버 중지·재기동 |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | 실증 평가 절차와 발표에서 쓸 수 있는 표현·쓸 수 없는 표현 |
| [`docs/ELDERLY_DIFFERENTIATION_EVIDENCE.md`](docs/ELDERLY_DIFFERENTIATION_EVIDENCE.md) | 고령층 차별성 근거와 출처 |
| [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) | 디렉터리 구조와 엔드포인트 |

## 라이선스

이 저장소의 코드와 문서는 BITBOX 팀이 저작권을 보유하며 무단 복제·배포·수정을
허용하지 않습니다. 전문은 [`LICENSE`](LICENSE)를 참고하십시오. 한이음 산출물
권리 귀속은 해당 사업 규정을 따르며, 규정이 이 고지에 우선합니다.

`frontend/src/assets/fonts/`의 Noto Sans KR은 위 고지가 적용되지 않는 제3자
저작물로, SIL Open Font License 1.1로 배포됩니다. 전문은 같은 디렉터리의
[`OFL.txt`](frontend/src/assets/fonts/OFL.txt)에 있습니다.
Copyright © The Noto Project Authors.
