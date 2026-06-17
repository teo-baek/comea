---
slug: comment-reveal-delay
source: comment-reveal-delay-requirements.md
---

# 기술설계: 댓글 순차 등장 딜레이 연출 (랜덤)

> 입력 PRD: `comment-reveal-delay-requirements.md`. 다음 단계: `/write-plan`.

## 1. 아키텍처 개요

클라이언트(`ulssu/`) 전용 변경. 백엔드 무변경. `detail_screen`의 등장 루프(`_revealNewComments`)가 현재 고정 딜레이(생각 800ms + 작성 1500ms)를 쓰는데, 이를 **댓글마다 랜덤 long-tail gap** 으로 바꾼다. 단, **댓글 순서는 그대로(백엔드 순서)** — 랜덤은 gap에만. gap 분포 계산은 외부 의존 없는 **순수 함수 + 주입형 `Random`** 으로 분리해 단위 테스트와 위젯 테스트가 결정적이게 한다.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `ulssu/lib/util/reveal_delay.dart` | **생성** | `Duration randomRevealGap(Random rng)` — long-tail(중앙값 ~2초, 최대 30초) gap 생성. 순수 + 시드 주입. |
| `ulssu/lib/screens/detail_screen.dart` | **수정** | `_revealNewComments`를 고정 딜레이 → `randomRevealGap(_rng)` 순차 적용으로 교체(순서 유지). `Random` 주입(기본 `Random()`). 2단계 연출 제거 → gap 뒤 짧은 타이핑 플래시 후 등장. |
| `ulssu/test/util/reveal_delay_test.dart` | **생성** | gap 범위/분포(시드별) 단위 테스트. |
| `ulssu/test/screens/detail_reveal_test.dart` | **생성** | 시드 주입 시 댓글이 백엔드 순서대로·결정적으로 등장하는지 위젯 테스트. |

신규 의존성 없음 (`dart:math` Random).

## 3. 데이터 모델

변경 없음. 댓글 데이터는 기존 그대로(서버가 한 번에 반환). gap은 저장하지 않고 클라이언트가 등장 시점에 계산.

## 4. 외부 인터페이스 (API)

변경 없음. 기존 `reactToPost`/`getPosts` 응답 그대로 사용. (이번 피처는 순수 UI 연출.)

## 5. 핵심 결정 (대안 비교)

- **D1. 순서 유지 + gap만 랜덤** (대안: 댓글별 독립 딜레이로 등장 순서 섞기). 순서 유지 채택 — 대댓글/대화 흐름이 깨지면 안 됨(사용자 명시). 랜덤은 순차 gap에만.
- **D2. long-tail 분포 = 거듭제곱 스큐** `gap = pow(rng.nextDouble(), 3) * 30000ms`. (대안: 균일 분포 / 지수 분포). 거듭제곱(세제곱) 채택 — 구현 단순 + 시드 결정적 + "대부분 짧고 가끔 김"(중앙값 ≈ 0.5³×30 ≈ 3.75초, 다수 더 짧음, 최대 30초)을 한 줄로 충족. 지수분포는 상한 보장이 번거로움.
- **D3. `Random` 주입** (대안: 전역 Random 직접 사용). 주입 채택 — 위젯/단위 테스트에서 `Random(seed)` 주입으로 결정적 검증(AC-6).
- **D4. 2단계 연출 제거 → gap 뒤 짧은 타이핑 플래시** (대안: 인디케이터 완전 제거 / 기존 2단계 유지). gap 동안은 인디케이터 없이 대기하고, 등장 직전 ~300ms만 '작성 중' 플래시 후 댓글 추가. 긴 정적(최대 30초) 동안 '작성 중'을 띄우지 않아 어색함 방지(FR-5 단순화).

## 6. 예비 위험 (→ 구현계획서 §2로 매핑)

- **side-effect**: gap이 순차 누적이라 댓글 많은 글(예: 20개)은 전체 등장이 수십 초~분이 걸릴 수 있음. (완화: 분포 중앙값이 작아 대부분 빠르게 뜨고, 속도 비요구(NFR). 사용자가 화면을 떠나도 무방 — `mounted` 가드로 안전.)
- **race/lifecycle**: 등장 대기(`Future.delayed`) 중 화면 dispose 또는 반응으로 재진입 시 `setState` 예외/중복 루프. (완화: 기존 `if (!mounted) return` 가드 유지 + 반응 경로는 ④의 `_revealNewComments` 재호출 패턴 그대로 — 진행 중 루프와 충돌하지 않게 "아직 안 보인 것부터" 이어가는 기존 인덱스 로직 유지.)

## 7. 테스트 전략

- **순수 함수 단위테스트** (`test/util/reveal_delay_test.dart`): `randomRevealGap(Random(seed))` 가 [0,30000]ms 범위, 같은 시드 → 같은 값(결정적), 여러 시드 표본의 다수가 짧은 쪽(스큐 확인).
- **위젯테스트** (`test/screens/detail_reveal_test.dart`): `DetailScreen`에 `Random(고정seed)` 주입 + 댓글 3개 → `pump(Duration)` 으로 시간 진행 시 **백엔드 순서대로** 하나씩 등장(순서 보존, AC-3) + 모두 등장 완료 확인.
- **수동**: `flutter run` 으로 실제 불규칙 등장 체감 확인.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 11:10] [개발방향-수정]
- **id**: CH-20260617-002
- **이유**: 신규 기술설계 (댓글 랜덤 딜레이 연출) — requirements 승인 후 작성
- **무엇이**: comment-reveal-delay-tech-design.md 전체 (§1~7, 결정 D1~D4)
- **영향범위**: ulssu/ — reveal_delay.dart(신설), detail_screen(수정), test 2파일. 백엔드 무변경. verifying-spec 4축 green.
- **연관 항목**: CH-20260617-001
