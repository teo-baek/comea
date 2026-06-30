"""댓글 분량(길이) 변주 스타일.

긴 글/짧은 글이 섞여 실제 게시판처럼 보이도록(FR-13), 댓글마다 길이 지침을 랜덤 선택한다.
선택 함수는 random.Random 주입을 허용해 테스트 결정성을 확보한다.
"""

import random

LENGTH_STYLES: list[str] = [
    "한 줄 이내로 짧고 강렬하게",
    "2~3줄 정도로 적당히",
    "5~6줄로 길고 자세하게 풀어서",
]


def pick_length_style(rng: random.Random | None = None) -> str:
    """분량 후보군에서 하나를 랜덤 선택. rng 주입 시 결정적."""
    chooser = rng if rng is not None else random
    return chooser.choice(LENGTH_STYLES)
