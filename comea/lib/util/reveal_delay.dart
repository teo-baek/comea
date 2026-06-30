import 'dart:math';

const int kMaxRevealGapMs = 30000; // 댓글 사이 간격 상한 (30초)

/// 댓글 등장 간격(gap)을 long-tail 분포로 생성한다.
/// 거듭제곱(세제곱) 스큐: 대부분 짧고(중앙값 ≈ 0.5³×30 ≈ 3.75초) 드물게 최대 30초.
/// rng 주입으로 테스트 결정성 확보.
Duration randomRevealGap(Random rng) {
  final r = rng.nextDouble(); // [0,1)
  final skewed = r * r * r; // long-tail: 작은 값으로 치우침
  return Duration(milliseconds: (skewed * kMaxRevealGapMs).round());
}
