import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:ulssu/util/reveal_delay.dart';

void main() {
  test('gap은 0~30초 범위 안에 있다', () {
    final rng = Random(1);
    for (var i = 0; i < 200; i++) {
      final gap = randomRevealGap(rng);
      expect(gap.inMilliseconds, greaterThanOrEqualTo(0));
      expect(gap.inMilliseconds, lessThanOrEqualTo(30000));
    }
  });

  test('같은 시드 → 같은 gap (결정적)', () {
    expect(randomRevealGap(Random(7)).inMilliseconds, randomRevealGap(Random(7)).inMilliseconds);
    final a = randomRevealGap(Random(42)).inMilliseconds;
    final b = randomRevealGap(Random(42)).inMilliseconds;
    expect(a, b);
  });

  test('long-tail: 표본 다수가 중앙값(7.5초)보다 짧다 (짧은 쪽으로 치우침)', () {
    final rng = Random(123);
    final samples = List.generate(500, (_) => randomRevealGap(rng).inMilliseconds);
    final shortCount = samples.where((ms) => ms < 7500).length;
    // 거듭제곱 스큐라 절반보다 훨씬 많은 표본이 7.5초 미만이어야 함
    expect(shortCount, greaterThan(300));
  });
}
