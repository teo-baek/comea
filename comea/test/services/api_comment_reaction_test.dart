import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:comea/services/api.dart';

void main() {
  test('reactToComment: 경로·헤더·바디가 올바르고 갱신 댓글을 반환한다', () async {
    String? path;
    String? auth;
    Map<String, dynamic>? body;
    final mock = MockClient((req) async {
      path = req.url.path;
      auth = req.headers['Authorization'];
      body = jsonDecode(req.body) as Map<String, dynamic>;
      return http.Response(
        jsonEncode({
          'id': 42,
          'faction': 'challenger',
          'persona_name': '직설적인 현실주의자',
          'content': '반박',
          'turn_index': 1,
          'likes': 5,
          'dislikes': 1,
          'my_reaction': 'like',
          'created_at': '2026-07-04T01:02:00',
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    final api = ApiService(client: mock)..token = 'TK';

    final comment = await api.reactToComment(42, 'like');

    expect(path, '/api/comments/42/reaction');
    expect(auth, 'Bearer TK');
    expect(body!['reaction'], 'like');
    expect(comment.likes, 5);
    expect(comment.myReaction, 'like');
  });
}
