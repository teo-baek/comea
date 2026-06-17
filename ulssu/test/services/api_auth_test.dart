import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/services/api.dart';

void main() {
  test('login: 토큰을 반환하고 ApiService에 보관된다', () async {
    final mock = MockClient((req) async {
      expect(req.url.path, '/api/auth/login');
      return http.Response(jsonEncode({'token': 'T123'}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final api = ApiService(client: mock);

    final token = await api.login('a@b.com', 'pw');

    expect(token, 'T123');
    expect(api.token, 'T123');
  });

  test('보호 요청에 Authorization 헤더가 붙는다', () async {
    String? seen;
    final mock = MockClient((req) async {
      seen = req.headers['Authorization'];
      return http.Response(jsonEncode({'id': 1, 'comments': []}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final api = ApiService(client: mock)..token = 'T999';

    await api.createPost('hi');

    expect(seen, 'Bearer T999');
  });
}
