import 'package:flutter/material.dart';

import '../tokens.dart';

/// "스르륵" 등장 — 잉크가 종이에 스며들 듯 아래에서 떠오르며 나타난다.
/// AI 댓글의 순차 공개, 피드 카드의 시차 등장에 사용.
///
/// 딜레이는 Timer 가 아니라 AnimationController 의 Interval 로 처리한다
/// (위젯 dispose 시 자동 정리 — 위젯 테스트에서 잔류 타이머가 남지 않는다).
class RevealIn extends StatefulWidget {
  const RevealIn({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.offset = 14,
    this.duration = ComeaMotion.reveal,
  });

  final Widget child;
  final Duration delay;
  final double offset;
  final Duration duration;

  @override
  State<RevealIn> createState() => _RevealInState();
}

class _RevealInState extends State<RevealIn> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _progress;

  @override
  void initState() {
    super.initState();
    final total = widget.delay + widget.duration;
    _controller = AnimationController(vsync: this, duration: total);
    final start = total.inMicroseconds == 0
        ? 0.0
        : widget.delay.inMicroseconds / total.inMicroseconds;
    _progress = CurvedAnimation(
      parent: _controller,
      curve: Interval(start, 1.0, curve: ComeaMotion.curve),
    );
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _progress,
      builder: (context, child) {
        return Opacity(
          opacity: _progress.value,
          child: Transform.translate(
            offset: Offset(0, widget.offset * (1 - _progress.value)),
            child: child,
          ),
        );
      },
      child: widget.child,
    );
  }
}

/// 리스트 항목에 시차를 주는 헬퍼.
Duration staggerDelay(int index, {Duration? base}) =>
    (base ?? ComeaMotion.stagger) * index;
