import 'package:flutter/material.dart';

import '../tokens.dart';

/// 진영 — Comea 세계관의 축.
/// 백엔드 comments.faction ("ally" | "challenger" | "moderator") 와 1:1.
enum Faction {
  ally,
  challenger,
  moderator;

  static Faction parse(String? raw) => switch (raw) {
        'challenger' => Faction.challenger,
        'moderator' => Faction.moderator,
        _ => Faction.ally,
      };
}

extension FactionX on Faction {
  String get label => switch (this) {
        Faction.ally => '호위대',
        Faction.challenger => '도전자',
        Faction.moderator => '중재자',
      };

  /// 전광판 부호 — 아이콘 대신 스크린의 기호를 쓴다.
  String get glyph => switch (this) {
        Faction.ally => '●',
        Faction.challenger => '◆',
        Faction.moderator => '◈',
      };

  Color get color => switch (this) {
        Faction.ally => ComeaColors.ally,
        Faction.challenger => ComeaColors.challenger,
        Faction.moderator => ComeaColors.moderator,
      };

  /// 다크 패널 위에서는 진영색 자체가 충분히 밝다.
  Color get deepColor => color;

  /// 배지·하이라이트용 반투명 워시
  Color get wash => ComeaColors.wash(color);
}

/// 중재자 판정 — 백엔드 posts.verdict ("ally" | "challenger" | "tie").
enum Verdict {
  ally,
  challenger,
  tie;

  static Verdict? parse(String? raw) => switch (raw) {
        'ally' => Verdict.ally,
        'challenger' => Verdict.challenger,
        'tie' => Verdict.tie,
        _ => null,
      };
}

extension VerdictX on Verdict {
  String get label => switch (this) {
        Verdict.ally => '호위대 우세',
        Verdict.challenger => '도전자 우세',
        Verdict.tie => '팽팽',
      };

  Color get color => switch (this) {
        Verdict.ally => ComeaColors.ally,
        Verdict.challenger => ComeaColors.challenger,
        Verdict.tie => ComeaColors.moderator,
      };
}
