import 'dart:async';

import 'package:flutter/material.dart';

import '../design/design.dart';
import '../models/models.dart';
import '../services/api.dart';

/// 토론 지면 — 사람의 글 아래에서 호위대와 도전자가 논쟁하고,
/// 댓글이 백엔드 생성 속도에 맞춰 "스르륵" 실린다. 2초 폴링.
class DetailScreen extends StatefulWidget {
  const DetailScreen({
    super.key,
    required this.api,
    required this.postId,
    this.initial,
  });

  final ApiService api;
  final int postId;
  final Post? initial;

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  Post? _post;
  Timer? _timer;
  String? _error;

  /// 첫 로드에 이미 실려 있던 댓글 — 시차 연출로 한 번에 공개
  Set<int>? _initialIds;

  @override
  void initState() {
    super.initState();
    _post = widget.initial;
    _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final post = await widget.api.fetchPost(widget.postId);
      if (!mounted) return;
      setState(() {
        _post = post;
        _error = null;
        _initialIds ??= post.comments.map((c) => c.id).toSet();
      });
      _syncPolling(post);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e is ApiException ? e.message : '글을 불러오지 못했습니다');
    }
  }

  void _syncPolling(Post post) {
    if (post.isLive) {
      _timer ??= Timer.periodic(const Duration(seconds: 2), (_) => _load());
    } else {
      _timer?.cancel();
      _timer = null;
    }
  }

  Future<void> _votePost(String reaction) async {
    final post = _post;
    if (post == null) return;
    final send = post.myReaction == reaction ? 'none' : reaction;
    try {
      final updated = await widget.api.reactToPost(post.id, send);
      if (!mounted) return;
      setState(() => _post = updated);
      _syncPolling(updated); // 투표로 재점화됐으면 폴링 재개
    } catch (e) {
      _toast(e);
    }
  }

  Future<void> _voteComment(CommentItem comment, String reaction) async {
    final send = comment.myReaction == reaction ? 'none' : reaction;
    try {
      await widget.api.reactToComment(comment.id, send);
      await _load(); // 집계·리밋·재점화까지 서버 기준으로 동기화
    } catch (e) {
      _toast(e);
    }
  }

  void _toast(Object e) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(e is ApiException ? e.message : '요청에 실패했습니다')));
  }

  @override
  Widget build(BuildContext context) {
    final post = _post;
    return Scaffold(
      appBar: AppBar(title: const Text('토론 지면')),
      body: post == null
          ? Center(
              child: _error == null
                  ? const CircularProgressIndicator(strokeWidth: 2)
                  : Text(_error!, style: Theme.of(context).textTheme.bodySmall),
            )
          : _buildBody(post),
    );
  }

  Widget _buildBody(Post post) {
    final text = Theme.of(context).textTheme;
    final debateComments = post.comments.where((c) => c.faction != 'moderator').toList();
    final moderatorComments = post.comments.where((c) => c.faction == 'moderator').toList();
    final allyLikes = debateComments
        .where((c) => c.faction == 'ally')
        .fold(0, (sum, c) => sum + c.likes);
    final challengerLikes = debateComments
        .where((c) => c.faction == 'challenger')
        .fold(0, (sum, c) => sum + c.likes);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 48),
      children: [
        // ── 원글 ──
        Row(
          children: [
            StatusTag(post.status),
            const Spacer(),
            if (post.authorName != null)
              Text(post.authorName!, style: ComeaType.mono(size: 11, color: ComeaColors.textFaint)),
          ],
        ),
        const SizedBox(height: 12),
        Text(post.content, style: text.bodyLarge),
        const SizedBox(height: 14),

        // ── 채점관의 쟁점 요약 ──
        if (post.coreClaim != null && post.coreClaim!.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.fromLTRB(14, 11, 14, 12),
            decoration: BoxDecoration(
              color: ComeaColors.surfaceHigh,
              borderRadius: BorderRadius.circular(ComeaRadii.card),
              border: const Border(left: BorderSide(color: ComeaColors.ally, width: 3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('쟁점 — 채점관', style: ComeaType.overline()),
                const SizedBox(height: 5),
                Text(post.coreClaim!,
                    style: ComeaType.sans(size: 15, weight: FontWeight.w700, height: 1.55)),
              ],
            ),
          ),
          const SizedBox(height: 14),
        ],

        // ── 점수 + 투표 ──
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (post.score != null) ScoreStamp(post.score!),
            if (post.score != null) const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      VotePill.like(
                        count: post.likes,
                        selected: post.myReaction == 'like',
                        onTap: () => _votePost('like'),
                      ),
                      const SizedBox(width: 8),
                      VotePill.dislike(
                        count: post.dislikes,
                        selected: post.myReaction == 'dislike',
                        onTap: () => _votePost('dislike'),
                      ),
                      const Spacer(),
                      if (post.finalLimit != null)
                        Text(
                          '논평 ${debateComments.length}/${post.finalLimit}',
                          style: ComeaType.mono(size: 11, color: ComeaColors.textFaint),
                        ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '투표가 쌓이면 토론이 길어지고, 판정이 뒤집힐 수 있습니다.',
                    style: ComeaType.sans(size: 11.5, color: ComeaColors.textFaint),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),

        // ── 토론 ──
        InkRule(
          title: '토론 · Debate',
          trailing: Text('${debateComments.length}',
              style: ComeaType.mono(size: 12, color: ComeaColors.textSoft)),
        ),
        const SizedBox(height: 14),

        if (debateComments.isEmpty && post.status == 'grading')
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 24),
            child: Column(
              children: [
                Text('채점관이 글을 읽고 있습니다…', style: text.bodySmall),
                const SizedBox(height: 4),
                Text('곧 호위대와 도전자가 도착합니다', style: ComeaType.sans(size: 11.5, color: ComeaColors.textFaint)),
              ],
            ),
          ),

        for (final comment in debateComments) ...[
          RevealIn(
            key: ValueKey('c-${comment.id}'),
            delay: _initialIds != null && _initialIds!.contains(comment.id)
                ? staggerDelay(debateComments.indexOf(comment).clamp(0, 8))
                : Duration.zero,
            child: DebateCommentCard(
              faction: Faction.parse(comment.faction),
              personaName: comment.personaName,
              content: comment.content,
              likes: comment.likes,
              dislikes: comment.dislikes,
              turnIndex: comment.turnIndex,
              myReaction: comment.myReaction,
              onLike: () => _voteComment(comment, 'like'),
              onDislike: () => _voteComment(comment, 'dislike'),
            ),
          ),
          const SizedBox(height: 10),
        ],

        if (post.status == 'debating') ...[
          const SizedBox(height: 2),
          const TypingIndicator(),
        ],

        // ── 중재 판정 ──
        for (final (i, m) in moderatorComments.indexed) ...[
          const SizedBox(height: 12),
          if (i == moderatorComments.length - 1 && Verdict.parse(post.verdict) != null)
            RevealIn(
              key: ValueKey('m-${m.id}'),
              child: VerdictCard(
                verdict: Verdict.parse(post.verdict)!,
                moderatorName: m.personaName,
                summary: m.content,
                allyLikes: allyLikes,
                challengerLikes: challengerLikes,
              ),
            )
          else
            RevealIn(
              key: ValueKey('m-${m.id}'),
              child: DebateCommentCard(
                faction: Faction.moderator,
                personaName: m.personaName,
                content: m.content,
                likes: m.likes,
                dislikes: m.dislikes,
                turnIndex: m.turnIndex,
                voteEnabled: false,
              ),
            ),
        ],
      ],
    );
  }
}
