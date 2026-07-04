import 'package:flutter/material.dart';

import '../design/design.dart';
import '../models/models.dart';
import '../services/api.dart';
import '../widgets/post_card.dart';
import 'compose_screen.dart';
import 'detail_screen.dart';

/// 홈 — 오늘의 광장(피드). 사람의 글이 실리고, AI의 논평이 붙는 1면.
class HomeScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback? onLogout;

  HomeScreen({super.key, ApiService? api, this.onLogout}) : api = api ?? ApiService();

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  ApiService get _api => widget.api;
  List<Post> _posts = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final posts = await _api.fetchPosts();
      if (!mounted) return;
      setState(() {
        _posts = posts;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e is ApiException ? e.message : '글 목록을 불러오지 못했습니다';
      });
    }
  }

  Future<void> _openCompose() async {
    final created = await Navigator.of(context).push<Post>(
      MaterialPageRoute(builder: (_) => ComposeScreen(api: _api)),
    );
    if (created == null || !mounted) return;
    setState(() => _posts = [created, ..._posts]);
    await _openDetail(created); // 등록 직후 토론이 벌어지는 지면으로 직행
  }

  Future<void> _openDetail(Post post) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => DetailScreen(api: _api, postId: post.id, initial: post),
      ),
    );
    if (mounted) _refresh(); // 돌아오면 투표·댓글 수 갱신
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        title: const ComeaWordmark(size: 21),
        actions: [
          IconButton(
            tooltip: '로그아웃',
            onPressed: widget.onLogout,
            icon: const Icon(Icons.logout, size: 20, color: ComeaColors.textSoft),
          ),
          const SizedBox(width: 6),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCompose,
        backgroundColor: ComeaColors.text,
        foregroundColor: ComeaColors.bg,
        elevation: 2,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(ComeaRadii.card)),
        icon: const Icon(Icons.edit_outlined, size: 18),
        label: Text('기고하기', style: ComeaType.sans(size: 14, weight: FontWeight.w800, color: ComeaColors.bg)),
      ),
      body: RefreshIndicator(
        color: ComeaColors.text,
        onRefresh: _refresh,
        child: _loading
            ? const Center(child: CircularProgressIndicator(strokeWidth: 2))
            : ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 96),
                children: [
                  const InkRule(title: '오늘의 광장 · The Forum'),
                  const SizedBox(height: 14),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 40),
                      child: Column(
                        children: [
                          Text('지면을 불러오지 못했습니다', style: text.titleMedium),
                          const SizedBox(height: 6),
                          Text(_error!, style: text.bodySmall, textAlign: TextAlign.center),
                          const SizedBox(height: 14),
                          OutlinedButton(onPressed: _refresh, child: const Text('다시 시도')),
                        ],
                      ),
                    )
                  else if (_posts.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 56),
                      child: Column(
                        children: [
                          Text('◈', style: TextStyle(fontSize: 22, color: ComeaColors.textFaint)),
                          const SizedBox(height: 12),
                          Text('아직 지면이 비어 있습니다', style: text.headlineSmall),
                          const SizedBox(height: 6),
                          Text('첫 고민을 실으면 AI 논객들이 찬반 논평을 시작합니다.',
                              style: text.bodySmall, textAlign: TextAlign.center),
                        ],
                      ),
                    )
                  else
                    for (final (i, post) in _posts.indexed) ...[
                      RevealIn(
                        key: ValueKey('post-${post.id}'),
                        delay: staggerDelay(i < 6 ? i : 6, base: const Duration(milliseconds: 70)),
                        child: PostCard(post: post, onTap: () => _openDetail(post)),
                      ),
                      const SizedBox(height: 10),
                    ],
                ],
              ),
      ),
    );
  }
}
