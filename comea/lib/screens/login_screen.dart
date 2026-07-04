import 'package:flutter/material.dart';

import '../design/design.dart';
import '../services/api.dart';

/// 로그인/가입 — 광장의 입구. 성공 시 onAuthed() 호출(상위가 홈 전환 + 토큰 영속화).
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

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (_email.text.trim().isEmpty || _password.text.isEmpty) {
      _toast('이메일과 비밀번호를 입력해주세요');
      return;
    }
    setState(() => _busy = true);
    try {
      if (_isSignup) {
        await widget.api.signup(_email.text.trim(), _password.text);
      } else {
        await widget.api.login(_email.text.trim(), _password.text);
      }
      widget.onAuthed();
    } catch (e) {
      _toast(e is ApiException ? e.message : (_isSignup ? '가입 실패' : '로그인 실패'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 40),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                RevealIn(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const ComeaWordmark(size: 42, tagline: true),
                      const SizedBox(height: 22),
                      const InkRule(),
                      const SizedBox(height: 14),
                      Text(_isSignup ? '광장에 합류하기' : '광장으로 입장', style: text.headlineMedium),
                      const SizedBox(height: 6),
                      Text(
                        _isSignup
                            ? '가입하면 당신 곁에 설 AI 논객이 한 명 배정됩니다.'
                            : '당신의 고민에 AI들이 찬반으로 논쟁하고, 사람들의 투표가 판정합니다.',
                        style: text.bodySmall,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                RevealIn(
                  delay: staggerDelay(1),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextField(
                        key: const Key('email-field'),
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                        decoration: const InputDecoration(hintText: '이메일'),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        key: const Key('password-field'),
                        controller: _password,
                        obscureText: true,
                        onSubmitted: (_) => _submit(),
                        decoration: const InputDecoration(hintText: '비밀번호'),
                      ),
                      const SizedBox(height: 18),
                      FilledButton(
                        key: const Key('login-button'),
                        onPressed: _busy ? null : _submit,
                        child: _busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: ComeaColors.bg),
                              )
                            : Text(_isSignup ? '가입하고 입장' : '로그인'),
                      ),
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: _busy ? null : () => setState(() => _isSignup = !_isSignup),
                        child: Text(_isSignup ? '이미 계정이 있어요 — 로그인' : '처음이신가요? — 가입하기'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
