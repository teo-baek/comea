import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/services/api.dart';

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
