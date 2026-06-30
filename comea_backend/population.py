"""전체 유저수(current_population) 인메모리 상태 훅.

이 슬라이스는 값을 읽고 쓰는 인터페이스만 제공한다. 실제 일일 새벽 배치 집계는
별도 슬라이스(PRD §3.4)가 set_current_population 으로 주입한다.
"""

_current_population = 0


def get_current_population() -> int:
    return _current_population


def set_current_population(value: int) -> None:
    if value < 0:
        raise ValueError("population must be non-negative")
    global _current_population
    _current_population = value
