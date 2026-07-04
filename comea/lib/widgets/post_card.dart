import 'package:flutter/material.dart';

import '../design/design.dart';
import '../models/models.dart';

/// 피드의 글 카드 — 신문 1면의 기사 단.
/// 첫 문장은 헤드라인(명조), 나머지는 본문 미리보기로 조판한다.
class PostCard extends StatelessWidget {
  const PostCard({super.key, required this.post, required this.onTap});

  final Post post;
  final VoidCallback onTap;

  (String, String) _split(String content) {
    final trimmed = content.trim();
    final firstBreak = trimmed.indexOf(RegExp(r'[.!?…\n]'));
    if (firstBreak == -1 || firstBreak >= trimmed.length - 1) {
      return (trimmed, '');
    }
    return (
      trimmed.substring(0, firstBreak + 1).trim(),
      trimmed.substring(firstBreak + 1).trim(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final (headline, rest) = _split(post.content);
    final verdict = Verdict.parse(post.verdict);

    return Material(
      color: ComeaColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.card),
        side: const BorderSide(color: ComeaColors.line),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(ComeaRadii.card),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 13, 16, 13),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  StatusTag(post.status),
                  const Spacer(),
                  if (post.authorName != null)
                    Text(post.authorName!,
                        style: ComeaType.mono(size: 10.5, color: ComeaColors.textFaint)),
                ],
              ),
              const SizedBox(height: 9),
              Text(
                headline,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: ComeaType.sans(size: 16.5, weight: FontWeight.w800, height: 1.42, spacing: -0.2),
              ),
              if (rest.isNotEmpty) ...[
                const SizedBox(height: 5),
                Text(rest, maxLines: 2, overflow: TextOverflow.ellipsis, style: text.bodySmall),
              ],
              const SizedBox(height: 11),
              Row(
                children: [
                  if (post.score != null) ...[
                    Text('화제성 ', style: ComeaType.sans(size: 11, weight: FontWeight.w600, color: ComeaColors.textFaint)),
                    Text('${post.score}',
                        style: ComeaType.mono(size: 12, weight: FontWeight.w600, color: ComeaColors.text)),
                    _dot(),
                  ],
                  Text('▲', style: TextStyle(fontSize: 9, color: ComeaColors.textSoft)),
                  const SizedBox(width: 3),
                  Text('${post.likes}', style: ComeaType.mono(size: 12, color: ComeaColors.textSoft)),
                  const SizedBox(width: 8),
                  Text('▽', style: TextStyle(fontSize: 9, color: ComeaColors.textFaint)),
                  const SizedBox(width: 3),
                  Text('${post.dislikes}', style: ComeaType.mono(size: 12, color: ComeaColors.textFaint)),
                  _dot(),
                  Text('논평 ', style: ComeaType.sans(size: 11, weight: FontWeight.w600, color: ComeaColors.textFaint)),
                  Text('${post.commentCount}',
                      style: ComeaType.mono(size: 12, weight: FontWeight.w600, color: ComeaColors.text)),
                  const Spacer(),
                  if (verdict != null)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('◈ ', style: TextStyle(fontSize: 9, color: verdict.color)),
                        Text(verdict.label,
                            style: ComeaType.sans(
                                size: 11.5, weight: FontWeight.w700, color: verdict.color)),
                      ],
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _dot() => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 7),
        child: Text('·', style: ComeaType.sans(size: 11, color: ComeaColors.textFaint)),
      );
}
