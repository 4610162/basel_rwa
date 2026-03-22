"""자연어 DB조회 파싱 및 응답 포맷 서비스."""
from __future__ import annotations

import re

from app.schemas.db_query import DbQueryRequest, DbQueryResponse
from app.services.db_query_service import execute_db_query, get_base_ym_list

_LOAN_NO_RE = re.compile(
    r"(?:대출\s*번호|loan\s*(?:no\.?|number|번호)?)\s*[:：]?\s*([0-9]{5,})",
    re.IGNORECASE,
)
_PRODUCT_CODE_RE = re.compile(
    r"(?:상품\s*코드|영업상품코드|product\s*code)\s*[:：]?\s*([0-9A-Za-z_-]{4,})",
    re.IGNORECASE,
)
_BASE_YM_PATTERNS = [
    re.compile(r"\b(20\d{2})[-./](0?[1-9]|1[0-2])\b"),
    re.compile(r"\b(20\d{2})(0[1-9]|1[0-2])\b"),
    re.compile(r"\b(20\d{2})년\s*(0?[1-9]|1[0-2])월\b"),
]

_DB_INTENT_KEYWORDS = [
    "db",
    "조회",
    "찾아",
    "검색",
    "보여",
    "알려",
    "내역",
    "잔액",
    "ead",
]
_CALC_HINT_KEYWORDS = ["계산", "산출", "위험가중", "rwa 계산"]


def detect_db_query_intent(query: str) -> bool:
    """자연어 DB조회 의도를 느슨하게 감지한다."""
    q = query.lower()
    has_identifier_hint = any(token in q for token in ["대출번호", "상품코드", "영업상품코드", "loan", "product"])
    has_db_keyword = any(token in q for token in _DB_INTENT_KEYWORDS)
    has_calc_bias = any(token in q for token in _CALC_HINT_KEYWORDS)
    return has_identifier_hint and has_db_keyword and not has_calc_bias


def parse_db_query_request(query: str) -> tuple[DbQueryRequest | None, bool]:
    """
    자연어에서 DB조회 요청을 구조화한다.

    반환:
    - DbQueryRequest | None
    - bool: 기준월 미지정으로 최신월을 기본 적용했는지 여부
    """
    identifier = _extract_identifier(query)
    if not identifier:
        return None, False

    query_type, value = identifier
    base_ym = _extract_base_ym(query)
    used_latest = False

    if not base_ym:
        base_ym_list = get_base_ym_list()
        if not base_ym_list:
            return None, False
        base_ym = base_ym_list[0]
        used_latest = True

    req = DbQueryRequest(
        query_type=query_type,
        base_ym=base_ym,
        loan_no=value if query_type == "loan_no" else None,
        product_code=value if query_type == "product_code" else None,
    )
    return req, used_latest


def run_natural_language_db_query(query: str) -> tuple[DbQueryResponse | None, bool]:
    """자연어 DB조회 요청을 실행한다."""
    req, used_latest = parse_db_query_request(query)
    if req is None:
        return None, False
    return execute_db_query(req), used_latest


def format_db_query_response(result: DbQueryResponse, used_latest: bool) -> str:
    """채팅 응답용 DB조회 결과 문자열을 생성한다."""
    if not result.success:
        return f"DB 조회 중 오류가 발생했습니다. [{result.error_code}] {result.message}"

    query_type = result.query.get("query_type")
    value = result.query.get("loan_no") or result.query.get("product_code") or "전체"
    query_label = "대출번호" if query_type == "loan_no" else "상품코드"
    base_ym = str(result.query.get("base_ym", ""))

    prefix = "최신 기준월을 적용했습니다.\n" if used_latest else ""
    title = f"{query_label} `{value}` / 기준월 `{base_ym}` 조회 결과입니다."

    if not result.summary or not result.rows:
        return prefix + title + "\n\n조회 결과가 없습니다."

    summary = result.summary
    lines = [
        prefix + title,
        "",
        f"- 조회 건수: {summary.record_count}건",
        f"- 총 BS잔액: {summary.total_bs_balance:,.0f}원",
        f"- 총 EAD: {summary.total_ead:,.0f}원",
        f"- 총 RWA: {summary.total_rwa:,.0f}원",
    ]
    if summary.avg_rw is not None:
        lines.append(f"- 평균 RW율: {summary.avg_rw * 100:.2f}%")

    first_row = result.rows[0]
    lines.extend(
        [
            "",
            "첫 번째 매칭 건:",
            f"- 대출번호: {first_row.loan_no}",
            f"- 상품코드: {first_row.product_code}",
            f"- EAD: {first_row.ead:,.0f}원",
            f"- RWA: {first_row.rwa:,.0f}원",
        ]
    )

    if summary.record_count > 1:
        lines.append("- 동일 조건의 다른 매칭 건도 있어 DB조회 탭에서 전체 행을 확인하는 편이 좋습니다.")

    return "\n".join(lines)


def build_db_query_help_text() -> str:
    """자연어 DB조회 파싱 실패 시 안내 문구."""
    return (
        "DB 조회 요청으로 보이지만 조회 키를 찾지 못했습니다.\n\n"
        "예시:\n"
        '- "2025-01 기준 대출번호 123456789 조회해줘"\n'
        '- "상품코드 ABCD1234 최신 기준으로 보여줘"'
    )


def _extract_identifier(query: str) -> tuple[str, str] | None:
    loan_match = _LOAN_NO_RE.search(query)
    if loan_match:
        return "loan_no", loan_match.group(1)

    product_match = _PRODUCT_CODE_RE.search(query)
    if product_match:
        return "product_code", product_match.group(1)

    return None


def _extract_base_ym(query: str) -> str | None:
    for pattern in _BASE_YM_PATTERNS:
        match = pattern.search(query)
        if match:
            year, month = match.group(1), match.group(2)
            return f"{year}-{int(month):02d}"
    return None
