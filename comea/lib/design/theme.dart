import 'package:flutter/material.dart';

import 'tokens.dart';
import 'typography.dart';

/// Comea 전역 테마 — "미드나잇 아레나".
/// 다크 상황실, 발광 텍스트, 패널 스트로크. 그림자 대신 글로우.
ThemeData buildComeaTheme() {
  const scheme = ColorScheme(
    brightness: Brightness.dark,
    primary: ComeaColors.text,
    onPrimary: ComeaColors.bg,
    secondary: ComeaColors.ally,
    onSecondary: ComeaColors.bg,
    tertiary: ComeaColors.challenger,
    onTertiary: ComeaColors.bg,
    error: ComeaColors.error,
    onError: ComeaColors.bg,
    surface: ComeaColors.bg,
    onSurface: ComeaColors.text,
    surfaceContainerHighest: ComeaColors.surfaceHigh,
    onSurfaceVariant: ComeaColors.textSoft,
    outline: ComeaColors.line,
    outlineVariant: ComeaColors.line,
    shadow: Colors.transparent,
    scrim: Colors.black87,
    inverseSurface: ComeaColors.text,
    onInverseSurface: ComeaColors.bg,
    inversePrimary: ComeaColors.bg,
  );

  final text = ComeaType.textTheme();

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: ComeaColors.bg,
    textTheme: text,
    splashFactory: InkSparkle.splashFactory,

    appBarTheme: AppBarTheme(
      backgroundColor: ComeaColors.bg,
      foregroundColor: ComeaColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      titleTextStyle: ComeaType.display(size: 19, spacing: 0.6),
      shape: const Border(bottom: BorderSide(color: ComeaColors.line, width: 1)),
    ),

    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: ComeaColors.text,
        foregroundColor: ComeaColors.bg,
        disabledBackgroundColor: ComeaColors.surfaceHigh,
        disabledForegroundColor: ComeaColors.textFaint,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(ComeaRadii.card)),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 15),
        textStyle: text.labelLarge,
      ),
    ),

    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: ComeaColors.text,
        side: const BorderSide(color: ComeaColors.line, width: 1.2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(ComeaRadii.card)),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        textStyle: text.labelLarge,
      ),
    ),

    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: ComeaColors.textSoft,
        textStyle: text.labelMedium,
      ),
    ),

    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: ComeaColors.surface,
      hintStyle: ComeaType.sans(size: 14, color: ComeaColors.textFaint, height: 1.6),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.field),
        borderSide: const BorderSide(color: ComeaColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.field),
        borderSide: const BorderSide(color: ComeaColors.ally, width: 1.6),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.field),
        borderSide: const BorderSide(color: ComeaColors.error),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.field),
        borderSide: const BorderSide(color: ComeaColors.error, width: 1.6),
      ),
    ),

    dividerTheme: const DividerThemeData(color: ComeaColors.line, thickness: 1, space: 1),

    snackBarTheme: SnackBarThemeData(
      backgroundColor: ComeaColors.surfaceHigh,
      contentTextStyle: ComeaType.sans(size: 13.5, color: ComeaColors.text, height: 1.4),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ComeaRadii.card),
        side: const BorderSide(color: ComeaColors.line),
      ),
    ),

    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: ComeaColors.ally,
      linearTrackColor: ComeaColors.surfaceHigh,
    ),
  );
}
