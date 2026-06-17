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
