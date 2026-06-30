import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:comea/screens/detail_screen.dart';
import 'package:comea/services/api.dart';

void main() {
  testWidgets('댓글이 백엔드 순서대로 결정적으로 등장한다', (tester) async {
    final api = ApiService(client: MockClient((req) async => http.Response(
          jsonEncode({}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        )));
    await tester.pumpWidget(MaterialApp(
      home: DetailScreen(
        postId: 1,
        postContent: 'x',
        score: 70,
        realComments: const [
          {'id': 1, 'post_id': 1, 'name': 'A', 'comment': 'first'},
          {'id': 2, 'post_id': 1, 'name': 'B', 'comment': 'second'},
          {'id': 3, 'post_id': 1, 'name': 'C', 'comment': 'third'},
        ],
        api: api,
        rng: Random(1), // 시드 고정 → 결정적
      ),
    ));

    // gap은 순차 누적(댓글 3개 × 최대 30초)이라 안전하게 95초 진행 → 3개 모두 등장
    await tester.pump(const Duration(seconds: 95));

    expect(find.text('first'), findsOneWidget);
    expect(find.text('second'), findsOneWidget);
    expect(find.text('third'), findsOneWidget);

    final firstY = tester.getTopLeft(find.text('first')).dy;
    final secondY = tester.getTopLeft(find.text('second')).dy;
    final thirdY = tester.getTopLeft(find.text('third')).dy;
    expect(firstY, lessThan(secondY)); // 화면상 first가 second 위
    expect(secondY, lessThan(thirdY));
  });
}
