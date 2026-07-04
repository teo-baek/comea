import 'package:flutter/material.dart';

import '../tokens.dart';
import '../typography.dart';

/// 섹션 룰 — 방송 자막 바. 진영색 틱 + 헤어라인.
/// 섹션의 시작을 알린다. [title] 을 주면 오버라인 라벨을 함께 켠다.
class InkRule extends StatelessWidget {
  const InkRule({super.key, this.title, this.trailing, this.accent});

  final String? title;
  final Widget? trailing;

  /// 좌측 틱 색 (기본: 시안→오렌지 대전 그라데이션)
  final Color? accent;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Container(
              width: 26,
              height: 3,
              decoration: BoxDecoration(
                color: accent,
                gradient: accent == null
                    ? const LinearGradient(
                        colors: [ComeaColors.ally, ComeaColors.challenger])
                    : null,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(child: Container(height: 1, color: ComeaColors.line)),
          ],
        ),
        if (title != null) ...[
          const SizedBox(height: 9),
          Row(
            children: [
              Expanded(child: Text(title!.toUpperCase(), style: ComeaType.overline())),
              ?trailing,
            ],
          ),
        ],
      ],
    );
  }
}

/// Comea 워드마크 — 전광판 로고.
class ComeaWordmark extends StatelessWidget {
  const ComeaWordmark({super.key, this.size = 22, this.tagline = false});

  final double size;
  final bool tagline;

  @override
  Widget build(BuildContext context) {
    final mark = Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text('COMEA', style: ComeaType.display(size: size, spacing: 1.2)),
        const SizedBox(width: 8),
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(
            color: ComeaColors.live,
            shape: BoxShape.circle,
            boxShadow: ComeaColors.glow(ComeaColors.live, blur: 8, alpha: 0.7),
          ),
        ),
      ],
    );
    if (!tagline) return mark;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        mark,
        const SizedBox(height: 6),
        Text('사람은 쓰고, AI가 맞붙고, 투표가 판정한다',
            style: ComeaType.sans(
                size: 11.5, color: ComeaColors.textFaint, spacing: 1.4, weight: FontWeight.w600)),
      ],
    );
  }
}
