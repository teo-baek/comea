---
commit_policy: per-task
---

# 댓글 단위 반응 구현계획서

> **다음 단계 안내**: `js-super-sub-driven`(권장) 또는 `executing-plans`로 task-by-task 실행.

**Goal:** `comment_reactions` 테이블(유저·댓글당 1개, upsert) + `POST /api/comments/{id}/reaction`(로그인 필수) + Flutter 댓글별 좋아요/싫어요 버튼. 글 단위 반응/한계선 불변, 개수 비노출. 진화 엔진(다음)의 신호 수집.

**Architecture:** 별도 테이블 + upsert 엔드포인트(get_current_user). 선호 페르소나는 `comments.name`으로 매핑(진화 엔진이 집계). Flutter 댓글 타일 버튼 + 로컬 선택 상태.

**Tech Stack:** FastAPI, SQLAlchemy / Flutter, http. 테스트 SQLite/MockClient.

**Spec inputs:**
- `comment-reactions-requirements.md` — FR-1~6, AC-1~6
- `comment-reactions-tech-design.md` — D1(별도 테이블) D2(upsert) D3(comments.name 매핑) D4(타일 버튼)

---

## 1. 단계별 작업

### Task 1: 백엔드 — `comment_reactions` + 엔드포인트 + 마이그레이션

**Files:**
- Modify: `ulssu_backend/database.py:2` (import), `ulssu_backend/database.py` (CommentReactionModel)
- Modify: `ulssu_backend/main.py:15` (import), `ulssu_backend/main.py` 끝(엔드포인트)
- Create: `ulssu_backend/migrations/004_add_comment_reactions.sql`
- Test: `ulssu_backend/tests/test_comment_reaction.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 통합 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_comment_reaction.py`):
```python
import database
import main
from database import CommentReactionModel


def _create_post_with_comments(auth_client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # 잡담 base 10
    return auth_client.post("/api/posts", json={"content": "테스트"}).json()


def _comment_reaction_rows(comment_id):
    db = next(main.app.dependency_overrides[database.get_db]())
    try:
        return db.query(CommentReactionModel).filter(CommentReactionModel.comment_id == comment_id).all()
    finally:
        db.close()


def test_comment_reaction_upsert(auth_client, monkeypatch):
    post = _create_post_with_comments(auth_client, monkeypatch)
    comment_id = post["comments"][0]["id"]

    r1 = auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "like"})
    assert r1.status_code == 200
    rows = _comment_reaction_rows(comment_id)
    assert len(rows) == 1 and rows[0].reaction_type == "like"

    # 같은 유저·댓글 재호출 → 갱신(여전히 1건, dislike)
    auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "dislike"})
    rows = _comment_reaction_rows(comment_id)
    assert len(rows) == 1 and rows[0].reaction_type == "dislike"


def test_comment_reaction_requires_token(client, monkeypatch):
    # 무토큰 401
    assert client.post("/api/comments/1/reaction", json={"reaction": "like"}).status_code == 401


def test_comment_reaction_missing_comment_404(auth_client):
    assert auth_client.post("/api/comments/99999/reaction", json={"reaction": "like"}).status_code == 404


def test_comment_reaction_invalid_400(auth_client, monkeypatch):
    post = _create_post_with_comments(auth_client, monkeypatch)
    cid = post["comments"][0]["id"]
    assert auth_client.post(f"/api/comments/{cid}/reaction", json={"reaction": "love"}).status_code == 400
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_comment_reaction.py -v`
Expected: FAIL — `404`/`ImportError: cannot import name 'CommentReactionModel'`

- [ ] **Step 3: database.py import에 UniqueConstraint 추가**

**원본** (`ulssu_backend/database.py:2`):
```python
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Boolean, DateTime, func, JSON
```

**수정 후**:
```python
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Boolean, DateTime, func, JSON, UniqueConstraint
```

- [ ] **Step 4: CommentReactionModel 추가 (AiPersonaModel 아래, get_db 위)**

**원본** (`ulssu_backend/database.py`):
```python
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


def get_db():
```

**수정 후**:
```python
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class CommentReactionModel(Base):
    # 댓글 단위 좋아요/싫어요(진화 신호). 유저·댓글당 1개(upsert). 어떤 페르소나 선호인지는 comments.name 으로 매핑.
    __tablename__ = "comment_reactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False)
    reaction_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "comment_id", name="uq_user_comment"),)


def get_db():
```

- [ ] **Step 5: main.py import에 CommentReactionModel 추가**

**원본** (`ulssu_backend/main.py:15`):
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel, AiPersonaModel
```

**수정 후**:
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel, AiPersonaModel, CommentReactionModel
```

- [ ] **Step 6: 댓글 반응 엔드포인트 추가 (파일 끝에 append)**

**수정 후** (append to `ulssu_backend/main.py`):
```python


# 📌 4. 댓글 단위 반응(진화 신호 수집) — 유저·댓글당 1개 upsert. 한계선/생성에 영향 없음.
@app.post("/api/comments/{comment_id}/reaction")
def react_to_comment(
    comment_id: int,
    request: ReactionRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),  # 로그인 필수
):
    comment = db.query(CommentModel).filter(CommentModel.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=404, detail="comment not found")
    if request.reaction not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="reaction must be 'like' or 'dislike'")

    existing = (
        db.query(CommentReactionModel)
        .filter(
            CommentReactionModel.user_id == current_user.id,
            CommentReactionModel.comment_id == comment_id,
        )
        .first()
    )
    if existing is not None:
        existing.reaction_type = request.reaction  # 재반응 → 교체(upsert)
    else:
        db.add(CommentReactionModel(
            user_id=current_user.id,
            comment_id=comment_id,
            reaction_type=request.reaction,
        ))
    db.commit()
    return {"ok": True}  # 개수 비노출 (FR-3)
```

- [ ] **Step 7: 마이그레이션 SQL 작성**

**수정 후** (new file: `ulssu_backend/migrations/004_add_comment_reactions.sql`):
```sql
-- 004_add_comment_reactions.sql
-- comment-reactions 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 적용:  psql "$DATABASE_URL" -f migrations/004_add_comment_reactions.sql

CREATE TABLE IF NOT EXISTS comment_reactions (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    comment_id    INTEGER NOT NULL REFERENCES comments(id),
    reaction_type VARCHAR NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_comment UNIQUE (user_id, comment_id)
);

-- 롤백 (down):
--   DROP TABLE IF EXISTS comment_reactions;
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_comment_reaction.py -v`
Expected: PASS (4 passed)

- [ ] **Step 9: 커밋**

```bash
git add ulssu_backend/database.py ulssu_backend/main.py ulssu_backend/migrations/004_add_comment_reactions.sql ulssu_backend/tests/test_comment_reaction.py
git commit -m "feat(backend): comment_reactions(upsert) + 댓글 반응 엔드포인트 + 마이그레이션"
```

---

### Task 2: Flutter — ApiService.reactToComment + 댓글 타일 버튼

**Files:**
- Modify: `ulssu/lib/services/api.dart` (reactToComment)
- Modify: `ulssu/lib/screens/detail_screen.dart` (_commentReactions 상태 + _reactToComment + 타일 버튼)
- Test: `ulssu/test/services/api_comment_reaction_test.dart`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu/test/services/api_comment_reaction_test.dart`):
```dart
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/services/api.dart';

void main() {
  test('reactToComment: 경로·헤더·바디가 올바르다', () async {
    String? path;
    String? auth;
    Map<String, dynamic>? body;
    final mock = MockClient((req) async {
      path = req.url.path;
      auth = req.headers['Authorization'];
      body = jsonDecode(req.body) as Map<String, dynamic>;
      return http.Response(jsonEncode({'ok': true}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final api = ApiService(client: mock)..token = 'TK';

    await api.reactToComment(42, 'like');

    expect(path, '/api/comments/42/reaction');
    expect(auth, 'Bearer TK');
    expect(body!['reaction'], 'like');
  });
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu && flutter test test/services/api_comment_reaction_test.dart`
Expected: FAIL — `reactToComment` 미존재로 컴파일 실패

- [ ] **Step 3: ApiService에 reactToComment 추가**

**원본** (`ulssu/lib/services/api.dart` — reactToPost 메서드 끝):
```dart
    if (resp.statusCode != 200) {
      throw Exception('반응 전송에 실패했습니다 (${resp.statusCode})');
    }
    return Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)));
  }
}
```

**수정 후**:
```dart
    if (resp.statusCode != 200) {
      throw Exception('반응 전송에 실패했습니다 (${resp.statusCode})');
    }
    return Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)));
  }

  Future<void> reactToComment(int commentId, String reaction) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/comments/$commentId/reaction'),
      headers: _headers(auth: true),
      body: jsonEncode({'reaction': reaction}),
    );
    if (resp.statusCode != 200) {
      throw Exception('댓글 반응 전송에 실패했습니다 (${resp.statusCode})');
    }
  }
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ulssu && flutter test test/services/api_comment_reaction_test.dart`
Expected: PASS (1 test)

- [ ] **Step 5: detail_screen에 댓글 반응 상태 + 핸들러 추가**

**원본** (`ulssu/lib/screens/detail_screen.dart:30`):
```dart
  bool _isReacting = false;
```

**수정 후**:
```dart
  bool _isReacting = false;
  final Map<int, String> _commentReactions = {}; // comment_id → 'like'|'dislike' (로컬 선택 표시)

  Future<void> _reactToComment(int commentId, String reaction) async {
    final prev = _commentReactions[commentId];
    setState(() => _commentReactions[commentId] = reaction);
    try {
      await widget.api.reactToComment(commentId, reaction);
    } catch (e) {
      if (mounted) {
        setState(() {
          if (prev == null) {
            _commentReactions.remove(commentId);
          } else {
            _commentReactions[commentId] = prev;
          }
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('댓글 반응을 보내지 못했습니다.'), backgroundColor: Colors.red),
        );
      }
    }
  }
```

- [ ] **Step 6: 댓글 타일에 좋아요/싫어요 버튼 추가**

**원본** (`ulssu/lib/screens/detail_screen.dart` — 댓글 본문 Container + Column 닫힘):
```dart
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(color: Colors.grey.shade100, borderRadius: BorderRadius.circular(12)),
                                    child: Text(comment["comment"] as String, style: const TextStyle(fontSize: 14, height: 1.3)),
                                  ),
                                ],
```

**수정 후**:
```dart
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(color: Colors.grey.shade100, borderRadius: BorderRadius.circular(12)),
                                    child: Text(comment["comment"] as String, style: const TextStyle(fontSize: 14, height: 1.3)),
                                  ),
                                  Builder(builder: (_) {
                                    final cid = comment["id"] as int;
                                    final picked = _commentReactions[cid];
                                    return Row(
                                      children: [
                                        IconButton(
                                          iconSize: 18,
                                          visualDensity: VisualDensity.compact,
                                          color: picked == 'like' ? Colors.deepPurple : Colors.grey,
                                          icon: const Icon(Icons.thumb_up_alt_outlined),
                                          onPressed: () => _reactToComment(cid, 'like'),
                                        ),
                                        IconButton(
                                          iconSize: 18,
                                          visualDensity: VisualDensity.compact,
                                          color: picked == 'dislike' ? Colors.deepPurple : Colors.grey,
                                          icon: const Icon(Icons.thumb_down_alt_outlined),
                                          onPressed: () => _reactToComment(cid, 'dislike'),
                                        ),
                                      ],
                                    );
                                  }),
                                ],
```

- [ ] **Step 7: 전체 테스트 + 정적 분석**

Run: `cd ulssu && flutter test && flutter analyze`
Expected: 모든 테스트 PASS + `No issues found!`

- [ ] **Step 8: 커밋**

```bash
git add ulssu/lib/services/api.dart ulssu/lib/screens/detail_screen.dart ulssu/test/services/api_comment_reaction_test.dart
git commit -m "feat(flutter): ApiService.reactToComment + 댓글 타일 좋아요/싫어요 버튼"
```

---

## 2. 위험 코드 지점

- `ulssu_backend/database.py:CommentReactionModel` — **breaking**: `comment_reactions` 테이블 신설. 운영 DB `create_all` 미반영 가능. (mitigation: `migrations/004_*.sql` 멱등. dev는 재생성.)
- `ulssu_backend/main.py:react_to_comment` / `ulssu/lib/screens/detail_screen.dart:_reactToComment` — **side-effect**: 댓글마다 버튼 + API 호출. (mitigation: 수집 전용 — 한계선/댓글 생성 무영향(별도 테이블·경로). Flutter 실패 시 로컬 상태 원복 + 스낵바.)

## 3. 롤백 전략

- **Code:** Task별 커밋 역순 `git revert`. 댓글 버튼만 끄려면 detail_screen의 Builder 블록 제거.
- **DB:** `migrations/004_*.sql` 하단 down SQL. dev는 재생성.
- **신규 의존성:** 없음.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 14:05] [구현계획서-수정]
- **id**: CH-20260617-002
- **이유**: 신규 구현계획서 작성 (댓글 단위 반응, 2 TDD task)
- **무엇이**: comment-reactions-implementation-plan.md §1(Task 1~2), §2 위험, §3 롤백
- **영향범위**: ulssu_backend(comment_reactions·엔드포인트·migration 004)·ulssu(api·detail_screen 타일 버튼).
- **연관 항목**: CH-20260617-001

### [2026-06-17 14:15] [코드-수정] (batch: tasks 1..2)
- **id**: CH-20260617-003
- **이유**: 댓글 단위 반응(진화 신호 수집) 구현(2 task). comment_reactions upsert + 엔드포인트 + Flutter 댓글 타일 버튼.
- **무엇이**: `ulssu_backend/database.py`(CommentReactionModel+UniqueConstraint), `main.py`(엔드포인트+import), `migrations/004_*.sql`(신설), `tests/test_comment_reaction.py`(신설), `ulssu/lib/services/api.dart`(reactToComment), `screens/detail_screen.dart`(타일 버튼+상태+핸들러), `test/services/api_comment_reaction_test.dart`(신설)
- **영향범위**: 신규 `POST /api/comments/{id}/reaction`(로그인 필수, upsert). 글 단위 반응/한계선/댓글 생성 불변. 선호 페르소나는 comments.name 으로 매핑(진화 엔진 입력). 개수 비노출.
- **위험 카테고리**: breaking(스키마→migration 004), side-effect(타일 버튼/호출, 수집 전용) — §2 사전 식별
- **task별 세부 (2건)**:
  - CR1: `database.py`/`main.py`/`migrations/004` — comment_reactions+엔드포인트 (breaking) — `b9971d4`
  - CR2: `api.dart`/`detail_screen.dart` — reactToComment+타일 버튼 (side-effect) — `56b6ef3`
- **테스트 결과**: 백엔드 +4(comment_reaction), Flutter 14 passed, analyze No issues.
- **연관 commits**: `b9971d4..56b6ef3`
- **변경 전/후 코드**: 생략 — `git show <SHA>`
- **연관 항목**: CH-20260617-002
