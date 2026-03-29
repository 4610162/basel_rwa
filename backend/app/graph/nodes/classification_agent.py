"""
Classification Agent Node

역할:
- 사용자 질문에서 intent, exposure_type, 계산 파라미터 추출
- 필요 필드 / 누락 필드 식별
- 규정 조문 경로 추정

LLM (Gemini) 을 사용하여 구조화된 JSON으로 분류 결과를 반환.
"""
from __future__ import annotations

import json
import re

from app.core.config import get_settings
from app.graph.state import GraphState
from app.graph.utils import format_conversation_history

# ── 각 exposure_type별 필수 계산 파라미터 정의 ─────────────────────────────────
REQUIRED_FIELDS_MAP: dict[str, list[str]] = {
    "sovereign": ["exposure_category", "entity_type", "exposure"],
    "bank": ["exposure_category", "entity_type", "exposure"],
    "corporate": ["exposure_category", "entity_type", "exposure"],
    "real_estate": ["exposure_category", "entity_type", "exposure", "re_exposure_type", "ltv_ratio"],
    "securitization": [
        "exposure_category", "entity_type", "exposure",
        "attachment_point", "detachment_point", "k_sa", "w",
    ],
    "equity": ["exposure_category", "entity_type", "exposure"],
    "ciu": ["exposure_category", "entity_type", "exposure", "ciu_approach"],
    "other": ["exposure_category", "entity_type", "exposure"],
    "unknown": [],
}

CLASSIFICATION_PROMPT = """\
당신은 Basel III 은행업감독업무시행세칙 전문가 AI입니다.
사용자 질문을 분석하여 아래 JSON 형식으로만 응답하세요. JSON 외 다른 텍스트는 절대 출력하지 마세요.

## 분류 기준

**intent (의도):**
- regulation_only: 규정 설명/조회/해석만 필요. 수치 계산 파라미터가 없거나 계산을 요청하지 않는 경우
- calculation_only: RWA 계산만 요청. 규정 설명 불필요. 계산에 필요한 파라미터가 충분한 경우
- regulation_plus_calculation: 규정 근거 설명 + RWA 계산 모두 필요. 계산 파라미터가 충분한 경우
- clarification_needed: RWA 계산을 원하지만 필수 파라미터(익스포져 금액, 등급 등)가 부족한 경우

**exposure_type (익스포져 유형):**
- sovereign: 중앙정부, 국채, 공공기관(PSE), 다자개발은행(MDB)
- bank: 은행, 금융기관, 증권사
- corporate: 일반기업, 중소기업(SME), 특수목적금융(PF/SF/CF/IPRE/HVCRE)
- real_estate: 주거용/상업용 부동산 담보대출, ADC
- securitization: 유동화 익스포져 (SEC-SA)
- equity: 주식, 출자금, 펀드 출자
- ciu: 집합투자기구(펀드, CIU)
- other: 위에 해당하지 않는 기타
- unknown: 판단 불가

**exposure_category (RwaCalculationRequest.exposure_category 값):**
gov | bank | corp | realestate | securitization | equity | ciu

**entity_type 예시:**
- gov: central_gov | zero_risk_entity | mdb_zero | mdb_general | pse_local_gov_krw | pse_local_gov_fx | pse_type1 | pse_type2
- bank: general | covered_bond | short_term | trade_lc | cet1_based | leverage_based
- corp: general | general_short | sl_pf | sl_of | sl_cf | ipre | hvcre
- realestate: cre_non_ipre | cre_ipre | adc | pf_consortium
- equity: listed | unlisted | fund | grandfathered | speculative
- ciu: lta | mba | fba

**신용등급 표기 기준:**
AAA, AA+, AA, AA-, A+, A, A-, BBB+, BBB, BBB-, BB+, BB, BB-, B+, B, B-, CCC 이상, CCC 미만

**금액 변환:**
- "100억" → 10000000000
- "50억" → 5000000000
- "1조" → 1000000000000
- "1억" → 100000000
- "1000만" → 10000000

## 응답 JSON 형식
{{
  "intent": "...",
  "exposure_type": "...",
  "entities": {{
    "company_name": null,
    "rating": null,
    "amount_raw": null,
    "amount_parsed": null
  }},
  "required_fields": [...],
  "missing_fields": [...],
  "regulation_path": [...],
  "extracted_params": {{
    "exposure_category": "...",
    "entity_type": "...",
    "exposure": null,
    "external_credit_rating": null
  }},
  "english_query": "..."
}}

**english_query 작성 규칙:**
- 질문이 한국어인 경우: Basel III / 은행 규제 검색에 적합한 간결한 영어 질의로 번역
- 질문이 이미 영어인 경우: null
- PD, LGD, EAD, RWA, Basel III 등 금융 전문 용어는 원문 유지

## 사용자 질문
{question}

## 최근 대화 맥락 (참고용)
{history}
"""


async def classification_node(state: GraphState) -> dict:
    """
    LangGraph Node: 질문 분류 및 파라미터 추출.
    Gemini API를 호출하여 구조화된 분류 결과를 반환한다.
    """
    from app.core.config import get_gemini_client

    settings = get_settings()
    client = get_gemini_client()

    question = state.get("normalized_question") or state["user_question"]
    prompt = CLASSIFICATION_PROMPT.format(
        question=question,
        history=format_conversation_history(state.get("conversation_history", [])),
    )

    raw_json: dict = {}
    try:
        response = await client.aio.models.generate_content(
            model=settings.primary_model,
            contents=prompt,
        )
        raw_text = response.text or ""
        raw_json = _parse_json_response(raw_text)
    except Exception as e:
        try:
            response = await client.aio.models.generate_content(
                model=settings.fallback_model,
                contents=prompt,
            )
            raw_text = response.text or ""
            raw_json = _parse_json_response(raw_text)
        except Exception as e2:
            # 분류 실패 시 기본값(규정 조회)으로 fallback
            return _fallback_classification(question, error=f"{e} / {e2}")

    return _build_result(raw_json, question)


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict:
    """LLM 응답 텍스트에서 JSON 블록을 추출한다."""
    # 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # JSON 객체 추출
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _build_result(raw: dict, question: str) -> dict:
    """LLM 출력 dict를 GraphState 업데이트 dict로 변환한다."""
    intent = raw.get("intent", "regulation_only")
    exposure_type = raw.get("exposure_type", "unknown")
    entities = raw.get("entities", {})
    extracted_params = raw.get("extracted_params", {})
    regulation_path = raw.get("regulation_path", [])

    # required_fields: LLM이 명시하지 않으면 exposure_type 기반으로 결정
    required_fields = raw.get("required_fields") or REQUIRED_FIELDS_MAP.get(exposure_type, [])

    # missing_fields: extracted_params에 없는 required_fields
    missing_fields = raw.get("missing_fields") or _compute_missing(
        required_fields, extracted_params
    )

    # 필수 파라미터 누락이 많으면 clarification_needed로 격상
    calc_intents = {"calculation_only", "regulation_plus_calculation"}
    if intent in calc_intents and len(missing_fields) > 1:
        intent = "clarification_needed"

    english_query = raw.get("english_query") or ""
    if isinstance(english_query, str):
        english_query = english_query.strip()

    return {
        "intent": intent,
        "exposure_type": exposure_type,
        "entities": entities if isinstance(entities, dict) else {},
        "required_fields": required_fields if isinstance(required_fields, list) else [],
        "missing_fields": missing_fields if isinstance(missing_fields, list) else [],
        "regulation_path": regulation_path if isinstance(regulation_path, list) else [],
        "extracted_params": extracted_params if isinstance(extracted_params, dict) else {},
        "english_query": english_query,
        "error": None,
    }


def _compute_missing(required: list[str], params: dict) -> list[str]:
    """params에 없거나 None인 required 필드 목록 반환."""
    return [
        f for f in required
        if f not in params or params[f] is None
    ]


def _fallback_classification(question: str, error: str = "") -> dict:
    """분류 LLM 호출 실패 시 regulation_only로 안전하게 fallback."""
    return {
        "intent": "regulation_only",
        "exposure_type": "unknown",
        "entities": {},
        "required_fields": [],
        "missing_fields": [],
        "regulation_path": [],
        "extracted_params": {},
        "english_query": "",
        "error": f"분류 실패 (regulation_only로 fallback): {error}" if error else None,
    }
