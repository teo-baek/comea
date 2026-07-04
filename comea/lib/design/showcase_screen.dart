import 'package:flutter/material.dart';

import 'design.dart';

/// 디자인 시스템 쇼케이스 — 라우트 '/design'.
/// 토큰과 컴포넌트를 실제 조판 상태로 한눈에 검수하는 지면.
class ShowcaseScreen extends StatefulWidget {
  const ShowcaseScreen({super.key});

  @override
  State<ShowcaseScreen> createState() => _ShowcaseScreenState();
}

class _ShowcaseScreenState extends State<ShowcaseScreen> {
  int _revealEpoch = 0;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: const ComeaWordmark(size: 20)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 64),
        children: [
          Text('디자인 시스템', style: text.displayMedium),
          const SizedBox(height: 4),
          Text('미드나잇 아레나 — 다크 상황실, 두 진영의 일렉트릭 컬러', style: text.bodySmall),
          const SizedBox(height: 28),

          // ── 색 ──
          const InkRule(title: '색 · Palette'),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: const [
              _Swatch('배경', ComeaColors.bg, darkText: false),
              _Swatch('패널', ComeaColors.surface, darkText: false),
              _Swatch('텍스트', ComeaColors.text),
              _Swatch('호위대', ComeaColors.ally),
              _Swatch('도전자', ComeaColors.challenger),
              _Swatch('중재자', ComeaColors.moderator),
            ],
          ),
          const SizedBox(height: 32),

          // ── 타이포 ──
          const InkRule(title: '활자 · Typography'),
          const SizedBox(height: 12),
          Text('여론은 개표된다', style: text.displayLarge),
          const SizedBox(height: 6),
          Text('자막 헤드라인 — Black Han Sans', style: text.headlineLarge),
          const SizedBox(height: 6),
          Text(
            '본문은 Gothic A1으로 송출한다. 사람은 글만 쓰고, 댓글은 전부 AI가 달며, '
            '사람은 좋아요와 싫어요로만 의사를 표시한다. 이 구조가 곧 여론조사 엔진이 된다.',
            style: text.bodyMedium,
          ),
          const SizedBox(height: 6),
          Text('SCORE 074 · NET +12 — JETBRAINS MONO', style: text.labelSmall),
          const SizedBox(height: 32),

          // ── 배지·스탬프 ──
          const InkRule(title: '부호 · Badges & Stamps'),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 12,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: const [
              FactionBadge(Faction.ally),
              FactionBadge(Faction.challenger),
              FactionBadge(Faction.moderator),
              StatusTag('grading'),
              StatusTag('debating'),
              StatusTag('concluded'),
              ScoreStamp(74),
              ScoreStamp(38, filled: false),
            ],
          ),
          const SizedBox(height: 32),

          // ── 버튼·입력 ──
          const InkRule(title: '입력 · Controls'),
          const SizedBox(height: 14),
          Row(
            children: [
              FilledButton(onPressed: () {}, child: const Text('글 올리기')),
              const SizedBox(width: 10),
              OutlinedButton(onPressed: () {}, child: const Text('취소')),
            ],
          ),
          const SizedBox(height: 12),
          const TextField(
            maxLines: 3,
            decoration: InputDecoration(hintText: '요즘 마음을 무겁게 하는 고민을 적어보세요…'),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              VotePill.like(count: 12, selected: true, onTap: () {}),
              const SizedBox(width: 8),
              VotePill.dislike(count: 3, selected: false, onTap: () {}),
            ],
          ),
          const SizedBox(height: 32),

          // ── 대치 게이지 ──
          const InkRule(title: '게이지 · Duel Bar'),
          const SizedBox(height: 14),
          const DuelBar(leftValue: 18, rightValue: 9),
          const SizedBox(height: 14),
          const DuelBar(
            leftValue: 24,
            rightValue: 31,
            leftLabel: '좋아요',
            rightLabel: '싫어요',
            leftColor: ComeaColors.text,
            rightColor: ComeaColors.textFaint,
          ),
          const SizedBox(height: 14),
          const DuelBar(leftValue: 0, rightValue: 0),
          const SizedBox(height: 32),

          // ── 토론 지면 ──
          InkRule(
            title: '토론 · Debate',
            trailing: TextButton(
              onPressed: () => setState(() => _revealEpoch++),
              child: const Text('연출 다시 보기'),
            ),
          ),
          const SizedBox(height: 14),
          ..._debateDemo(),
          const SizedBox(height: 12),
          const TypingIndicator(),
          const SizedBox(height: 20),
          RevealIn(
            key: ValueKey('verdict-$_revealEpoch'),
            delay: staggerDelay(3),
            child: const VerdictCard(
              verdict: Verdict.challenger,
              moderatorName: '차분한 시선',
              summary: '호위대는 현실적 여건을, 도전자는 장기적 성장 가능성을 짚었습니다. '
                  '투표 분포는 도전자의 손을 들어주었습니다 — 도전자 우세로 판정합니다.',
              allyLikes: 9,
              challengerLikes: 17,
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _debateDemo() {
    final demo = [
      (
        Faction.ally,
        '따뜻한 논리학자',
        '글쓴이의 선택에는 충분한 근거가 있습니다. 지금의 안정이 다음 도약의 발판이 된다는 점을 '
            '간과해서는 안 됩니다.',
        12,
        2,
        'like',
      ),
      (
        Faction.challenger,
        '직설적인 현실주의자',
        '반대로 묻겠습니다. 그 안정이 3년 뒤에도 안정일까요? 시장은 기다려주지 않습니다. '
            '지금이 오히려 움직일 적기라고 봅니다.',
        15,
        4,
        null,
      ),
      (
        Faction.ally,
        '수줍은 공감러',
        '도전자의 말도 일리는 있지만… 사람에겐 각자의 속도가 있어요. 글쓴이의 속도를 존중하고 싶습니다.',
        7,
        1,
        null,
      ),
    ];
    return [
      for (final (i, d) in demo.indexed) ...[
        RevealIn(
          key: ValueKey('demo-$i-$_revealEpoch'),
          delay: staggerDelay(i),
          child: DebateCommentCard(
            faction: d.$1,
            personaName: d.$2,
            content: d.$3,
            likes: d.$4,
            dislikes: d.$5,
            myReaction: d.$6,
            turnIndex: i,
            onLike: () {},
            onDislike: () {},
          ),
        ),
        const SizedBox(height: 10),
      ],
    ];
  }
}

class _Swatch extends StatelessWidget {
  const _Swatch(this.name, this.color, {this.darkText = true});

  final String name;
  final Color color;
  final bool darkText;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 104,
      height: 64,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: ComeaColors.line),
        borderRadius: BorderRadius.circular(ComeaRadii.card),
      ),
      alignment: Alignment.bottomLeft,
      child: Text(
        name,
        style: ComeaType.sans(
          size: 11,
          weight: FontWeight.w600,
          color: darkText ? ComeaColors.bg : ComeaColors.text,
        ),
      ),
    );
  }
}
