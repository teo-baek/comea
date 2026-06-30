---
commit_policy: per-task
---

# Flutter 반응 버튼 UI 구현계획서

> **다음 단계 안내**: 이 계획을 task-by-task 로 실행하려면 `js-super-sub-driven` (보조 에이전트 강제 모드, 권장) 또는 `executing-plans` (인라인 모드) 를 사용하세요. 각 step 은 체크박스 (`- [ ]`) 형식이라 진행 상황 추적이 가능합니다.

**Goal:** comea 글 상세 화면에 좋아요/싫어요 버튼을 붙여 reaction API를 호출하고, 새로 늘어난 AI 댓글만 기존 순차 등장 연출로 이어 붙인다. 수치는 비노출, 잠긴 글도 버튼 유지, 게시판 톤.

**Architecture:** `lib/services/api.dart`(ApiService — baseURL 1곳 + getPosts/createPost/reactToPost, `http.Client` 주입)를 신설해 HTTP를 모은다. `DetailScreen`은 `postId`와 `ApiService`를 주입받아 반응 버튼을 갖고, 응답의 댓글로 가변 리스트를 갱신해 길이 델타만 애니메이션한다. `home_screen`은 ApiService로 이관하고 postId를 넘긴다.

**Tech Stack:** Flutter (Dart), http ^1.6.0 (+ package:http/testing MockClient), flutter_test. 신규 의존성 없음.

**Spec inputs:**
- `flutter-reaction-ui-requirements.md` — FR-1~10 (버튼/호출/수치비노출/여러번/델타머지/상태변화/중복방지/잠김유지/실패안내/톤)
- `flutter-reaction-ui-tech-design.md` — D1(api 모듈) D2(테스트) D3(is_locked 미사용) D4(길이 델타) D5(_isReacting)

---

## 1. 단계별 작업

### Task 1: ApiService 모듈 + 유닛 테스트

**Files:**
- Create: `comea/lib/services/api.dart`
- Test: `comea/test/services/api_test.dart`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `comea/test/services/api_test.dart`):
```dart
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:comea/services/api.dart';

http.Response _json(Object body, int status) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

void main() {
  test('reactToPost: 성공 시 갱신된 글(댓글 포함)을 반환', () async {
    final mock = MockClient((req) async {
      expect(req.method, 'POST');
      expect(req.url.path, '/api/posts/7/reaction');
      expect(jsonDecode(req.body)['reaction'], 'like');
      return _json({
        'id': 7,
        'content': 'x',
        'score': 70,
        'is_locked': false,
        'comments': [
          {'id': 1, 'post_id': 7, 'name': 'AI', 'comment': 'hi'},
        ],
      }, 200);
    });
    final api = ApiService(client: mock);

    final post = await api.reactToPost(7, 'like');

    expect(post['id'], 7);
    expect(post['comments'], hasLength(1));
  });

  test('reactToPost: 비200 응답이면 예외', () async {
    final mock = MockClient((req) async => _json({}, 404));
    final api = ApiService(client: mock);

    expect(() => api.reactToPost(99, 'like'), throwsException);
  });

  test('getPosts: 200 리스트 파싱', () async {
    final mock = MockClient((req) async => _json([
          {'id': 1, 'content': 'a', 'score': 40, 'is_locked': false, 'comments': []},
        ], 200));
    final api = ApiService(client: mock);

    final posts = await api.getPosts();

    expect(posts, hasLength(1));
    expect(posts.first['id'], 1);
  });

  test('createPost: 200 글 객체 파싱', () async {
    final mock = MockClient((req) async {
      expect(req.url.path, '/api/posts');
      expect(jsonDecode(req.body)['content'], '고민');
      return _json({
        'id': 5,
        'content': '고민',
        'score': 95,
        'is_locked': false,
        'comments': [],
      }, 200);
    });
    final api = ApiService(client: mock);

    final post = await api.createPost('고민');

    expect(post['id'], 5);
    expect(post['score'], 95);
  });
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea && flutter test test/services/api_test.dart`
Expected: FAIL — `Error: Couldn't resolve the package 'comea/services/api.dart'` (모듈 미존재, 컴파일 실패)

- [ ] **Step 3: ApiService 구현**

**수정 후** (new file: `comea/lib/services/api.dart`):
```dart
import 'dart:convert';

import 'package:http/http.dart' as http;

/// comea 백엔드 HTTP 호출을 한곳에 모은 서비스.
/// baseUrl 단일화 + http.Client 주입(테스트 시 MockClient 사용).
class ApiService {
  static const String baseUrl = 'http://172.28.0.1:8000/api';

  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Future<List<Map<String, dynamic>>> getPosts() async {
    final resp = await _client.get(Uri.parse('$baseUrl/posts'));
    if (resp.statusCode != 200) {
      throw Exception('글 목록을 불러오지 못했습니다 (${resp.statusCode})');
    }
    final List<dynamic> data = jsonDecode(utf8.decode(resp.bodyBytes));
    return List<Map<String, dynamic>>.from(data);
  }

  Future<Map<String, dynamic>> createPost(String content) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/posts'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'content': content}),
    );
    if (resp.statusCode != 200) {
      throw Exception('글 등록에 실패했습니다 (${resp.statusCode})');
    }
    return Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)));
  }

  Future<Map<String, dynamic>> reactToPost(int postId, String reaction) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/posts/$postId/reaction'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'reaction': reaction}),
    );
    if (resp.statusCode != 200) {
      throw Exception('반응 전송에 실패했습니다 (${resp.statusCode})');
    }
    return Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)));
  }
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd comea && flutter test test/services/api_test.dart`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add comea/lib/services/api.dart comea/test/services/api_test.dart
git commit -m "feat(flutter): ApiService(baseUrl 단일화 + reactToPost) + MockClient 유닛테스트"
```

---

### Task 2: home_screen을 ApiService로 이관 + postId 전달

**Files:**
- Modify: `comea/lib/screens/home_screen.dart:1-4` (imports), `:13-16` (필드), `:31-45` (getPosts), `:58-82` (createPost)

**Model**: sonnet

> 검증: 이 task는 기존 동작을 ApiService로 이관하는 배선 변경이라 별도 테스트 대신 `flutter analyze`(컴파일/타입 통과)로 확인한다. 서비스 로직은 Task 1 유닛테스트가 커버.
> 주의: `DetailScreen` push에 `postId`를 넘기는 변경은 **Task 3**에서 한다(DetailScreen이 postId를 받게 되는 시점과 맞춰 한 커밋에서 정합 유지 → 중간 커밋도 컴파일 OK).

- [ ] **Step 1: import 정리 (http/convert 제거, api 추가)**

**원본** (`comea/lib/screens/home_screen.dart:1-4`):
```dart
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'detail_screen.dart';
```

**수정 후**:
```dart
import 'package:flutter/material.dart';
import 'detail_screen.dart';
import '../services/api.dart';
```

- [ ] **Step 2: ApiService 필드 추가**

**원본** (`comea/lib/screens/home_screen.dart:13-16`):
```dart
class _HomeScreenState extends State<HomeScreen> {
  List<Map<String, dynamic>> _posts = [];
  final TextEditingController _textController = TextEditingController();
  bool _isLoading = false;
```

**수정 후**:
```dart
class _HomeScreenState extends State<HomeScreen> {
  final ApiService _api = ApiService();
  List<Map<String, dynamic>> _posts = [];
  final TextEditingController _textController = TextEditingController();
  bool _isLoading = false;
```

- [ ] **Step 3: getPosts 이관**

**원본** (`comea/lib/screens/home_screen.dart:31-42`):
```dart
    try {
      final url = Uri.parse('http://172.28.0.1:8000/api/posts');
      final response = await http.get(url);

      if (response.statusCode == 200) {
        final List<dynamic> decodedData = jsonDecode(utf8.decode(response.bodyBytes));
        setState(() {
          _posts = List<Map<String, dynamic>>.from(decodedData);
        });
      } else {
        _showErrorSnackBar("데이터를 불러오는 중 오류가 발생했습니다.");
      }
    } catch (e) {
      _showErrorSnackBar("백엔드 서버와 통신할 수 없습니다.");
    } finally {
```

**수정 후**:
```dart
    try {
      final posts = await _api.getPosts();
      setState(() {
        _posts = posts;
      });
    } catch (e) {
      _showErrorSnackBar("데이터를 불러오는 중 오류가 발생했습니다.");
    } finally {
```

- [ ] **Step 4: createPost 이관 (+ id/is_locked 포함)**

**원본** (`comea/lib/screens/home_screen.dart:58-79`):
```dart
    try {
      final url = Uri.parse('http://172.28.0.1:8000/api/posts');
      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"content": content}),
      );

      if (response.statusCode == 200) {
        final dynamic decodedData = jsonDecode(utf8.decode(response.bodyBytes));
        
        setState(() {
          // 서버가 반환한 영구 저장된 객체를 리스트 맨 앞에 즉시 주입
          _posts.insert(0, {
            "content": decodedData["content"],
            "score": decodedData["score"],
            "comments": List<Map<String, dynamic>>.from(decodedData["comments"]),
          });
        });
      } else {
        _showErrorSnackBar("서버 응답 오류가 발생했습니다.");
      }
    } catch (e) {
      _showErrorSnackBar("서버와 통신할 수 없습니다.");
    } finally {
```

**수정 후**:
```dart
    try {
      final post = await _api.createPost(content);
      setState(() {
        // 서버가 반환한 영구 저장된 객체를 리스트 맨 앞에 즉시 주입 (id 포함 — 반응 호출에 필요)
        _posts.insert(0, {
          "id": post["id"],
          "content": post["content"],
          "score": post["score"],
          "is_locked": post["is_locked"],
          "comments": List<Map<String, dynamic>>.from(post["comments"]),
        });
      });
    } catch (e) {
      _showErrorSnackBar("서버와 통신할 수 없습니다.");
    } finally {
```

- [ ] **Step 5: 컴파일/타입 확인**

Run: `cd comea && flutter analyze`
Expected: `No issues found!` (push는 아직 기존 시그니처 그대로라 정상 컴파일. createPost가 넣는 `id`/`is_locked` 추가 키는 무해.)

- [ ] **Step 6: 커밋**

```bash
git add comea/lib/screens/home_screen.dart
git commit -m "refactor(flutter): home_screen을 ApiService로 이관(중복 baseURL 제거)"
```

---

### Task 3: detail_screen 반응 버튼 + 델타 머지 + 톤 카피

**Files:**
- Modify: `comea/lib/screens/detail_screen.dart` (전체 재작성 — 생성자/상태/initState/메서드/build)
- Modify: `comea/lib/screens/home_screen.dart:164-168` (DetailScreen push에 postId 전달)
- Test: `comea/test/screens/detail_reaction_test.dart`

**Model**: sonnet

- [ ] **Step 1: 실패하는 위젯 테스트 작성**

**수정 후** (new file: `comea/test/screens/detail_reaction_test.dart`):
```dart
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:comea/screens/detail_screen.dart';
import 'package:comea/services/api.dart';

http.Response _json(Object body) => http.Response(
      jsonEncode(body),
      200,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

void main() {
  testWidgets('좋아요/싫어요 버튼이 렌더된다', (tester) async {
    final api = ApiService(client: MockClient((req) async => _json({})));
    await tester.pumpWidget(MaterialApp(
      home: DetailScreen(
        postId: 1,
        postContent: '테스트 글',
        score: 70,
        realComments: const [],
        api: api,
      ),
    ));
    await tester.pump();

    expect(find.byKey(const Key('like-button')), findsOneWidget);
    expect(find.byKey(const Key('dislike-button')), findsOneWidget);
    await tester.pump(const Duration(seconds: 2)); // 잔여 타이머 정리
  });

  testWidgets('처리 중 연타해도 반응은 1번만 전송된다 (FR-7)', (tester) async {
    var calls = 0;
    final api = ApiService(client: MockClient((req) async {
      calls++;
      return _json({
        'id': 1,
        'content': 'x',
        'score': 70,
        'is_locked': false,
        'comments': const [],
      });
    }));
    await tester.pumpWidget(MaterialApp(
      home: DetailScreen(
        postId: 1,
        postContent: 'x',
        score: 70,
        realComments: const [],
        api: api,
      ),
    ));
    await tester.pump();

    await tester.tap(find.byKey(const Key('like-button')));
    await tester.tap(find.byKey(const Key('like-button'))); // 연타
    await tester.pump(const Duration(seconds: 3));

    expect(calls, 1); // _isReacting 가드로 중복 차단
  });
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea && flutter test test/screens/detail_reaction_test.dart`
Expected: FAIL — DetailScreen에 `postId`/`api` 파라미터, `Key('like-button')` 부재로 컴파일/매칭 실패

- [ ] **Step 3: detail_screen 전체 재작성**

**원본** (`comea/lib/screens/detail_screen.dart:1-143`):
```dart
import 'package:flutter/material.dart';

class DetailScreen extends StatefulWidget {
  final String postContent;
  final int score;
  final List<Map<String, dynamic>> realComments; // [수정] 서버에서 받아온 진짜 댓글들

  const DetailScreen({
    super.key,
    required this.postContent,
    required this.score,
    required this.realComments,
  });

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  final List<Map<String, dynamic>> _visibleComments = [];
  bool _isAiTyping = false;
  String _currentTypingAi = "";

  @override
  void initState() {
    super.initState();
    // 화면이 켜지면 서버에서 받아온 실제 AI 댓글들로 순차적 등장 연출 가동
    _simulateAiDispute();
  }

  void _simulateAiDispute() async {
    // 서버가 준 댓글 개수만큼만 루프 돌기 (점수가 낮으면 알아서 0개 혹은 적은 개수가 됨)
    for (int i = 0; i < widget.realComments.length; i++) {
      await Future.delayed(const Duration(milliseconds: 800)); // 생각 시간
      
      if (!mounted) return;
      setState(() {
        _isAiTyping = true;
        _currentTypingAi = widget.realComments[i]["name"] as String;
      });

      await Future.delayed(const Duration(milliseconds: 1500)); // 키보드 두드리는 시간

      if (!mounted) return;
      setState(() {
        _visibleComments.add(widget.realComments[i]);
        _isAiTyping = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isHot = widget.score >= 90;

    return Scaffold(
      appBar: AppBar(
        title: Text(isHot ? '🚨 실시간 끝장 토론' : '💬 대화 광장'),
        backgroundColor: isHot ? Colors.red.shade50 : Colors.blue.shade50,
      ),
      body: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            color: isHot ? Colors.red.shade50 : Colors.blue.shade50,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(widget.postContent, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.4)),
                const SizedBox(height: 12),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('채점 점수: ${widget.score}점', style: TextStyle(fontWeight: FontWeight.bold, color: isHot ? Colors.red : Colors.blue)),
                    Text('참여 완료: ${_visibleComments.length}/${widget.realComments.length}명', style: const TextStyle(color: Colors.grey)),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1),

          Expanded(
            child: _visibleComments.isEmpty && !_isAiTyping
                ? const Center(child: Text('이 글에는 AI 시민들이 조용히 침묵을 지키고 있습니다.', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    itemCount: _visibleComments.length,
                    itemBuilder: (context, index) {
                      final comment = _visibleComments[index];
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            CircleAvatar(
                              backgroundColor: Colors.deepPurple.shade100,
                              child: Text((comment["name"] as String)[0]),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(comment["name"] as String, style: const TextStyle(fontWeight: FontWeight.bold)),
                                  const SizedBox(height: 4),
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(color: Colors.grey.shade100, borderRadius: BorderRadius.circular(12)),
                                    child: Text(comment["comment"] as String, style: const TextStyle(fontSize: 14, height: 1.3)),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),

          if (_isAiTyping)
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.grey.shade50,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.deepPurple),
                  ),
                  const SizedBox(width: 12),
                  Text('⚡ $_currentTypingAi이(가) 키보드 배틀 참여를 준비 중입니다...', style: const TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w500)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
```

**수정 후**:
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

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  late List<Map<String, dynamic>> _allComments; // 지금까지 알려진 전체 댓글
  final List<Map<String, dynamic>> _visibleComments = []; // 등장 완료된 댓글
  bool _isAiTyping = false;
  String _currentTypingAi = "";
  bool _isReacting = false;

  @override
  void initState() {
    super.initState();
    _allComments = List<Map<String, dynamic>>.from(widget.realComments);
    _revealNewComments();
  }

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

  // 좋아요/싫어요 반응 → 갱신된 댓글로 교체 → 늘어난 만큼만 이어서 등장.
  Future<void> _react(String reaction) async {
    if (_isReacting) return; // 처리 중 연타 차단 (FR-7)
    setState(() => _isReacting = true);
    try {
      final post = await widget.api.reactToPost(widget.postId, reaction);
      _allComments = List<Map<String, dynamic>>.from(post["comments"]);
      await _revealNewComments();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('반응을 전송하지 못했습니다.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isReacting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isHot = widget.score >= 90;

    return Scaffold(
      appBar: AppBar(
        title: Text(isHot ? '🔥 인기 글' : '💬 글'),
        backgroundColor: isHot ? Colors.red.shade50 : Colors.blue.shade50,
      ),
      body: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            color: isHot ? Colors.red.shade50 : Colors.blue.shade50,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(widget.postContent, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.4)),
                const SizedBox(height: 12),
                Text('AI 시민 ${_visibleComments.length}명이 댓글을 남겼어요', style: const TextStyle(color: Colors.grey)),
              ],
            ),
          ),
          const Divider(height: 1),

          // 반응 버튼 줄 (수치 비노출 — 개수 표시 없음, FR-3)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                TextButton.icon(
                  key: const Key('like-button'),
                  onPressed: _isReacting ? null : () => _react('like'),
                  icon: const Icon(Icons.thumb_up_alt_outlined),
                  label: const Text('좋아요'),
                ),
                const SizedBox(width: 8),
                TextButton.icon(
                  key: const Key('dislike-button'),
                  onPressed: _isReacting ? null : () => _react('dislike'),
                  icon: const Icon(Icons.thumb_down_alt_outlined),
                  label: const Text('싫어요'),
                ),
                const Spacer(),
                if (_isReacting)
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.deepPurple),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),

          Expanded(
            child: _visibleComments.isEmpty && !_isAiTyping
                ? const Center(child: Text('아직 댓글이 없어요. 잠시 후 AI 시민들이 댓글을 남깁니다.', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    itemCount: _visibleComments.length,
                    itemBuilder: (context, index) {
                      final comment = _visibleComments[index];
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            CircleAvatar(
                              backgroundColor: Colors.deepPurple.shade100,
                              child: Text((comment["name"] as String)[0]),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(comment["name"] as String, style: const TextStyle(fontWeight: FontWeight.bold)),
                                  const SizedBox(height: 4),
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(color: Colors.grey.shade100, borderRadius: BorderRadius.circular(12)),
                                    child: Text(comment["comment"] as String, style: const TextStyle(fontSize: 14, height: 1.3)),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),

          if (_isAiTyping)
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.grey.shade50,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.deepPurple),
                  ),
                  const SizedBox(width: 12),
                  Text('$_currentTypingAi 님이 댓글을 작성 중...', style: const TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w500)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: home_screen push에 postId 전달**

**원본** (`comea/lib/screens/home_screen.dart:164-168`):
```dart
                              builder: (context) => DetailScreen(
                                postContent: post["content"] as String,
                                score: post["score"] as int,
                                realComments: List<Map<String, dynamic>>.from(post["comments"]),
                              ),
```

**수정 후**:
```dart
                              builder: (context) => DetailScreen(
                                postId: post["id"] as int,
                                postContent: post["content"] as String,
                                score: post["score"] as int,
                                realComments: List<Map<String, dynamic>>.from(post["comments"]),
                              ),
```

- [ ] **Step 5: 위젯 테스트 통과 확인**

Run: `cd comea && flutter test test/screens/detail_reaction_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 6: 전체 테스트 + 정적 분석**

Run: `cd comea && flutter test && flutter analyze`
Expected: 모든 테스트 PASS + `No issues found!` (home_screen push ↔ DetailScreen postId 정합 확인)

- [ ] **Step 7: 커밋**

```bash
git add comea/lib/screens/detail_screen.dart comea/lib/screens/home_screen.dart comea/test/screens/detail_reaction_test.dart
git commit -m "feat(flutter): 글 상세 반응 버튼 + 새 댓글 델타 등장 + 게시판 톤 카피"
```

---

## 2. 위험 코드 지점

- `comea/lib/screens/detail_screen.dart:_react` — **side-effect**: `reactToPost` 1회가 백엔드 동기 AI 생성을 유발해 응답이 수초 걸릴 수 있음. (mitigation: `_isReacting` 플래그로 처리 중 버튼 비활성 + 인디케이터, 응답 후 해제. 속도 비요구(NFR)라 지연 허용.)
- `comea/lib/screens/home_screen.dart:26-79` — **breaking**: getPosts/createPost를 ApiService로 이관 → 응답 파싱/에러 처리 동작이 바뀔 위험. (mitigation: 계약 동일 유지(반환 타입·키), Task 1 유닛테스트로 서비스 검증 + `flutter analyze` + 수동 확인.)
- `comea/lib/screens/detail_screen.dart:_react` / `_revealNewComments` — **race**: 화면 dispose 후 비동기 응답/딜레이 콜백 도착 시 `setState` 예외. (mitigation: 각 await 뒤 `if (!mounted) return` / `if (mounted)` 가드.)

## 3. 롤백 전략

- **Code:** Task별 커밋이므로 `git revert <SHA>` 역순(Task 3→1). 또는 `git reset --hard <Task1 직전 SHA>`.
- **부분 비활성화:** 반응 기능만 끄려면 `detail_screen`의 반응 버튼 Row를 주석 처리(나머지 영향 없음). ApiService/`postId` 전달은 무해하게 남길 수 있음.
- **API 주소:** baseURL은 `ApiService.baseUrl` 1곳 — 환경 변경 시 여기만 수정.
- **신규 의존성 없음** → 패키지 롤백 불필요.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 10:06] [구현계획서-수정]
- **id**: CH-20260617-003
- **이유**: 신규 구현계획서 작성 (Flutter 반응 버튼 UI, 3 TDD task)
- **무엇이**: flutter-reaction-ui-implementation-plan.md §1(Task 1~3), §2 위험, §3 롤백
- **영향범위**: comea/ — api.dart(신설), home_screen·detail_screen(수정), test 2파일. 실행순서 결함(중간 커밋 컴파일) 자체점검에서 수정.
- **연관 항목**: CH-20260617-001, CH-20260617-002

### [2026-06-17 10:48] [코드-수정] (batch: tasks 1..3)
- **id**: CH-20260617-004
- **이유**: Flutter 반응 버튼 UI 슬라이스 전체 구현(3 TDD task). ApiService 도입 + 상세 화면 좋아요/싫어요 버튼 + 새 댓글 델타 등장 + 게시판 톤 카피.
- **무엇이**: `comea/lib/services/api.dart`(신설), `comea/lib/screens/home_screen.dart`, `comea/lib/screens/detail_screen.dart`, `comea/test/services/api_test.dart`(신설), `comea/test/screens/detail_reaction_test.dart`(신설), `comea/test/widget_test.dart`(삭제)
- **영향범위**: DetailScreen 생성자에 `postId`/`api` 추가(호출부 home_screen 동시 갱신). baseURL이 ApiService 1곳으로. 반응 카운트 비노출 유지(서버+클라 모두 미표시).
- **위험 카테고리**: side-effect(동기 생성 지연 → _isReacting 가드), breaking(home_screen 이관 → 계약 동일+테스트), race(dispose 후 setState → mounted 가드) — 모두 §2 사전 식별·완화
- **task별 세부 (3건)**:
  - FT1: `lib/services/api.dart` — ApiService + MockClient 유닛테스트 4 (none) — commits: `a5d0d5d`
  - FT2: `lib/screens/home_screen.dart` — ApiService 이관 + 죽은 기본 widget_test 제거 (breaking) — commits: `a726d2b`
  - FT3: `lib/screens/detail_screen.dart`+`home_screen.dart` — 반응 버튼/델타/가드/톤 + 위젯테스트 2 (side-effect, race) — commits: `093e819`
- **계획 대비 보정 1건**: 기존 Flutter 기본 템플릿 `test/widget_test.dart`(존재하지 않는 `MyApp` 참조)가 analyze/test green을 막아 삭제(FT2에 포함). 계획 외 발견 정리.
- **테스트 결과**: flutter test 6 passed (api 4 + widget 2), flutter analyze No issues.
- **연관 commits**: `a5d0d5d..093e819` (3 커밋)
- **변경 전/후 코드**: 생략 — `git show <SHA>` 로 조회 (git-fast 모드)
- **연관 항목**: CH-20260617-003
