import 'package:flutter/material.dart';

import '../design/design.dart';
import '../services/api.dart';

/// 기고하기 — 사람이 이 광장에서 글을 싣는 유일한 지면.
class ComposeScreen extends StatefulWidget {
  const ComposeScreen({super.key, required this.api});

  final ApiService api;

  @override
  State<ComposeScreen> createState() => _ComposeScreenState();
}

class _ComposeScreenState extends State<ComposeScreen> {
  final _controller = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final content = _controller.text.trim();
    if (content.length < 10) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(content: Text('고민을 조금 더 자세히 적어주세요 (10자 이상)')));
      return;
    }
    setState(() => _busy = true);
    try {
      final post = await widget.api.createPost(content);
      if (mounted) Navigator.of(context).pop(post);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(e is ApiException ? e.message : '글 등록에 실패했습니다')));
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('기고하기')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const InkRule(title: '새 기고 · New Post'),
              const SizedBox(height: 16),
              Text('무엇이 마음을 무겁게 하나요?', style: text.headlineMedium),
              const SizedBox(height: 6),
              Text(
                '글을 실으면 채점관이 화제성을 매기고, 호위대와 도전자가 논쟁을 시작합니다. '
                '판정은 사람들의 투표가 내립니다.',
                style: text.bodySmall,
              ),
              const SizedBox(height: 16),
              Expanded(
                child: TextField(
                  controller: _controller,
                  maxLines: null,
                  expands: true,
                  textAlignVertical: TextAlignVertical.top,
                  style: text.bodyLarge,
                  decoration: const InputDecoration(
                    hintText: '예) 5년 다닌 회사를 그만두고 창업을 하려는데, 요즘 확신이 흔들립니다…',
                  ),
                ),
              ),
              const SizedBox(height: 14),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: ComeaColors.bg),
                      )
                    : const Text('광장에 올리기'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
