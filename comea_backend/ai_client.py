"""AI 클라이언트 (스펙 §5) — AsyncOpenAI 래퍼 + 결정적 Fake 스텁.

- `COMEA_FAKE_AI=1` 또는 `OPENAI_API_KEY` 부재 시 FakeAIClient 사용 (네트워크 호출 0).
- env 는 **호출 시점**에 읽으므로 테스트에서 monkeypatch 로 모드 전환이 가능하다.
- FakeAIClient 는 완전 결정적: 같은 (system, user) 입력이면 항상 같은 출력.
  - 요청 텍스트에 'JSON' 이 포함되면 유효한 채점 JSON 문자열 반환.
  - 그 외에는 페르소나/진영 힌트를 섞은 짧은 한국어 댓글 반환 (hash 기반 변주 —
    페르소나마다 system 이 다르므로 서로 다른 문장을 갖는다).
"""

import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

# COMEA_FAKE_AI truthy 값 허용 집합
_TRUTHY = {"1", "true", "yes", "on"}


def _fake_env_on() -> bool:
    """COMEA_FAKE_AI env 가 켜져 있는지 (호출 시점 판정)."""
    return os.getenv("COMEA_FAKE_AI", "").strip().lower() in _TRUTHY


def _has_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def is_fake_mode() -> bool:
    """fake 모드 여부 — COMEA_FAKE_AI=1 이거나 API 키가 없으면 True.

    헬스체크의 ai_mode("real"|"fake") 판정에 사용된다. env 는 매 호출마다 읽는다.
    """
    return _fake_env_on() or not _has_api_key()


class AIClient:
    """AsyncOpenAI 래퍼 — 실제 OpenAI Chat Completions 호출."""

    def __init__(self) -> None:
        # 지연 임포트: fake 모드 테스트에서 openai 초기화 비용/의존을 피한다
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI()

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.8,
        max_tokens: int | None = 400,
    ) -> str:
        kwargs: dict = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            **kwargs,
        )
        return (response.choices[0].message.content or "").strip()


# ── FakeAIClient 문장 재료 (진영별 톤) ──────────────────────────────────────
# opener × body × closer 조합으로 변주 — 페르소나(system)마다 다른 문장이 나온다.

_ALLY_OPENERS = ["정말 공감합니다.", "글쓴이 말이 맞다고 봅니다.", "저도 비슷한 경험이 있어요.", "이 글, 충분히 이해가 갑니다.", "동의하는 입장입니다."]
_ALLY_BODIES = [
    "핵심 논점이 현실적으로 타당하고 근거도 자연스럽습니다.",
    "이런 고민을 꺼내놓는 것 자체가 쉽지 않은데 잘 정리하셨네요.",
    "반대 의견도 있겠지만 글쓴이의 판단 기준이 더 설득력 있어 보여요.",
    "상황을 보면 글쓴이의 선택이 합리적이라고 생각합니다.",
    "논리 전개가 깔끔해서 덧붙일 말이 많지 않네요.",
]
_ALLY_CLOSERS = ["응원합니다.", "힘내세요.", "저는 글쓴이 편에 서겠습니다.", "좋은 결과 있길 바랍니다."]

_CHALLENGER_OPENERS = ["조심스럽지만 저는 생각이 다릅니다.", "반대 관점도 한번 보시죠.", "음, 이건 짚고 넘어가야겠네요.", "정중히 반박해 보겠습니다.", "다른 각도에서 보면 어떨까요."]
_CHALLENGER_BODIES = [
    "전제 자체가 한쪽으로 기울어 있어서 결론도 흔들릴 수 있어요.",
    "감정적으로는 이해되지만 현실적인 비용을 과소평가한 듯합니다.",
    "반대 사례도 충분히 많다는 점을 고려하면 단정하긴 이릅니다.",
    "그 논리라면 반대 결론도 똑같이 성립한다는 게 문제예요.",
    "대안 없이 결론만 내리기엔 근거가 부족해 보입니다.",
]
_CHALLENGER_CLOSERS = ["다른 선택지도 검토해 보세요.", "한 발 물러서서 다시 보시길 권합니다.", "저라면 다르게 하겠습니다.", "냉정하게 다시 따져봅시다."]

_MODERATOR_OPENERS = ["토론을 정리하겠습니다.", "양측 의견 잘 들었습니다.", "이쯤에서 중간 정리를 하죠.", "판정을 위해 흐름을 요약합니다."]
_MODERATOR_BODIES = [
    "호위대는 공감과 논리 보강으로, 도전자는 반박과 대안으로 맞섰습니다.",
    "양 진영 모두 나름의 근거를 제시하며 팽팽하게 맞붙었습니다.",
    "핵심 쟁점을 두고 양측의 시각 차이가 뚜렷하게 드러났습니다.",
    "감정과 논리가 균형 있게 오간 토론이었습니다.",
]
_MODERATOR_CLOSERS = ["판정은 여러분의 반응이 말해줍니다.", "이상으로 이번 라운드를 마칩니다.", "결과는 좋아요 분포로 확인해 주세요.", "수고하셨습니다."]

_NEUTRAL_OPENERS = ["흥미로운 글이네요.", "한마디 보태자면,", "지나가다 남깁니다.", "이 주제 재밌네요.", "생각해볼 만한 글입니다."]
_NEUTRAL_BODIES = [
    "양쪽 다 일리가 있어서 쉽게 결론 내리기 어렵네요.",
    "결국 본인 상황에 맞는 답을 찾는 게 중요할 것 같아요.",
    "댓글들 흐름을 보니 논점이 점점 선명해지고 있네요.",
    "이런 주제는 시간이 지나야 답이 보이는 법이죠.",
    "저마다 기준이 달라서 더 흥미로운 토론입니다.",
]
_NEUTRAL_CLOSERS = ["다들 좋은 하루 보내세요.", "계속 지켜보겠습니다.", "좋은 토론 감사합니다.", "저는 여기까지요."]

_FACTION_POOLS: dict[str, tuple[list[str], list[str], list[str]]] = {
    "ally": (_ALLY_OPENERS, _ALLY_BODIES, _ALLY_CLOSERS),
    "challenger": (_CHALLENGER_OPENERS, _CHALLENGER_BODIES, _CHALLENGER_CLOSERS),
    "moderator": (_MODERATOR_OPENERS, _MODERATOR_BODIES, _MODERATOR_CLOSERS),
    "neutral": (_NEUTRAL_OPENERS, _NEUTRAL_BODIES, _NEUTRAL_CLOSERS),
}


def _detect_faction(system: str) -> str:
    """system 프롬프트에서 진영 힌트를 추정 (best-effort 휴리스틱).

    ally/challenger 지시문에는 상대 진영 단어도 등장하므로("이전 도전자 논점을 재반박" 등)
    '먼저 등장하는' 진영 키워드를 자기 진영으로 본다. 중재자는 별도 우선 판정.
    """
    lowered = system.lower()
    if "중재" in system or "moderator" in lowered:
        return "moderator"
    positions: dict[str, int] = {}
    for keyword, tag in (
        ("도전", "challenger"),
        ("반박하", "challenger"),
        ("challenger", "challenger"),
        ("호위", "ally"),
        ("공감하", "ally"),
        ("ally", "ally"),
    ):
        idx = lowered.find(keyword) if keyword.isascii() else system.find(keyword)
        if idx != -1 and (tag not in positions or idx < positions[tag]):
            positions[tag] = idx
    if not positions:
        return "neutral"
    return min(positions, key=lambda tag: positions[tag])


def _extract_claim(user: str) -> str:
    """user 프롬프트에서 원글로 추정되는 라인을 뽑아 core_claim 스텁으로 사용.

    대괄호 라벨 라인([채점 대상 글] 등)과 JSON 지시문 라인은 제외하고 가장 긴 라인을 고른다.
    """
    lines = [line.strip() for line in user.splitlines() if line.strip()]
    candidates = [
        line for line in lines
        if not line.startswith("[") and "json" not in line.lower()
    ] or lines
    if not candidates:
        return "핵심 주장"
    return max(candidates, key=len)[:60]


class FakeAIClient:
    """결정적 스텁 — 네트워크 0. 같은 입력이면 항상 같은 출력.

    - 요청(system+user)에 'JSON' 포함 → 유효한 채점 JSON 문자열.
    - 그 외 → 진영 힌트 톤의 짧은 한국어 댓글 (sha256 해시 기반 변주).
    """

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.8,
        max_tokens: int | None = 400,
    ) -> str:
        # hash() 는 프로세스마다 시드가 달라지므로 sha256 으로 프로세스 간 결정성 확보
        digest = hashlib.sha256(f"{system}\x00{user}".encode("utf-8")).digest()

        if "JSON" in f"{system}\n{user}".upper():
            payload = {
                "emotion": 1 + digest[0] % 5,
                "controversy": 1 + digest[1] % 5,
                "clarity": 1 + digest[2] % 5,
                "novelty": 1 + digest[3] % 5,
                "core_claim": _extract_claim(user),
            }
            return json.dumps(payload, ensure_ascii=False)

        openers, bodies, closers = _FACTION_POOLS[_detect_faction(system)]
        opener = openers[digest[4] % len(openers)]
        body = bodies[digest[5] % len(bodies)]
        closer = closers[digest[6] % len(closers)]
        return f"{opener} {body} {closer}"


# ── 싱글턴 관리 ─────────────────────────────────────────────────────────────

_instance: AIClient | FakeAIClient | None = None


def get_ai_client() -> AIClient | FakeAIClient:
    """싱글턴 반환. env 를 호출 시점에 읽어 모드가 바뀌면 인스턴스를 갈아탄다."""
    global _instance
    want_fake = is_fake_mode()
    if _instance is not None and isinstance(_instance, FakeAIClient) == want_fake:
        return _instance
    if want_fake:
        if not _fake_env_on() and not _has_api_key():
            # 키 부재로 인한 자동 전환은 명시 설정과 달리 운영 실수일 수 있어 경고
            logger.warning("OPENAI_API_KEY 가 없어 FakeAIClient 로 자동 전환합니다.")
        _instance = FakeAIClient()
    else:
        _instance = AIClient()
    return _instance


def reset_ai_client() -> None:
    """테스트용 — 캐시된 싱글턴을 폐기해 다음 호출에서 재생성하게 한다."""
    global _instance
    _instance = None
