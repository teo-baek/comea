import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/screens/login_screen.dart';
import 'package:ulssu/services/api.dart';

void main() {
  testWidgets('이메일/비번 입력 후 로그인 탭 → onAuthed 콜백', (tester) async {
    final api = ApiService(client: MockClient((req) async => http.Response(
        jsonEncode({'token': 'T1'}), 200,
        headers: {'content-type': 'application/json; charset=utf-8'})));
    var authed = false;

    await tester.pumpWidget(MaterialApp(
      home: LoginScreen(api: api, onAuthed: () => authed = true),
    ));

    await tester.enterText(find.byKey(const Key('email-field')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password-field')), 'pw123456');
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();
    await tester.pump();

    expect(authed, isTrue);
    expect(api.token, 'T1');
  });
}
