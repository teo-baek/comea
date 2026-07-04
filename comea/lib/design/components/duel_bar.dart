import 'package:flutter/material.dart';

import '../tokens.dart';
import '../typography.dart';

/// 대전 게이지 — 두 세력의 표가 전광판 위에서 밀고 당기는 개표 바.
/// 판정 카드(호위대 vs 도전자), 글의 찬반(좋아요 vs 싫어요) 등에 쓴다.
class DuelBar extends StatelessWidget {
  const DuelBar({
    super.key,
    required this.leftValue,
    required this.rightValue,
    this.leftLabel = '호위대',
    this.rightLabel = '도전자',
    this.leftColor = ComeaColors.ally,
    this.rightColor = ComeaColors.challenger,
    this.showCounts = true,
    this.height = 10,
  });

  final int leftValue;
  final int rightValue;
  final String leftLabel;
  final String rightLabel;
  final Color leftColor;
  final Color rightColor;
  final bool showCounts;
  final double height;

  @override
  Widget build(BuildContext context) {
    final total = leftValue + rightValue;
    final leftRatio = total == 0 ? 0.5 : leftValue / total;
    final empty = total == 0;
    final leftPct = (leftRatio * 100).round();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showCounts) ...[
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('$leftLabel ',
                  style: ComeaType.sans(
                      size: 11, weight: FontWeight.w800, color: leftColor, spacing: 0.8)),
              Text(empty ? '-' : '$leftPct%',
                  style: ComeaType.mono(size: 14, color: leftColor, weight: FontWeight.w700)),
              Text('  $leftValue', style: ComeaType.mono(size: 10.5, color: ComeaColors.textFaint)),
              const Spacer(),
              Text('$rightValue  ', style: ComeaType.mono(size: 10.5, color: ComeaColors.textFaint)),
              Text(empty ? '-' : '${100 - leftPct}%',
                  style: ComeaType.mono(size: 14, color: rightColor, weight: FontWeight.w700)),
              Text(' $rightLabel',
                  style: ComeaType.sans(
                      size: 11, weight: FontWeight.w800, color: rightColor, spacing: 0.8)),
            ],
          ),
          const SizedBox(height: 6),
        ],
        SizedBox(
          height: height,
          child: Row(
            children: [
              Expanded(
                flex: (leftRatio * 1000).round().clamp(1, 999),
                child: AnimatedContainer(
                  duration: ComeaMotion.settle,
                  curve: ComeaMotion.curve,
                  decoration: BoxDecoration(
                    color: empty ? ComeaColors.surfaceHigh : leftColor,
                    borderRadius: const BorderRadius.horizontal(left: Radius.circular(3)),
                    boxShadow: empty ? null : ComeaColors.glow(leftColor, blur: 8, alpha: 0.3),
                  ),
                ),
              ),
              Container(width: 3, color: ComeaColors.bg),
              Expanded(
                flex: ((1 - leftRatio) * 1000).round().clamp(1, 999),
                child: AnimatedContainer(
                  duration: ComeaMotion.settle,
                  curve: ComeaMotion.curve,
                  decoration: BoxDecoration(
                    color: empty ? ComeaColors.surfaceHigh : rightColor,
                    borderRadius: const BorderRadius.horizontal(right: Radius.circular(3)),
                    boxShadow: empty ? null : ComeaColors.glow(rightColor, blur: 8, alpha: 0.3),
                  ),
                ),
              ),
            ],
          ),
        ),
        if (empty) ...[
          const SizedBox(height: 4),
          Text('아직 개표 전입니다', style: ComeaType.sans(size: 11, color: ComeaColors.textFaint)),
        ],
      ],
    );
  }
}
