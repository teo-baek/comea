"""채점관 (스펙 §6, PRD 3.2) — 글을 4축 루브릭으로 평가해 0~100 점수를 산출.

- temperature 0 + few-shot 예시 3개 고정 (일관성 확보).
- 모델은 각 축 1~5 정수 + core_claim 만 JSON 으로 출력. **score 는 서버가 계산**:
  round(가중합 * 20), 가중치 = 정서 0.35 / 논쟁 0.30 / 명확성 0.20 / 신규성 0.15.
- JSON 파싱 실패 → 1회 재시도 → 그래도 실패 시 폴백 GradeResult(60, 전축 3, content[:80]).
- 마크다운 코드펜스(```json ... ```)로 감싼 응답도 파싱한다.
"""

import json
import logging
import os
import re
from dataclasses import dataclass

from ai_client import get_ai_client

logger = logging.getLogger(__name__)

# 루브릭 축 순서/가중치 (PRD 3.2 표)
AXES: tuple[str, ...] = ("emotion", "controversy", "clarity", "novelty")
WEIGHTS: dict[str, float] = {
    "emotion": 0.35,      # 정서적 깊이 (고민의 무게)
    "controversy": 0.30,  # 논쟁 유발성 (찬반 갈림)
    "clarity": 0.20,      # 주제 명확성
    "novelty": 0.15,      # 신규성/비일상성
}

FALLBACK_SCORE = 60  # 파싱 완전 실패 시 폴백 점수

# few-shot 3개(저/중/고품질) 고정 — temperature 0 과 함께 채점 일관성을 확보한다
SYSTEM_PROMPT = """너는 커뮤니티에 올라온 글을 평가하는 엄격하고 일관된 채점관 AI다.
아래 4축 루브릭을 각각 1~5 정수로 채점하고, 글쓴이의 핵심 주장을 한국어 한 문장(core_claim)으로 추출하라.

[루브릭]
- emotion     : 정서적 깊이 (고민의 무게)
- controversy : 논쟁 유발성 (찬반이 갈리는가)
- clarity     : 주제 명확성 (무엇을 말하려는지 분명한가)
- novelty     : 신규성/비일상성 (흔한 잡담이 아닌가)

총점은 서버가 계산하므로 절대 출력하지 마라.
반드시 아래 형식의 JSON 객체 하나만 출력하라 (설명·인사·마크다운 금지):
{"emotion":1~5,"controversy":1~5,"clarity":1~5,"novelty":1~5,"core_claim":"한 문장"}

[예시 1 — 저품질 글]
글: "아 배고프다 점심 뭐 먹지"
정답: {"emotion":1,"controversy":1,"clarity":2,"novelty":1,"core_claim":"점심 메뉴가 고민된다"}

[예시 2 — 중품질 글]
글: "5년 다닌 회사를 그만두고 연봉 20% 더 주는 스타트업으로 이직할지 고민입니다. 안정성은 지금 회사가 낫지만 성장은 멈춘 느낌이에요."
정답: {"emotion":3,"controversy":3,"clarity":4,"novelty":2,"core_claim":"안정적인 현 직장과 성장 가능한 스타트업 사이에서 이직을 고민한다"}

[예시 3 — 고품질 글]
글: "치매 초기인 아버지를 요양원에 모시는 게 불효일까요? 형제들은 집에서 모시자는데 저는 전문 케어가 낫다고 봅니다. 매일 밤 죄책감에 잠이 안 옵니다."
정답: {"emotion":5,"controversy":5,"clarity":5,"novelty":4,"core_claim":"치매 아버지를 요양원에 모시는 선택이 옳은지 죄책감 속에 갈등한다"}"""

# ```json ... ``` / ``` ... ``` 코드펜스 내부만 추출
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass
class GradeResult:
    score: int        # 0~100 (서버 계산)
    breakdown: dict   # {"emotion":1~5, "controversy":1~5, "clarity":1~5, "novelty":1~5}
    core_claim: str   # 글쓴이의 핵심 주장 1문장 (진영 프롬프트에 사용)


def _compute_score(breakdown: dict) -> int:
    """가중합 × 20 을 반올림해 0~100 으로 클램프 (score 는 항상 서버 계산)."""
    weighted = sum(WEIGHTS[axis] * breakdown[axis] for axis in AXES)
    return max(0, min(100, round(weighted * 20)))


def _parse_grade(raw: str, content: str) -> tuple[dict, str] | None:
    """모델 응답에서 (breakdown, core_claim) 추출. 실패 시 None.

    - 코드펜스로 감싼 JSON, JSON 앞뒤에 잡담이 붙은 응답도 허용.
    - 축 값은 숫자면 1~5 정수로 클램프. core_claim 누락 시 content[:80] 대체.
    """
    if not raw:
        return None
    text = raw.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    breakdown: dict = {}
    for axis in AXES:
        value = data.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        breakdown[axis] = min(5, max(1, round(value)))

    claim = data.get("core_claim")
    if not isinstance(claim, str) or not claim.strip():
        claim = content[:80]
    return breakdown, claim.strip()


async def grade_post(content: str) -> GradeResult:
    """글 1개를 채점. 파싱 실패 시 1회 재시도, 그래도 실패면 폴백 결과 반환."""
    client = get_ai_client()
    model = os.getenv("COMEA_JUDGE_MODEL", "gpt-4o-mini")
    user_prompt = f"[채점 대상 글]\n{content}\n\n위 글을 루브릭에 따라 JSON 으로만 채점하라."

    for attempt in (1, 2):  # 최초 1회 + 실패 시 1회 재시도
        try:
            raw = await client.complete(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                model=model,
                temperature=0.0,  # 채점 일관성 — 반드시 0
                max_tokens=300,
            )
        except Exception:
            logger.warning("채점 호출 실패 (attempt=%d)", attempt, exc_info=True)
            continue
        parsed = _parse_grade(raw, content)
        if parsed is not None:
            breakdown, claim = parsed
            return GradeResult(score=_compute_score(breakdown), breakdown=breakdown, core_claim=claim)
        logger.warning("채점 JSON 파싱 실패 (attempt=%d): %.120s", attempt, raw)

    # 폴백: 중간 점수로 파이프라인은 계속 진행 (스펙 §6)
    return GradeResult(
        score=FALLBACK_SCORE,
        breakdown={axis: 3 for axis in AXES},
        core_claim=content[:80],
    )
