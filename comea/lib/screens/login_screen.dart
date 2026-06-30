import 'package:flutter/material.dart';

import '../services/api.dart';

/// 로그인/가입 화면. 성공 시 onAuthed() 호출(상위가 홈으로 전환 + 토큰 영속화).
class LoginScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback onAuthed;

  const LoginScreen({super.key, required this.api, required this.onAuthed});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _isSignup = false;
  bool _busy = false;

  Future<void> _submit() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      if (_isSignup) {
        await widget.api.signup(_email.text.trim(), _password.text);
      } else {
        await widget.api.login(_email.text.trim(), _password.text);
      }
      widget.onAuthed();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_isSignup ? '가입 실패' : '로그인 실패'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isSignup ? '가입' : '로그인')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextField(
              key: const Key('email-field'),
              controller: _email,
              decoration: const InputDecoration(labelText: '이메일', border: OutlineInputBorder()),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('password-field'),
              controller: _password,
              decoration: const InputDecoration(labelText: '비밀번호', border: OutlineInputBorder()),
              obscureText: true,
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                key: const Key('login-button'),
                onPressed: _busy ? null : _submit,
                child: Text(_isSignup ? '가입하기' : '로그인'),
              ),
            ),
            TextButton(
              onPressed: _busy ? null : () => setState(() => _isSignup = !_isSignup),
              child: Text(_isSignup ? '이미 계정이 있어요 (로그인)' : '계정이 없어요 (가입)'),
            ),
          ],
        ),
      ),
    );
  }
}
