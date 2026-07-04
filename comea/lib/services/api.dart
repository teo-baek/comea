import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/models.dart';

/// Comea 백엔드(8247) API 클라이언트 — docs/stage2-backend-spec.md §8 과 1:1.
/// baseUrl 단일화 + http.Client 주입(테스트 시 MockClient 사용).
/// baseUrl 은 `--dart-define=API_BASE=...` 로 재정의 가능.
class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://127.0.0.1:8247/api',
  );

  final http.Client _client;
  String? token; // 로그인 후 JWT (보호 요청에 첨부)

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  void logout() => token = null;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Never _fail(http.Response res, String fallback) {
    String message = '$fallback (${res.statusCode})';
    try {
      final body = jsonDecode(utf8.decode(res.bodyBytes));
      if (body is Map && body['detail'] is String) {
        message = body['detail'] as String;
      }
    } catch (_) {}
    throw ApiException(message, res.statusCode);
  }

  dynamic _decode(http.Response res) => jsonDecode(utf8.decode(res.bodyBytes));

  Future<String> signup(String email, String password) async {
    final res = await _client.post(
      Uri.parse('$baseUrl/auth/signup'),
      headers: _headers,
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (res.statusCode != 201 && res.statusCode != 200) _fail(res, '가입에 실패했습니다');
    token = (_decode(res) as Map<String, dynamic>)['token'] as String;
    return token!;
  }

  Future<String> login(String email, String password) async {
    final res = await _client.post(
      Uri.parse('$baseUrl/auth/login'),
      headers: _headers,
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (res.statusCode != 200) _fail(res, '로그인에 실패했습니다');
    token = (_decode(res) as Map<String, dynamic>)['token'] as String;
    return token!;
  }

  Future<List<Post>> fetchPosts() async {
    final res = await _client.get(Uri.parse('$baseUrl/posts'), headers: _headers);
    if (res.statusCode != 200) _fail(res, '글 목록을 불러오지 못했습니다');
    final body = _decode(res);
    final list = body is Map<String, dynamic>
        ? (body['posts'] as List<dynamic>? ?? const [])
        : body as List<dynamic>;
    return list.whereType<Map<String, dynamic>>().map(Post.fromJson).toList();
  }

  Future<Post> createPost(String content) async {
    final res = await _client.post(
      Uri.parse('$baseUrl/posts'),
      headers: _headers,
      body: jsonEncode({'content': content}),
    );
    if (res.statusCode != 201 && res.statusCode != 200) _fail(res, '글 등록에 실패했습니다');
    return Post.fromJson(_decode(res) as Map<String, dynamic>);
  }

  Future<Post> fetchPost(int id) async {
    final res = await _client.get(Uri.parse('$baseUrl/posts/$id'), headers: _headers);
    if (res.statusCode != 200) _fail(res, '글을 불러오지 못했습니다');
    return Post.fromJson(_decode(res) as Map<String, dynamic>);
  }

  /// reaction: "like" | "dislike" | "none"(취소)
  Future<Post> reactToPost(int postId, String reaction) async {
    final res = await _client.post(
      Uri.parse('$baseUrl/posts/$postId/reaction'),
      headers: _headers,
      body: jsonEncode({'reaction': reaction}),
    );
    if (res.statusCode != 200) _fail(res, '반응 전송에 실패했습니다');
    return Post.fromJson(_decode(res) as Map<String, dynamic>);
  }

  Future<CommentItem> reactToComment(int commentId, String reaction) async {
    final res = await _client.post(
      Uri.parse('$baseUrl/comments/$commentId/reaction'),
      headers: _headers,
      body: jsonEncode({'reaction': reaction}),
    );
    if (res.statusCode != 200) _fail(res, '댓글 반응 전송에 실패했습니다');
    return CommentItem.fromJson(_decode(res) as Map<String, dynamic>);
  }
}

class ApiException implements Exception {
  ApiException(this.message, this.statusCode);

  final String message;
  final int statusCode;

  @override
  String toString() => message;
}
