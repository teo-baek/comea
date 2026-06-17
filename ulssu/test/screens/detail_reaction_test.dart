import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/screens/detail_screen.dart';
import 'package:ulssu/services/api.dart';

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
