import 'package:flutter/material.dart';

/// Comea 디자인 토큰 — 컨셉 "미드나잇 아레나 (Midnight Arena)"
///
/// 개표방송 × e스포츠 대전 상황실. 깊은 다크 위에서
/// 두 진영의 일렉트릭 컬러(시안 vs 오렌지)가 맞붙고,
/// 판정의 순간에만 금색 자막이 켜진다. 토론은 경기, 투표는 개표다.
abstract final class ComeaColors {
  // ── 배경(상황실) ────────────────────────────────────────────
  static const bg = Color(0xFF0B0E14); // 스크린 밖 어둠
  static const surface = Color(0xFF141A26); // 패널
  static const surfaceHigh = Color(0xFF1C2434); // 눌린 면 · 인용 · 트랙

  // ── 텍스트 ─────────────────────────────────────────────────
  static const text = Color(0xFFE9EDF5); // 주 텍스트 (스크린 발광)
  static const textSoft = Color(0xFF9AA5B8);
  static const textFaint = Color(0xFF5D6880);
  static const line = Color(0xFF273040); // 패널 스트로크
  static const rule = text; // 섹션 굵은 룰 (방송 자막 바)

  // ── 진영 (일렉트릭) ─────────────────────────────────────────
  /// 호위대(아군) — 일렉트릭 시안. 글쓴이 코너의 색.
  static const ally = Color(0xFF22D3EE);

  /// 도전자(적군) — 핫 오렌지. 반대 코너의 색.
  static const challenger = Color(0xFFFF6B3D);

  /// 중재자 — 방송 금색 자막. 판정의 순간에만 켜진다.
  static const moderator = Color(0xFFF5C33B);

  // ── 상태 ───────────────────────────────────────────────────
  static const live = Color(0xFFFF4D5E); // LIVE 점멸
  static const error = Color(0xFFFF5C5C);

  /// 진영색 반투명 워시 (다크 패널 위 배지/하이라이트 용)
  static Color wash(Color c) => c.withValues(alpha: 0.13);

  /// 진영색 글로우 (네온 새어나옴)
  static List<BoxShadow> glow(Color c, {double blur = 10, double alpha = 0.35}) =>
      [BoxShadow(color: c.withValues(alpha: alpha), blurRadius: blur)];
}

abstract final class ComeaSpacing {
  static const double x1 = 4;
  static const double x2 = 8;
  static const double x3 = 12;
  static const double x4 = 16;
  static const double x5 = 20;
  static const double x6 = 24;
  static const double x8 = 32;
  static const double x12 = 48;

  /// 지면 좌우 여백
  static const page = EdgeInsets.symmetric(horizontal: 20);
}

abstract final class ComeaRadii {
  /// 전광판 패널 — 살짝만 깎는다.
  static const double card = 8;
  static const double field = 8;
  static const double pill = 999; // 투표 알약 · 스코어 칩만 예외
}

abstract final class ComeaMotion {
  static const quick = Duration(milliseconds: 140);
  static const settle = Duration(milliseconds: 260);
  /// 댓글 "스르륵" — 자막이 올라오듯.
  static const reveal = Duration(milliseconds: 560);
  static const curve = Curves.easeOutCubic;

  /// 연속 등장 시 항목 간 시차
  static const stagger = Duration(milliseconds: 110);
}
