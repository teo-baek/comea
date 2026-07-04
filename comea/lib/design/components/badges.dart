import 'package:flutter/material.dart';

import '../tokens.dart';
import '../typography.dart';
import 'faction.dart';

/// 진영 배지 — 전광판 부호(●◆◈) + 진영명. 팀 태그처럼.
class FactionBadge extends StatelessWidget {
  const FactionBadge(this.faction, {super.key, this.compact = false});

  final Faction faction;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 8, vertical: compact ? 1.5 : 3),
      decoration: BoxDecoration(
        color: faction.wash,
        border: Border.all(color: faction.color.withValues(alpha: 0.55), width: 1),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(faction.glyph,
              style: TextStyle(fontSize: compact ? 7 : 8, color: faction.color, height: 1)),
          SizedBox(width: compact ? 4 : 5),
          Text(
            faction.label,
            style: ComeaType.sans(
              size: compact ? 10.5 : 11.5,
              weight: FontWeight.w800,
              color: faction.color,
              spacing: 1.0,
              height: 1.25,
            ),
          ),
        ],
      ),
    );
  }
}

/// 글 상태 태그 — 채점 중 / LIVE 토론 중(점멸) / 판정 완료.
class StatusTag extends StatelessWidget {
  const StatusTag(this.status, {super.key});

  /// "grading" | "debating" | "concluded"
  final String status;

  @override
  Widget build(BuildContext context) {
    final (label, color, isLive) = switch (status) {
      'grading' => ('채점 중', ComeaColors.textFaint, true),
      'debating' => ('LIVE · 토론 중', ComeaColors.live, true),
      _ => ('판정 완료', ComeaColors.textSoft, false),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (isLive)
          _PulsingDot(color: color)
        else
          Text('◼', style: TextStyle(fontSize: 7, color: color, height: 1)),
        const SizedBox(width: 5),
        Text(label,
            style: ComeaType.sans(
                size: 11, weight: FontWeight.w800, color: color, spacing: 1.4, height: 1.2)),
      ],
    );
  }
}

class _PulsingDot extends StatefulWidget {
  const _PulsingDot({required this.color});
  final Color color;

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween(begin: 0.25, end: 1.0)
          .animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut)),
      child: Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(
          color: widget.color,
          shape: BoxShape.circle,
          boxShadow: ComeaColors.glow(widget.color, blur: 6, alpha: 0.6),
        ),
      ),
    );
  }
}

/// 화제성 스코어 타일 — 전광판의 점수판.
/// filled(발광 숫자 패널)와 outline 두 변형.
class ScoreStamp extends StatelessWidget {
  const ScoreStamp(this.score, {super.key, this.filled = true, this.tilt = false});

  final int score;
  final bool filled;
  final bool tilt; // 아레나 컨셉에서는 항상 수평 (호환용 파라미터)

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: filled ? ComeaColors.surfaceHigh : Colors.transparent,
        border: Border.all(
          color: filled ? ComeaColors.line : ComeaColors.line,
          width: 1.2,
        ),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('화제성',
              style: ComeaType.sans(
                size: 9,
                weight: FontWeight.w800,
                color: ComeaColors.textFaint,
                spacing: 2.6,
                height: 1.1,
              )),
          const SizedBox(height: 2),
          Text(
            score.toString().padLeft(2, '0'),
            style: ComeaType.mono(
              size: 21,
              weight: FontWeight.w700,
              color: filled ? ComeaColors.text : ComeaColors.textSoft,
              spacing: 0.5,
            ).copyWith(height: 1.05, shadows: [
              if (filled)
                Shadow(color: ComeaColors.text.withValues(alpha: 0.35), blurRadius: 10),
            ]),
          ),
        ],
      ),
    );
  }
}
