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

Map<String, dynamic> _post(int id, {String status = 'debating'}) => {
      'id': id,
      'content': '고민 내용. 자세한 사연.',
      'status': status,
      'score': 74,
      'base_limit': 15,
      'final_limit': 18,
      'likes': 3,
      'dislikes': 1,
      'net_reaction': 5,
      'comment_count': 4,
      'verdict': null,
      'created_at': '2026-07-04T01:00:00',
      'author_name': 'tester',
      'is_mine': true,
      'my_reaction': 'like',
      'score_breakdown': {'emotion': 4, 'controversy': 4, 'clarity': 3, 'novelty': 3},
      'core_claim': '창업이냐 잔류냐',
      'comments': [
        {
          'id': 1,
          'faction': 'ally',
          'persona_name': '따뜻한 논리학자',
          'content': '지지합니다',
          'turn_index': 0,
          'likes': 2,
          'dislikes': 0,
          'my_reaction': null,
          'created_at': '2026-07-04T01:01:00',
        },
      ],
    };

void main() {
  test('reactToPost: 갱신된 글(진영 댓글 포함)을 파싱한다', () async {
    final mock = MockClient((req) async {
      expect(req.method, 'POST');
      expect(req.url.path, '/api/posts/7/reaction');
      expect(jsonDecode(req.body)['reaction'], 'like');
      return _json(_post(7), 200);
    });
    final api = ApiService(client: mock);

    final post = await api.reactToPost(7, 'like');

    expect(post.id, 7);
    expect(post.status, 'debating');
    expect(post.finalLimit, 18);
    expect(post.comments, hasLength(1));
    expect(post.comments.first.faction, 'ally');
    expect(post.comments.first.personaName, '따뜻한 논리학자');
  });

  test('reactToPost: 비200 응답이면 ApiException', () async {
    final mock = MockClient((req) async => _json({'detail': '없는 글'}, 404));
    final api = ApiService(client: mock);

    expect(() => api.reactToPost(99, 'like'), throwsA(isA<ApiException>()));
  });

  test('fetchPosts: {"posts": [...]} 래핑 파싱', () async {
    final mock = MockClient((req) async => _json({
          'posts': [_post(1, status: 'concluded')]
        }, 200));
    final api = ApiService(client: mock);

    final posts = await api.fetchPosts();

    expect(posts, hasLength(1));
    expect(posts.first.id, 1);
    expect(posts.first.status, 'concluded');
    expect(posts.first.isLive, isFalse);
  });

  test('createPost: 201 즉시 반환(grading, 댓글 없음)', () async {
    final mock = MockClient((req) async {
      expect(req.url.path, '/api/posts');
      expect(jsonDecode(req.body)['content'], '고민');
      final body = _post(5, status: 'grading')
        ..['comments'] = []
        ..['score'] = null;
      return _json(body, 201);
    });
    final api = ApiService(client: mock);

    final post = await api.createPost('고민');

    expect(post.id, 5);
    expect(post.status, 'grading');
    expect(post.isLive, isTrue);
    expect(post.comments, isEmpty);
  });

  test('fetchPost: 상세 필드(쟁점·브레이크다운) 파싱', () async {
    final mock = MockClient((req) async {
      expect(req.url.path, '/api/posts/7');
      return _json(_post(7), 200);
    });
    final api = ApiService(client: mock);

    final post = await api.fetchPost(7);

    expect(post.coreClaim, '창업이냐 잔류냐');
    expect(post.scoreBreakdown!.emotion, 4);
    expect(post.myReaction, 'like');
  });
}
