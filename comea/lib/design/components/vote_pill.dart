import 'package:flutter/material.dart';

import '../tokens.dart';
import '../typography.dart';

/// 투표 알약 — 사람이 이 경기장에서 할 수 있는 유일한 발화.
/// ▲(좋아요) / ▽(싫어요) 부호와 카운트. 선택되면 발광 반전된다.
class VotePill extends StatelessWidget {
  const VotePill.like({
    super.key,
    required this.count,
    required this.selected,
    this.onTap,
    this.enabled = true,
  }) : _up = true;

  const VotePill.dislike({
    super.key,
    required this.count,
    required this.selected,
    this.onTap,
    this.enabled = true,
  }) : _up = false;

  final bool _up;
  final int count;
  final bool selected;
  final VoidCallback? onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final glyph = _up ? (selected ? '▲' : '△') : (selected ? '▼' : '▽');
    final fg = selected ? ComeaColors.bg : ComeaColors.textSoft;

    return Material(
      color: selected ? ComeaColors.text : ComeaColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.pill),
        side: BorderSide(color: selected ? ComeaColors.text : ComeaColors.line, width: 1),
      ),
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(ComeaRadii.pill),
        child: AnimatedContainer(
          duration: ComeaMotion.quick,
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(glyph, style: TextStyle(fontSize: 10, color: fg, height: 1.2)),
              const SizedBox(width: 6),
              Text('$count',
                  style: ComeaType.mono(size: 12.5, weight: FontWeight.w600, color: fg, spacing: 0)),
            ],
          ),
        ),
      ),
    );
  }
}
