"""
RWA 계산 의도 감지 및 입력 안내 모듈

사용자가 채팅에서 RWA 계산을 요청할 때,
기존 RAG 답변 대신 계산 설명 + 입력 체크리스트를 반환한다.

입력 체크리스트는 exposure_schema.py에서 자동 생성된다.
하드코딩 템플릿은 이 파일에 존재하지 않는다.

수집 흐름 (Collection Flow):
- 챗봇이 입력 템플릿을 보낸 이후부터 수집 흐름이 시작된다.
- 수집 상태는 대화 히스토리(history)에서 재구성한다 (서버 세션 없음).
- 흐름 감지 마커:
    FLOW_START: "계산에 필요한 입력값"  ← build_calc_guidance() 출력에 포함
    FLOW_CONT:  "입력 현황"             ← build_collection_response() 출력에 포함
"""
from __future__ import annotations

from app.services.exposure_schema import (
    EXPOSURE_SCHEMAS,
    ExposureSchema,
    FieldSchema,
    build_template_string,
    get_schema,
)

# 수집 흐름 감지 마커
_FLOW_START_MARKER = "계산에 필요한 입력값"   # 최초 템플릿에만 포함
_FLOW_CONT_MARKER = "입력 현황"               # 후속 누락 필드 질문에 포함
_FLOW_ANY_MARKERS = (_FLOW_START_MARKER, _FLOW_CONT_MARKER)

# ── 계산 세션 상태 상수 ────────────────────────────────────────────────────────
SESSION_IDLE = "idle"               # 계산 세션 없음
SESSION_COLLECTING = "collecting_inputs"   # 입력값 수집 중
SESSION_COMPLETED = "completed"     # 계산 완료
SESSION_CANCELLED = "cancelled"     # 사용자가 취소

# ── 취소 명령 키워드 ───────────────────────────────────────────────────────────
_CANCEL_KEYWORDS = [
    "취소", "초기화", "처음부터", "중단", "그만", "새로시작", "다시시작",
    "리셋", "reset", "새로 시작", "다시 시작",
]

# ── 일반 질문 판별: 한국어 질문 어미 ──────────────────────────────────────────
_QUESTION_ENDINGS = [
    "인가요", "인가", "인지요", "인지", "나요", "까요", "합니까",
    "건가요", "건지", "는지", "을까요", "을까",
    "알려줘", "알려주세요", "설명해줘", "설명해주세요",
    "뭔가요", "뭐죠", "뭐예요", "뭐야", "뭐인가요",
]

# ── 일반 질문 판별: 규정/설명 관련 키워드 ─────────────────────────────────────
_REGULATORY_QUESTION_KEYWORDS = [
    "규정", "조항", "세칙", "의미", "이유", "원리",
    "기준은", "기준이", "차이는", "차이가", "어떻게 되", "어떻게되",
    "무엇인가", "무엇이", "어떤 경우", "어떤경우",
]

# ── 익스포져 유형 감지 키워드 ─────────────────────────────────────────────────
EXPOSURE_KEYWORDS: dict[str, list[str]] = {
    "corporate": [
        "기업 익스포져", "기업익스포져", "기업노출", "법인 익스포져", "법인익스포져",
        "일반기업", "일반 기업", "중소기업", "sme", "법인대출",
        "특수목적금융", "pf 익스포져", "프로젝트금융",
    ],
    "bank": [
        "은행 익스포져", "은행익스포져", "금융기관 익스포져", "금융기관익스포져",
        "은행노출", "금융기관노출", "커버드본드",
    ],
    "sovereign": [
        "정부 익스포져", "정부익스포져", "정부노출", "중앙정부", "국채",
        "공공기관 익스포져", "공공기관익스포져", "mdb", "국제개발은행",
        "pse", "지방정부", "sovereign",
    ],
    "retail": [
        "소매 익스포져", "소매익스포져", "소매노출", "소매대출",
        "개인대출", "신용카드 익스포져", "리볼빙", "소기업대출",
        "retail", "소매",
    ],
    "real_estate": [
        "부동산 익스포져", "부동산익스포져", "부동산노출",
        "주거용 부동산", "상업용 부동산", "부동산담보", "담보대출",
        "adc", "ipre", "모기지",
    ],
    "equity": [
        "주식 익스포져", "주식익스포져", "주식노출",
        "출자금 익스포져", "출자 익스포져", "출자금",
        "equity 익스포져",
    ],
    "ciu": [
        "ciu", "집합투자기구", "집합투자 익스포져", "집합투자익스포져",
        "펀드 익스포져", "펀드익스포져", "펀드노출",
        "lta", "mba", "fba",
    ],
}

# ── 익스포져별 규정 설명 (스키마의 description보다 상세한 마크다운 버전) ─────
EXPOSURE_DESCRIPTIONS: dict[str, str] = {
    "corporate": (
        "## 기업 익스포져 RWA 계산 안내\n\n"
        "기업 익스포져는 **표준방법(SA)** 기준으로 외부신용등급에 따라 **20%~150%** 위험가중치를 적용합니다.\n\n"
        "| 외부등급    | 위험가중치 |\n"
        "|-------------|------------|\n"
        "| AAA~AA-     | 20%        |\n"
        "| A+~A-       | 50%        |\n"
        "| BBB+~BBB-   | 75%        |\n"
        "| BB+~BB-     | 100%       |\n"
        "| B+~이하     | 150%       |\n"
        "| 무등급      | 100% (SME 우대 시 85%) |\n\n"
        "특수목적금융(PF/OF/CF), IPRE, HVCRE 등 세부 유형별로 기준이 달라집니다.\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제37조~제38조의2"
    ),
    "bank": (
        "## 은행 익스포져 RWA 계산 안내\n\n"
        "은행 익스포져는 **표준방법(SA)** 기준으로 외부등급 또는 실사등급(DD)에 따라 위험가중치를 결정합니다.\n\n"
        "| 구분                        | 위험가중치 |\n"
        "|-----------------------------|------------|\n"
        "| 외부등급 AA 이상            | 20%        |\n"
        "| 외부등급 A+~A-              | 30%        |\n"
        "| 외부등급 BBB+~BBB-          | 50%        |\n"
        "| DD A등급 (우량)             | 30%~40%    |\n"
        "| DD B등급                    | 75%        |\n"
        "| DD C등급                    | 150%       |\n"
        "| 커버드본드 (외부 AA 이상)   | 10%        |\n"
        "| 단기 원화 (3개월 이내)      | 20%        |\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제35조~제36조"
    ),
    "sovereign": (
        "## 정부·공공기관 익스포져 RWA 계산 안내\n\n"
        "정부 익스포져는 **중앙정부 등급** 또는 **OECD 국가신용도**에 따라 위험가중치를 결정합니다.\n\n"
        "| 구분                              | 위험가중치 |\n"
        "|-----------------------------------|------------|\n"
        "| 국내 중앙정부 (원화 표시·조달)    | 0%         |\n"
        "| 외국 중앙정부 (외부등급 AAA~AA-)  | 0%         |\n"
        "| 외국 중앙정부 (A+~A-)             | 20%        |\n"
        "| 외국 중앙정부 (BBB+~BBB-)         | 50%        |\n"
        "| 외국 중앙정부 (BB+~B-)            | 100%       |\n"
        "| 무등급 중앙정부                   | 100%       |\n"
        "| 무위험기관 (BIS, IMF, ECB 등)     | 0%         |\n"
        "| 우량 MDB (World Bank 등)          | 0%         |\n\n"
        "공공기관(PSE)은 정부간주/은행간주/기타 분류에 따라 별도 기준 적용.\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제29조~제34조"
    ),
    "retail": (
        "## 소매 익스포져 RWA 계산 안내\n\n"
        "소매 익스포져는 적격 여부에 따라 **75%** 또는 차주 기준 위험가중치를 적용합니다.\n\n"
        "| 구분           | 위험가중치 |\n"
        "|----------------|------------|\n"
        "| 적격 소매      | 75%        |\n"
        "| 비적격 소매    | 차주 RW 기준 |\n\n"
        "**적격 소매 기준:**\n"
        "- 차주가 개인 또는 소기업\n"
        "- 단일 차주에 대한 총 익스포져 ≤ 소매 포트폴리오의 0.2%\n"
        "- 소기업의 경우 총 익스포져 ≤ 10억원\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제39조"
    ),
    "real_estate": (
        "## 부동산 익스포져 RWA 계산 안내\n\n"
        "부동산 익스포져는 **LTV 비율**과 부동산 유형(주거용/상업용/ADC 등)에 따라 위험가중치가 달라집니다.\n\n"
        "| 유형              | LTV   | 위험가중치 |\n"
        "|-------------------|-------|------------|\n"
        "| 비IPRE 상업용     | ≤60%  | min(60%, 차주RW) |\n"
        "| 비IPRE 상업용     | >60%  | 차주 RW    |\n"
        "| IPRE              | ≤60%  | 70%        |\n"
        "| IPRE              | 60~80%| 90%        |\n"
        "| IPRE              | >80%  | 110%       |\n"
        "| ADC               | -     | 150% (주거용 예외 100%) |\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제41조~제41조의2"
    ),
    "equity": (
        "## 주식 익스포져 RWA 계산 안내\n\n"
        "주식 익스포져는 상장/비상장 여부, 투기성 여부에 따라 **250%~400%** 위험가중치를 적용합니다.\n\n"
        "| 유형                     | 위험가중치 |\n"
        "|--------------------------|------------|\n"
        "| 일반 상장주식             | 250%       |\n"
        "| 비상장 장기보유·출자전환  | 250%       |\n"
        "| 투기적 비상장주식 (VC 등) | 400%       |\n"
        "| 정부보조 프로그램 주식    | 100%       |\n"
        "| 후순위채권·기타 자본수단  | 150%       |\n"
        "| 비금융자회사 대규모 출자  | 1,250%     |\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제38조의3"
    ),
    "ciu": (
        "## CIU(집합투자기구) 익스포져 RWA 계산 안내\n\n"
        "CIU 익스포져는 **3가지 접근법** 중 선택 적용합니다.\n\n"
        "| 접근법          | 설명                         | 위험가중치        |\n"
        "|-----------------|------------------------------|-------------------|\n"
        "| LTA (투시법)    | 기초자산을 직접 투시하여 계산 | 기초자산 기준     |\n"
        "| MBA (위임기준법)| 투자제한 정보 기반 산출       | 최대 허용 RW 기준 |\n"
        "| FBA (폴백법)    | 구성 정보 없을 때 적용        | 1,250%            |\n\n"
        "**적용 근거:** 은행업감독업무시행세칙 [별표 3] 제38조의4"
    ),
}

# ── 익스포져 유형 미감지 시 기본 안내 ─────────────────────────────────────────
_SUPPORTED_LABELS = "\n".join(
    f"- **{s.label}**"
    for s in EXPOSURE_SCHEMAS.values()
)

DEFAULT_GUIDANCE = (
    "## RWA 계산 안내\n\n"
    "RWA(위험가중자산) 계산을 원하시는군요! 어떤 익스포져 유형을 계산하고 싶으신가요?\n\n"
    f"**지원 익스포져 유형:**\n{_SUPPORTED_LABELS}\n\n"
    "예시: \"기업 익스포져 RWA 계산하고 싶어\" 또는 \"소매 익스포져 계산 입력값 알려줘\""
)


# ── 공개 함수 ─────────────────────────────────────────────────────────────────

def detect_calc_intent(query: str) -> bool:
    """
    사용자 입력에서 RWA 계산 의도를 감지한다.

    감지 조건 (OR):
    1. 직접적인 계산 의도 구문 포함
    2. RWA/위험가중 관련 키워드 + 계산/산출/입력 관련 키워드 동시 등장
    3. 익스포져 유형 키워드 + 계산 관련 키워드 동시 등장
    """
    q = query.lower()
    q_nospace = q.replace(" ", "")

    has_rwa = any(kw in q for kw in ["rwa", "위험가중자산", "위험가중치"])
    has_calc = any(kw in q for kw in ["계산", "산출", "구하", "필요", "입력"])

    direct_phrases = [
        "rwa계산", "rwa산출", "위험가중자산계산", "위험가중치계산",
        "계산하고싶", "계산해줘", "계산하려면", "계산방법",
        "계산하는방법", "어떻게계산", "뭐가필요", "무엇이필요",
        "필수입력", "입력값", "입력이뭐", "입력뭐",
        # 새 계산 시작 의도 (초기화/취소 후 재진입)
        "새계산", "새로운계산", "새계산시작", "다른계산", "다른익스포져",
    ]
    if any(p in q_nospace for p in direct_phrases):
        return True

    if has_rwa and has_calc:
        return True

    has_exposure = any(
        kw.lower() in q
        for keywords in EXPOSURE_KEYWORDS.values()
        for kw in keywords
    )
    if has_exposure and has_calc:
        return True

    return False


def detect_exposure_type(query: str) -> str | None:
    """
    사용자 입력에서 익스포져 유형을 감지한다.
    감지 실패 시 None 반환.
    """
    q = query.lower()
    for exposure_type, keywords in EXPOSURE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in q:
                return exposure_type
    return None


def is_in_collection_flow(history: list[dict]) -> bool:
    """
    가장 최근 assistant 메시지가 수집 흐름 메시지인지 확인한다.

    수집 흐름 = 챗봇이 입력 템플릿이나 누락 필드 질문을 마지막으로 보낸 상태.
    RAG 답변이 그 이후에 나오면 흐름이 끊긴 것으로 간주한다.
    """
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        return any(marker in content for marker in _FLOW_ANY_MARKERS)
    return False


def get_flow_exposure_type(history: list[dict]) -> str | None:
    """
    최근 수집 흐름 메시지에서 익스포져 유형을 감지한다.
    """
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if any(marker in content for marker in _FLOW_ANY_MARKERS):
            return _detect_exposure_type_from_content(content)
    return None


def _detect_exposure_type_from_content(content: str) -> str | None:
    """assistant 메시지 내용에서 익스포져 유형 레이블을 찾아 id를 반환한다."""
    for exp_type, schema in EXPOSURE_SCHEMAS.items():
        if schema.label in content:
            return exp_type
    return None


def _find_flow_start_idx(history: list[dict]) -> int | None:
    """
    히스토리에서 가장 최근의 흐름 시작(최초 템플릿) 인덱스를 반환한다.

    흐름 시작 = _FLOW_START_MARKER("계산에 필요한 입력값")가 포함된 assistant 메시지.
    사용자가 다른 유형으로 전환하면 새 템플릿이 최근 것이 되므로 자동 리셋.
    """
    for i in range(len(history) - 1, -1, -1):
        msg = history[i]
        if msg.get("role") == "assistant" and _FLOW_START_MARKER in msg.get("content", ""):
            return i
    return None


def accumulate_field_values(
    history: list[dict], schema: ExposureSchema
) -> dict[str, str]:
    """
    수집 흐름 시작 이후 모든 user 메시지를 파싱해 누적된 필드값을 반환한다.

    - 서버 세션 없이 history만으로 상태 재구성
    - flow_start(최초 안내) 메시지의 DB_PREFILL 마커를 초기값으로 사용
    - 나중에 입력된 user 값이 DB 조회값을 덮어씀 (사용자 명시 입력 우선)
    """
    from app.services.rwa_field_parser import parse_field_values
    from app.services.db_lookup_service import extract_prefill_from_message

    flow_start_idx = _find_flow_start_idx(history)
    if flow_start_idx is None:
        return {}

    # DB 자동 조회값을 초기값으로 설정 (마커가 없으면 빈 dict)
    accumulated: dict[str, str] = {}
    flow_start_content = history[flow_start_idx].get("content", "")
    accumulated.update(extract_prefill_from_message(flow_start_content))

    # 사용자 입력값으로 덮어씀 (나중에 입력된 값이 이전 값을 덮어씀)
    for msg in history[flow_start_idx + 1:]:
        if msg.get("role") == "user":
            parsed = parse_field_values(msg["content"], schema)
            accumulated.update(parsed)

    return accumulated


def get_missing_required_fields(
    accumulated: dict[str, str], schema: ExposureSchema
) -> list[FieldSchema]:
    """required_fields 중 아직 수집되지 않은 필드 목록을 반환한다."""
    return [f for f in schema.required_fields if f.name not in accumulated]


def build_collection_response(
    accumulated: dict[str, str],
    missing: list[FieldSchema],
    schema: ExposureSchema,
) -> str:
    """
    현재 수집 상태와 누락 필드 질문을 담은 응답 문자열을 생성한다.

    - 상태 요약: "입력 완료: X/Y | 추가 필요: 필드1, 필드2"
    - 누락 필드만 재질문 (전체 체크리스트 반복 없음)
    - 모두 수집 시: 계산 가능 확인 메시지
    """
    total = len(schema.required_fields)
    collected = total - len(missing)

    # ── 상태 헤더 ──────────────────────────────────────────────────────────
    header = f"### {schema.label} 입력 현황\n\n"

    if missing:
        missing_labels = ", ".join(f.label for f in missing)
        status = (
            f"> ✅ 입력 완료: **{collected}/{total}**  |  "
            f"❌ 추가 필요: **{missing_labels}**"
        )
    else:
        status = f"> ✅ 입력 완료: **{total}/{total}**  |  모든 필수 입력값 수집됨"

    lines = [header + status, ""]

    # ── 누락 필드 재질문 ────────────────────────────────────────────────────
    if missing:
        lines.append("다음 정보를 추가로 입력해주세요:\n")
        for f in missing:
            if f.options:
                # 옵션이 많으면 앞 5개 + "..." 형태로 축약
                if len(f.options) > 6:
                    opts_preview = " / ".join(f.options[:5]) + " / ..."
                else:
                    opts_preview = " / ".join(f.options)
                lines.append(f"- **{f.label}**: {opts_preview}")
            else:
                hint = f.hint or "값을 직접 입력해주세요"
                lines.append(f"- **{f.label}**: {hint}")
    else:
        # ── 모두 수집됨 ────────────────────────────────────────────────────
        from app.services.rwa_field_parser import format_amount

        lines.append("필수 입력값이 모두 수집되었습니다. 수집된 값:\n")
        for f in schema.required_fields:
            raw = accumulated.get(f.name, "")
            display = format_amount(raw) if f.name == "exposure" else raw
            lines.append(f"- **{f.label}**: {display}")
        lines.append(
            "\n계산을 진행할 준비가 되었습니다. "
            "계산 실행 기능은 추후 구현 예정입니다."
        )

    return "\n".join(lines)


def build_field_sources(
    history: list[dict],
    schema: ExposureSchema,
    accumulated: dict[str, str],
) -> dict[str, str]:
    """
    accumulated 각 필드의 입력 출처를 반환한다.

    반환값: {field_name: "db" | "user"}
        "db"   — flow_start 메시지의 DB_PREFILL 마커에 포함된 필드 (DB 자동 조회)
        "user" — 사용자가 직접 입력한 필드

    참고: 규정 적용으로 파생된 값(예: is_sme_legal)은 별도 source 없이
    계산 결과의 basis 문자열에서 설명된다.
    """
    from app.services.db_lookup_service import extract_prefill_from_message

    db_fields: set[str] = set()
    flow_start_idx = _find_flow_start_idx(history)
    if flow_start_idx is not None:
        content = history[flow_start_idx].get("content", "")
        db_fields = set(extract_prefill_from_message(content).keys())

    return {
        field_name: ("db" if field_name in db_fields else "user")
        for field_name in accumulated
    }


def get_session_state(history: list[dict]) -> str:
    """
    대화 히스토리로부터 현재 계산 세션 상태를 반환한다.

    SESSION_IDLE       : 수집 흐름 없음 (초기 상태)
    SESSION_COLLECTING : 수집 흐름 마커가 있는 assistant 메시지가 마지막 → 입력 수집 중
    SESSION_COMPLETED  : 계산 결과 마커("위험가중치:" + "RWA:")가 마지막 → 계산 완료
    SESSION_CANCELLED  : 취소 마커가 마지막 → 세션 취소
    """
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if "계산 취소" in content:
            return SESSION_CANCELLED
        if "위험가중치:" in content and "RWA:" in content:
            return SESSION_COMPLETED
        if any(marker in content for marker in _FLOW_ANY_MARKERS):
            return SESSION_COLLECTING
        return SESSION_IDLE
    return SESSION_IDLE


def is_cancel_command(query: str) -> bool:
    """취소/초기화 명령인지 확인한다."""
    q = query.lower().replace(" ", "")
    return any(kw.replace(" ", "") in q for kw in _CANCEL_KEYWORDS)


def is_general_question(query: str) -> bool:
    """
    일반 규정/개념 질문인지 판별한다 (계산 입력값이 아닌 경우).

    판별 순서:
    1. 물음표 포함
    2. 한국어 질문 어미로 끝남
    3. 의문사로 시작
    4. 규정/설명 관련 키워드 포함
    """
    q = query.strip()
    q_lower = q.lower()

    if "?" in q or "？" in q:
        return True

    if any(q_lower.endswith(e) for e in _QUESTION_ENDINGS):
        return True

    if any(q_lower.startswith(w) for w in ["왜 ", "왜\n", "어떻게 ", "무엇", "어떤 "]):
        return True

    if any(kw in q_lower for kw in _REGULATORY_QUESTION_KEYWORDS):
        return True

    return False


def classify_collection_message(query: str, schema: "ExposureSchema") -> str:
    """
    계산 입력 수집 흐름 중 사용자 메시지를 분류한다.

    반환값:
        "cancel"           — 취소/초기화 명령
        "general_question" — 일반 규정 질문 → RAG 처리
        "calc_input"       — 계산 입력값 → 슬롯필링 처리

    우선순위: cancel > general_question > calc_input > general_question(폴백)
    """
    from app.services.rwa_field_parser import parse_field_values

    if is_cancel_command(query):
        return "cancel"

    if is_general_question(query):
        return "general_question"

    parsed = parse_field_values(query, schema)
    if parsed:
        return "calc_input"

    return "general_question"


def build_calc_guidance(query: str) -> str:
    """
    RWA 계산 안내 응답 문자열을 반환한다.

    익스포져 유형이 감지되면: EXPOSURE_DESCRIPTIONS의 설명 + 스키마 기반 입력 체크리스트
    감지 실패 시: 유형 선택 안내(DEFAULT_GUIDANCE)
    """
    exposure_type = detect_exposure_type(query)

    if exposure_type and exposure_type in EXPOSURE_DESCRIPTIONS:
        description = EXPOSURE_DESCRIPTIONS[exposure_type]
        schema = get_schema(exposure_type)

        if schema is None:
            # 스키마가 없는 경우 (확장 중인 유형) — 설명만 반환
            return description

        template = build_template_string(schema)
        return (
            f"{description}\n\n"
            "---\n\n"
            "### 계산에 필요한 입력값\n\n"
            "아래 템플릿을 복사하여 값을 채워 입력해주시면 RWA를 계산해 드리겠습니다:\n\n"
            f"{template}"
        )

    return DEFAULT_GUIDANCE
