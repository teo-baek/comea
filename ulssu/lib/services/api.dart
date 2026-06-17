import 'dart:convert';

import 'package:http/http.dart' as http;

/// ulssu 백엔드 HTTP 호출을 한곳에 모은 서비스.
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
