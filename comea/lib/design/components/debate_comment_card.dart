import 'package:flutter/material.dart';

import '../tokens.dart';
import '../typography.dart';
import 'badges.dart';
import 'faction.dart';
import 'vote_pill.dart';

/// AI 토론 댓글 카드 — 호위대/도전자의 발언 한 턴.
/// 왼쪽 진영 스트라이프(발광)가 발언자의 코너를 표시하고,
/// 하단 투표 알약이 사람의 유일한 개입 지점이다.
class DebateCommentCard extends StatelessWidget {
  const DebateCommentCard({
    super.key,
    required this.faction,
    required this.personaName,
    required this.content,
    required this.likes,
    required this.dislikes,
    this.turnIndex,
    this.myReaction,
    this.onLike,
    this.onDislike,
    this.voteEnabled = true,
  });

  final Faction faction;
  final String personaName;
  final String content;
  final int likes;
  final int dislikes;
  final int? turnIndex;
  final String? myReaction; // "like" | "dislike" | null
  final VoidCallback? onLike;
  final VoidCallback? onDislike;
  final bool voteEnabled;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: ComeaColors.surface,
        border: Border.all(color: ComeaColors.line),
        borderRadius: BorderRadius.circular(ComeaRadii.card),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 진영 스트라이프 (발광)
            Container(
              width: 3.5,
              decoration: BoxDecoration(
                color: faction.color,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(ComeaRadii.card),
                  bottomLeft: Radius.circular(ComeaRadii.card),
                ),
                boxShadow: ComeaColors.glow(faction.color, blur: 7, alpha: 0.4),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 11),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Flexible(
                          child: Text(
                            personaName,
                            overflow: TextOverflow.ellipsis,
                            style: ComeaType.sans(
                                size: 14, weight: FontWeight.w800, height: 1.3),
                          ),
                        ),
                        const SizedBox(width: 8),
                        FactionBadge(faction, compact: true),
                        const Spacer(),
                        if (turnIndex != null)
                          Text(
                            '#${(turnIndex! + 1).toString().padLeft(2, '0')}',
                            style: ComeaType.mono(size: 10.5, color: ComeaColors.textFaint),
                          ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    Text(content, style: Theme.of(context).textTheme.bodyMedium),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        VotePill.like(
                          count: likes,
                          selected: myReaction == 'like',
                          onTap: onLike,
                          enabled: voteEnabled,
                        ),
                        const SizedBox(width: 8),
                        VotePill.dislike(
                          count: dislikes,
                          selected: myReaction == 'dislike',
                          onTap: onDislike,
                          enabled: voteEnabled,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 다음 발언을 기다리는 자리 — 송출 대기 커서.
/// "토론 중" 글의 댓글 목록 맨 아래에서 점멸한다.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          FadeTransition(
            opacity: Tween(begin: 0.15, end: 1.0)
                .animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut)),
            child: Container(
              width: 9,
              height: 15,
              decoration: BoxDecoration(
                color: ComeaColors.ally,
                boxShadow: ComeaColors.glow(ComeaColors.ally, blur: 8, alpha: 0.5),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Text('다음 논객이 마이크를 잡고 있습니다…',
              style: ComeaType.sans(size: 12.5, color: ComeaColors.textFaint)),
        ],
      ),
    );
  }
}
