---
slug: flutter-reaction-ui
source: flutter-reaction-ui-requirements.md
---

# 기술설계: Flutter 반응 버튼 UI

> 입력 PRD: `flutter-reaction-ui-requirements.md`. 다음 단계: `/write-plan`.

## 1. 아키텍처 개요

Flutter 앱(`comea/`)은 `StatefulWidget` + `setState` + `http` 패키지 구조다. 현재 HTTP 호출이 화면 위젯에 inline으로 박혀 있고 baseURL이 중복된다. 이번 피처는 **`lib/services/api.dart` 서비스 모듈을 신설**해 baseURL을 1곳으로 모으고 `getPosts/createPost/reactToPost`를 제공한다. `DetailScreen`은 반응 버튼을 갖고, 버튼 탭 시 `ApiService.reactToPost`를 호출해 갱신된 글을 받아 **새로 늘어난 댓글만** 기존 순차 등장 연출로 이어 붙인다. 테스트 가능성을 위해 `ApiService`는 `http.Client` 주입을 받고, `DetailScreen`은 `ApiService` 주입을 받는다(기본값은 실제 구현).

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea/lib/services/api.dart` | **생성** | `ApiService` — baseURL 상수 1곳 + `getPosts()` / `createPost(content)` / `reactToPost(postId, reaction)`. `http.Client` 주입 가능. |
| `comea/lib/screens/detail_screen.dart` | **수정** | `postId` 파라미터 추가, 좋아요/싫어요 버튼, 가변 댓글 리스트 + 델타 애니메이션, `_isReacting` 가드, FR-10 톤 카피 완화. `ApiService` 주입. |
| `comea/lib/screens/home_screen.dart` | **수정** | inline http → `ApiService` 사용(중복 baseURL 제거). `DetailScreen`에 `postId` 전달. 등록 직후 로컬 insert map에 `id` 포함. |
| `comea/test/services/api_test.dart` | **생성** | `reactToPost` 등 `MockClient` 단위 테스트. |
| `comea/test/screens/detail_reaction_test.dart` | **생성** | 버튼 탭 → 새 댓글 append / 연타 차단 위젯 테스트. |

신규 의존성 없음 (`http ^1.6.0`의 `package:http/testing.dart` MockClient + `flutter_test` 활용).

## 3. 데이터 모델

클라이언트 영속 저장 없음. 반응 응답(서버 PostModel 직렬화) 형태:

```
{ "id": int, "content": str, "score": int, "is_locked": bool,
  "comments": [ { "id": int, "post_id": int, "name": str, "comment": str }, ... ] }
```

⚠️ 응답에 **좋아요/싫어요 카운트 필드가 없다**(백엔드가 비노출) → FR-3은 서버에서 이미 보장. 클라이언트는 카운트를 받지도, 보여주지도 않는다.

## 4. 외부 인터페이스 (API)

- `ApiService.reactToPost(int postId, String reaction)` → `POST {baseURL}/posts/{postId}/reaction`, body `{"reaction": "like"|"dislike"}`. 성공 시 갱신된 글(댓글 포함) 반환. 404(없는 글)/400(잘못된 reaction)/네트워크 예외는 호출부로 전파 → 화면이 오류 안내.
- `ApiService.getPosts()` / `createPost(content)` — 기존 `home_screen` 동작을 동일 계약으로 이관(회귀 없도록).
- baseURL 상수 1곳(`ApiService` 내부, 기존 `http://172.28.0.1:8000/api`).

## 5. 핵심 결정 (대안 비교)

- **D1. API 서비스 모듈 신설** (대안: detail_screen inline 추가). 모듈 채택 — baseURL 3중복 제거 + `http.Client` 주입으로 테스트 가능. 비용: `home_screen` 2개 호출 이관(소폭 수정).
- **D2. 테스트 = 서비스 유닛(MockClient) + 가벼운 위젯** (대안: 수동 검증만). 자동 테스트 채택 — 회귀 방지. backend의 TDD 기조 유지.
- **D3. `is_locked`는 UI에서 미사용** (대안: 전달해 버튼 비활성/배지). 미사용 채택 — FR-8 "별표시 없이 버튼 유지"라 UI 분기 불필요(YAGNI). 잠긴 글도 반응 전송은 되며 새 댓글이 안 늘 뿐.
- **D4. 새 댓글 머지 = 길이 기반 델타** (대안: 댓글 id 집합 diff). 길이 기반 채택 — 서버가 append-only(기존 댓글 보존 + 뒤에 추가)라 "이전 개수 이후"만 애니메이트하면 충분. id diff는 과설계.
- **D5. 반응 중복 전송 방지 = `_isReacting` 플래그** — 처리 중 같은 동작 버튼 비활성 + 인디케이터, 응답 후 해제.

## 6. 예비 위험 (→ 구현계획서 §2로 매핑)

- **side-effect**: `reactToPost` 1회가 서버에서 동기 AI 생성을 유발 → 응답이 수초 걸릴 수 있음. (완화: `_isReacting`로 연타 차단 + 처리 중 인디케이터. 속도 비요구(NFR)라 지연 자체는 허용.)
- **breaking**: `home_screen`의 getPosts/createPost를 `ApiService`로 이관하며 기존 동작이 바뀔 위험(응답 파싱/에러 처리). (완화: 계약 동일 유지 + 기존 동작 수동 확인, 서비스 유닛테스트.)
- **race/lifecycle**: 화면 dispose 후 비동기 응답 도착 → `setState` 시 예외. (완화: 기존 코드처럼 `if (!mounted) return` 가드.)

## 7. 테스트 전략

- **ApiService 유닛테스트** (`test/services/api_test.dart`): `MockClient` 주입으로 `reactToPost` 200(갱신 글 반환), 400, 404, 네트워크 예외 경로를 결정적으로 검증. 실제 네트워크 없음.
- **위젯테스트** (`test/screens/detail_reaction_test.dart`): mock `ApiService` 주입한 `DetailScreen`에서 좋아요 탭 → 새 댓글이 리스트에 append 되는지, `_isReacting` 동안 연타가 차단되는지 확인. 카운트 미노출(개수 텍스트 부재)도 단언.
- **수동 검증**: `flutter run` + 로컬 백엔드로 실제 반응→댓글 증식 최종 확인.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 10:06] [개발방향-수정]
- **id**: CH-20260617-002
- **이유**: 신규 기술설계 (Flutter 반응 버튼 UI) — requirements 승인 후 작성
- **무엇이**: flutter-reaction-ui-tech-design.md 전체 (§1~7, 결정 D1~D5)
- **영향범위**: comea/ Flutter 코드 — api.dart(신설), detail_screen·home_screen(수정), test 2파일. verifying-spec 4축 green(누락/모순 0).
- **연관 항목**: CH-20260617-001
