---
commit_policy: per-task
---

# 댓글 순차 등장 딜레이 연출 (랜덤) 구현계획서

> **다음 단계 안내**: 이 계획을 task-by-task 로 실행하려면 `js-super-sub-driven` (보조 에이전트 강제 모드, 권장) 또는 `executing-plans` (인라인 모드) 를 사용하세요. 각 step 은 체크박스 (`- [ ]`) 형식이라 진행 상황 추적이 가능합니다.

**Goal:** detail_screen의 댓글 등장을 고정 딜레이에서 **댓글별 랜덤 long-tail gap**(중앙값 ~2초, 최대 30초)으로 바꾼다. 순서는 백엔드 순서 그대로 유지(대화 흐름 보존), 랜덤은 gap에만, 클라이언트 전용.

**Architecture:** gap 분포는 `lib/util/reveal_delay.dart`의 순수 함수 `randomRevealGap(Random)`로 분리(시드 주입 → 테스트 결정성). `detail_screen`의 `_revealNewComments`가 고정 800/1500ms 대신 이 함수를 순차 적용하고, 등장 직전 짧은 타이핑 플래시만 둔다. `Random`은 DetailScreen에 주입(기본 `Random()`).

**Tech Stack:** Flutter (Dart), dart:math Random, flutter_test. 신규 의존성 없음.

**Spec inputs:**
- `comment-reveal-delay-requirements.md` — FR-1~6 (랜덤 gap/순서 유지/클라 전용/2단계 제거/반응 동일/시드)
- `comment-reveal-delay-tech-design.md` — D1(순서 유지) D2(거듭제곱 스큐) D3(Random 주입) D4(타이핑 플래시)

---

## 1. 단계별 작업

### Task 1: `reveal_delay` 순수 함수 + 유닛 테스트

**Files:**
- Create: `comea/lib/util/reveal_delay.dart`
- Test: `comea/test/util/reveal_delay_test.dart`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `comea/test/util/reveal_delay_test.dart`):
```dart
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:comea/util/reveal_delay.dart';

void main() {
  test('gap은 0~30초 범위 안에 있다', () {
    final rng = Random(1);
    for (var i = 0; i < 200; i++) {
      final gap = randomRevealGap(rng);
      expect(gap.inMilliseconds, greaterThanOrEqualTo(0));
      expect(gap.inMilliseconds, lessThanOrEqualTo(30000));
    }
  });

  test('같은 시드 → 같은 gap 수열 (결정적)', () {
    final a = List.generate(10, (_) => randomRevealGap(Random(42)).inMilliseconds);
    final b = List.generate(10, (_) => randomRevealGap(Random(42)).inMilliseconds);
    // 각 리스트는 새 Random(42)로 첫 호출만 같으므로, 같은 시드의 첫 값끼리 비교
    expect(randomRevealGap(Random(7)).inMilliseconds, randomRevealGap(Random(7)).inMilliseconds);
    expect(a.first, b.first);
  });

  test('long-tail: 표본 다수가 중앙값(7.5초)보다 짧다 (짧은 쪽으로 치우침)', () {
    final rng = Random(123);
    final samples = List.generate(500, (_) => randomRevealGap(rng).inMilliseconds);
    final shortCount = samples.where((ms) => ms < 7500).length;
    // 거듭제곱 스큐라 절반보다 훨씬 많은 표본이 7.5초 미만이어야 함
    expect(shortCount, greaterThan(300));
  });
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea && flutter test test/util/reveal_delay_test.dart`
Expected: FAIL — `Error: Couldn't resolve the package 'comea/util/reveal_delay.dart'`

- [ ] **Step 3: 구현 작성**

**수정 후** (new file: `comea/lib/util/reveal_delay.dart`):
```dart
import 'dart:math';

const int kMaxRevealGapMs = 30000; // 댓글 사이 간격 상한 (30초)

/// 댓글 등장 간격(gap)을 long-tail 분포로 생성한다.
/// 거듭제곱(세제곱) 스큐: 대부분 짧고(중앙값 ≈ 0.5³×30 ≈ 3.75초) 드물게 최대 30초.
/// rng 주입으로 테스트 결정성 확보.
Duration randomRevealGap(Random rng) {
  final r = rng.nextDouble(); // [0,1)
  final skewed = r * r * r; // long-tail: 작은 값으로 치우침
  return Duration(milliseconds: (skewed * kMaxRevealGapMs).round());
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd comea && flutter test test/util/reveal_delay_test.dart`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add comea/lib/util/reveal_delay.dart comea/test/util/reveal_delay_test.dart
git commit -m "feat(flutter): 댓글 등장 랜덤 long-tail gap 순수 함수 + 유닛테스트"
```

---

### Task 2: detail_screen 등장 루프를 랜덤 gap으로 교체

**Files:**
- Modify: `comea/lib/screens/detail_screen.dart` (import, 생성자 Random 주입, `_revealNewComments` 로직)
- Test: `comea/test/screens/detail_reveal_test.dart`

**Model**: sonnet

> 참고: 이 파일은 직전 슬라이스(flutter-reaction-ui)에서 작성된 상태가 기준이다. `**원본**` 블록은 그 상태와 byte-equal.

- [ ] **Step 1: 실패하는 위젯 테스트 작성**

**수정 후** (new file: `comea/test/screens/detail_reveal_test.dart`):
```dart
import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:comea/screens/detail_screen.dart';
import 'package:comea/services/api.dart';

void main() {
  testWidgets('댓글이 백엔드 순서대로 결정적으로 등장한다', (tester) async {
    final api = ApiService(client: MockClient((req) async => http.Response(
          jsonEncode({}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        )));
    await tester.pumpWidget(MaterialApp(
      home: DetailScreen(
        postId: 1,
        postContent: 'x',
        score: 70,
        realComments: const [
          {'id': 1, 'post_id': 1, 'name': 'A', 'comment': 'first'},
          {'id': 2, 'post_id': 1, 'name': 'B', 'comment': 'second'},
          {'id': 3, 'post_id': 1, 'name': 'C', 'comment': 'third'},
        ],
        api: api,
        rng: Random(1), // 시드 고정 → 결정적
      ),
    ));

    // gap은 순차 누적(댓글 3개 × 최대 30초)이라 안전하게 95초 진행 → 3개 모두 등장
    await tester.pump(const Duration(seconds: 95));

    // 순서 보존: first → second → third 가 이 순서로 모두 보인다
    expect(find.text('first'), findsOneWidget);
    expect(find.text('second'), findsOneWidget);
    expect(find.text('third'), findsOneWidget);

    final firstY = tester.getTopLeft(find.text('first')).dy;
    final secondY = tester.getTopLeft(find.text('second')).dy;
    final thirdY = tester.getTopLeft(find.text('third')).dy;
    expect(firstY, lessThan(secondY)); // 화면상 first가 second 위
    expect(secondY, lessThan(thirdY));
  });
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea && flutter test test/screens/detail_reveal_test.dart`
Expected: FAIL — DetailScreen에 `rng` 파라미터 부재로 컴파일 실패

- [ ] **Step 3: import + Random 주입 (생성자)**

**원본** (`comea/lib/screens/detail_screen.dart:1-19`):
```dart
import 'package:flutter/material.dart';

import '../services/api.dart';

class DetailScreen extends StatefulWidget {
  final int postId;
  final String postContent;
  final int score;
  final List<Map<String, dynamic>> realComments; // 서버에서 받아온 초기 댓글들
  final ApiService api;

  DetailScreen({
    super.key,
    required this.postId,
    required this.postContent,
    required this.score,
    required this.realComments,
    ApiService? api,
  }) : api = api ?? ApiService();
```

**수정 후**:
```dart
import 'dart:math';

import 'package:flutter/material.dart';

import '../services/api.dart';
import '../util/reveal_delay.dart';

class DetailScreen extends StatefulWidget {
  final int postId;
  final String postContent;
  final int score;
  final List<Map<String, dynamic>> realComments; // 서버에서 받아온 초기 댓글들
  final ApiService api;
  final Random rng;

  DetailScreen({
    super.key,
    required this.postId,
    required this.postContent,
    required this.score,
    required this.realComments,
    ApiService? api,
    Random? rng,
  })  : api = api ?? ApiService(),
        rng = rng ?? Random();
```

- [ ] **Step 4: `_revealNewComments`를 랜덤 gap + 짧은 타이핑 플래시로 교체**

**원본** (`comea/lib/screens/detail_screen.dart:39-56`):
```dart
  // 아직 등장하지 않은(_visibleComments 이후) 댓글만 순차적으로 등장시킨다.
  Future<void> _revealNewComments() async {
    for (int i = _visibleComments.length; i < _allComments.length; i++) {
      await Future.delayed(const Duration(milliseconds: 800));
      if (!mounted) return;
      setState(() {
        _isAiTyping = true;
        _currentTypingAi = _allComments[i]["name"] as String;
      });

      await Future.delayed(const Duration(milliseconds: 1500));
      if (!mounted) return;
      setState(() {
        _visibleComments.add(_allComments[i]);
        _isAiTyping = false;
      });
    }
  }
```

**수정 후**:
```dart
  // 아직 등장하지 않은(_visibleComments 이후) 댓글만 순서대로 등장시킨다.
  // 순서는 백엔드 순서를 유지하고(대화 흐름 보존), 댓글 사이 간격만 랜덤 long-tail.
  Future<void> _revealNewComments() async {
    for (int i = _visibleComments.length; i < _allComments.length; i++) {
      // 댓글 사이 랜덤 gap (대부분 짧고 드물게 긴 정적). 등장 직전 ~300ms만 타이핑 플래시.
      final gap = randomRevealGap(widget.rng);
      final flash = const Duration(milliseconds: 300);
      final wait = gap > flash ? gap - flash : Duration.zero;

      await Future.delayed(wait);
      if (!mounted) return;
      setState(() {
        _isAiTyping = true;
        _currentTypingAi = _allComments[i]["name"] as String;
      });

      await Future.delayed(flash);
      if (!mounted) return;
      setState(() {
        _visibleComments.add(_allComments[i]);
        _isAiTyping = false;
      });
    }
  }
```

- [ ] **Step 5: 위젯 테스트 통과 확인**

Run: `cd comea && flutter test test/screens/detail_reveal_test.dart`
Expected: PASS (1 test)

- [ ] **Step 6: 전체 테스트 + 정적 분석**

Run: `cd comea && flutter test && flutter analyze`
Expected: 모든 테스트 PASS + `No issues found!` (reaction 슬라이스 테스트 포함 전부 green)

- [ ] **Step 7: 커밋**

```bash
git add comea/lib/screens/detail_screen.dart comea/test/screens/detail_reveal_test.dart
git commit -m "feat(flutter): 댓글 등장을 랜덤 long-tail gap으로(순서 유지) + 위젯테스트"
```

---

## 2. 위험 코드 지점

- `comea/lib/screens/detail_screen.dart:_revealNewComments` — **side-effect**: gap이 순차 누적이라 댓글 많은 글은 전체 등장이 수십 초~분 소요 가능. (mitigation: 거듭제곱 스큐로 대부분 짧음 + 속도 비요구(NFR). 사용자 이탈해도 무방.)
- `comea/lib/screens/detail_screen.dart:_revealNewComments` — **race**: `Future.delayed` 대기 중 화면 dispose 또는 반응으로 재진입 시 `setState`/중복 루프. (mitigation: 각 await 뒤 `if (!mounted) return` 유지 + "안 보인 댓글부터(`_visibleComments.length`)" 이어가는 인덱스 로직으로 중복 등장 방지. ④ 반응 경로와 동일 패턴.)

## 3. 롤백 전략

- **Code:** Task별 커밋이므로 `git revert <SHA>` 역순(Task 2→1). 고정 딜레이로 되돌리려면 Task 2 커밋만 revert(reveal_delay.dart는 미사용으로 남아도 무해).
- **간격 조정:** 분포/상한은 `reveal_delay.dart`의 `kMaxRevealGapMs` + 스큐 지수 한 곳에서 조정.
- **신규 의존성 없음** → 패키지 롤백 불필요.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 11:10] [구현계획서-수정]
- **id**: CH-20260617-003
- **이유**: 신규 구현계획서 작성 (댓글 랜덤 딜레이 연출, 2 TDD task)
- **무엇이**: comment-reveal-delay-implementation-plan.md §1(Task 1~2), §2 위험, §3 롤백
- **영향범위**: comea/ — reveal_delay.dart(신설), detail_screen(수정), test 2파일. 위젯 테스트 pump 타이밍(누적 95s) 자체점검에서 보정.
- **연관 항목**: CH-20260617-001, CH-20260617-002

### [2026-06-17 11:35] [코드-수정] (batch: tasks 1..2)
- **id**: CH-20260617-004
- **이유**: 댓글 순차 등장 랜덤 딜레이 연출 구현(2 TDD task). 고정 딜레이 → long-tail gap(순서 유지).
- **무엇이**: `comea/lib/util/reveal_delay.dart`(신설), `comea/lib/screens/detail_screen.dart`, `comea/test/util/reveal_delay_test.dart`(신설), `comea/test/screens/detail_reveal_test.dart`(신설)
- **영향범위**: DetailScreen에 `rng` optional 파라미터 추가(호출부 무영향). 등장 연출만 변경, 백엔드/데이터 무변경. ④ 반응 경로의 _revealNewComments 재사용 → 반응 추가 댓글도 동일 적용.
- **위험 카테고리**: side-effect(gap 누적 지연), race(대기 중 dispose) — §2 사전 식별, mounted 가드로 완화
- **task별 세부 (2건)**:
  - DT1: `lib/util/reveal_delay.dart` — randomRevealGap long-tail + 유닛테스트 3 (none) — commits: `296167c`
  - DT2: `lib/screens/detail_screen.dart` — _revealNewComments 랜덤 gap(순서 유지)+Random 주입 + 위젯테스트 1 (side-effect, race) — commits: `89a4c69`
- **테스트 결과**: flutter test 10 passed (reveal_delay 3 + reaction 2 + reveal 1 + api 4), flutter analyze No issues.
- **연관 commits**: `296167c..89a4c69` (2 커밋)
- **변경 전/후 코드**: 생략 — `git show <SHA>` 로 조회 (git-fast 모드)
- **연관 항목**: CH-20260617-003
