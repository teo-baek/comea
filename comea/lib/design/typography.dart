import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'tokens.dart';

/// Comea 타이포그래피 — 개표방송의 위계.
///
/// 자막/판정/스코어 = Black Han Sans (콘덴스드 헤비 — 방송 자막),
/// 본문·UI        = Gothic A1,
/// 숫자·태그      = JetBrains Mono (라틴/숫자 전용 — 한글 라벨엔 쓰지 않는다).
abstract final class ComeaType {
  /// 방송 자막체 — 판정·워드마크·큰 숫자 헤드라인 전용.
  static TextStyle display({
    double size = 22,
    Color color = ComeaColors.text,
    double height = 1.25,
    double spacing = 0.2,
  }) =>
      GoogleFonts.blackHanSans(
        fontSize: size,
        fontWeight: FontWeight.w400, // BHS 는 단일 웨이트(외형은 블랙)
        color: color,
        height: height,
        letterSpacing: spacing,
      );

  static TextStyle sans({
    double size = 14,
    FontWeight weight = FontWeight.w400,
    Color color = ComeaColors.text,
    double height = 1.6,
    double spacing = 0,
  }) =>
      GoogleFonts.gothicA1(
        fontSize: size,
        fontWeight: weight,
        color: color,
        height: height,
        letterSpacing: spacing,
      );

  /// 점수 · 카운트 · 시각 등 숫자/라틴 전용
  static TextStyle mono({
    double size = 12,
    FontWeight weight = FontWeight.w500,
    Color color = ComeaColors.textSoft,
    double spacing = 0.8,
  }) =>
      GoogleFonts.jetBrainsMono(
        fontSize: size,
        fontWeight: weight,
        color: color,
        letterSpacing: spacing,
      );

  /// 섹션 오버라인 — "LIVE · 오늘의 대전" 같은 잔글씨
  static TextStyle overline({Color color = ComeaColors.textFaint}) =>
      sans(size: 11.5, weight: FontWeight.w800, color: color, spacing: 2.2, height: 1.2);

  static TextTheme textTheme() {
    return TextTheme(
      displayLarge: display(size: 34, height: 1.2),
      displayMedium: display(size: 27, height: 1.24),
      headlineLarge: display(size: 23, height: 1.3),
      headlineMedium: sans(size: 21, weight: FontWeight.w800, height: 1.36, spacing: -0.2),
      headlineSmall: sans(size: 18.5, weight: FontWeight.w800, height: 1.4, spacing: -0.2),
      titleLarge: sans(size: 17, weight: FontWeight.w800, height: 1.4),
      titleMedium: sans(size: 15, weight: FontWeight.w700, height: 1.45),
      titleSmall: sans(size: 13, weight: FontWeight.w600, height: 1.4, color: ComeaColors.textSoft),
      bodyLarge: sans(size: 15.5, height: 1.8, color: ComeaColors.text),
      bodyMedium: sans(size: 14, height: 1.72, color: ComeaColors.text),
      bodySmall: sans(size: 12.5, height: 1.55, color: ComeaColors.textSoft),
      labelLarge: sans(size: 14, weight: FontWeight.w800, spacing: 0.4, height: 1.2),
      labelMedium: sans(size: 12, weight: FontWeight.w700, spacing: 0.6, height: 1.2),
      labelSmall: mono(size: 11, spacing: 1.2),
    );
  }
}
