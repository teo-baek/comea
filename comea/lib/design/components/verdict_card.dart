import 'package:flutter/material.dart';

import '../tokens.dart';
import '../typography.dart';
import 'duel_bar.dart';
import 'faction.dart';

/// 중재 판정 카드 — 방송의 최종 자막(로어서드).
/// 금색 테두리가 켜진 다크 패널에 판정과 개표 결과를 띄운다.
class VerdictCard extends StatelessWidget {
  const VerdictCard({
    super.key,
    required this.verdict,
    required this.moderatorName,
    required this.summary,
    required this.allyLikes,
    required this.challengerLikes,
  });

  final Verdict verdict;
  final String moderatorName;
  final String summary;
  final int allyLikes;
  final int challengerLikes;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: ComeaColors.surface,
        border: Border.all(color: ComeaColors.moderator, width: 1.4),
        borderRadius: BorderRadius.circular(ComeaRadii.card),
        boxShadow: ComeaColors.glow(ComeaColors.moderator, blur: 18, alpha: 0.18),
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('◈',
                  style: TextStyle(fontSize: 10, color: ComeaColors.moderator, height: 1)),
              const SizedBox(width: 6),
              Expanded(
                child: Text('중재 판정 — $moderatorName',
                    style: ComeaType.overline(color: ComeaColors.moderator)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            verdict.label,
            style: ComeaType.display(size: 26, color: verdict.color, height: 1.2)
                .copyWith(shadows: [
              Shadow(color: verdict.color.withValues(alpha: 0.45), blurRadius: 14),
            ]),
          ),
          const SizedBox(height: 8),
          Text(summary, style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 13),
          DuelBar(leftValue: allyLikes, rightValue: challengerLikes),
        ],
      ),
    );
  }
}
