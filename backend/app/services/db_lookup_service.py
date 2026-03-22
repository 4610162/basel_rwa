"""
DB 식별자 감지 및 익스포져 자동 조회 서비스

사용자 채팅에서 대출번호/상품코드를 감지한 뒤 DuckDB를 통해
EAD(익스포져 금액)를 자동 조회하여 RWA 계산 흐름에 pre-fill한다.

설계 원칙:
- DB에 실제로 존재하는 값만 사용 (ead → exposure)
- product_code_nm 등 텍스트 컬럼은 정보 표시용, 계산 입력으로 추정하지 않음
- 복수 레코드 매칭 시 자동 보완하지 않고 사용자에게 명시적으로 안내
- 기존 db_query_service.py의 DuckDB 연결/경로 재사용

자동 보완 가능 필드:
    exposure ← EAD (EAD = Exposure at Default, RWA 계산 기준 익스포져 금액)

마커 포맷 (assistant 메시지에 삽입):
    <!-- DB_PREFILL:{"exposure":"12007345069"} -->
    accumulate_field_values() 에서 이 마커를 파싱해 초기 accumulated 값으로 사용
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import duckdb

from app.services.db_query_service import CSV_PATH, get_base_ym_list

# ── 마커 상수 ──────────────────────────────────────────────────────────────────
_PREFILL_START = "<!-- DB_PREFILL:"
_PREFILL_END = " -->"

# ── 식별자 감지 정규식 ─────────────────────────────────────────────────────────
_LOAN_NO_RE = re.compile(
    r"(?:대출\s*번호|loan\s*(?:no\.?|number|번호)?)\s*[:：]?\s*([0-9]{5,})",
    re.IGNORECASE,
)
_PRODUCT_CODE_RE = re.compile(
    r"(?:상품\s*코드|product\s*code)\s*[:：]?\s*([0-9A-Za-z]{4,})",
    re.IGNORECASE,
)


# ── 공개 함수 ──────────────────────────────────────────────────────────────────

def detect_identifier(query: str) -> Optional[tuple[str, str]]:
    """
    사용자 쿼리에서 거래 식별자를 감지한다.

    지원 식별자:
        - 대출번호 / loan no / loan number  → ("loan_no", value)
        - 상품코드 / product code           → ("product_code", value)

    반환: (query_type, value) 또는 None (식별자 미감지)
    """
    m = _LOAN_NO_RE.search(query)
    if m:
        return ("loan_no", m.group(1))
    m = _PRODUCT_CODE_RE.search(query)
    if m:
        return ("product_code", m.group(1))
    return None


def lookup_exposure_from_db(
    query_type: str, value: str
) -> Optional[dict]:
    """
    DuckDB에서 식별자로 EAD(익스포져 금액)를 조회한다.

    - 가장 최근 기준월(base_ym) 데이터 사용
    - loan_no: 단일 레코드 기대 (고유 식별자)
    - product_code: 레코드 수 확인 후 반환

    반환:
        {
            "exposure": str,          # EAD 원 단위 정수 문자열
            "loan_no": str,
            "product_code": str,
            "product_code_nm": str,
            "base_ym": str,           # 조회 기준월 YYYY-MM
            "record_count": int,      # 매칭 레코드 수 (>1이면 자동 보완 불가)
        }
        또는 None (CSV 없음, 기준월 없음, 조회 결과 없음)
    """
    if not os.path.exists(CSV_PATH):
        return None

    base_ym_list = get_base_ym_list()
    if not base_ym_list:
        return None

    latest_ym = base_ym_list[0]
    base_ym_int = int(latest_ym.replace("-", ""))
    col = "loan_no" if query_type == "loan_no" else "product_code"

    con = duckdb.connect()
    try:
        # 레코드 수 확인
        count_row = con.execute(
            f"SELECT COUNT(*) FROM read_csv_auto('{CSV_PATH}') "
            f"WHERE base_ym = ? AND CAST({col} AS VARCHAR) = ?",
            [base_ym_int, value],
        ).fetchone()
        count = int(count_row[0]) if count_row else 0
        if count == 0:
            return None

        # 단일 행 조회 (LIMIT 1)
        row = con.execute(
            f"SELECT loan_no, product_code, product_code_nm, ead "
            f"FROM read_csv_auto('{CSV_PATH}') "
            f"WHERE base_ym = ? AND CAST({col} AS VARCHAR) = ? "
            f"LIMIT 1",
            [base_ym_int, value],
        ).fetchone()
        if row is None:
            return None

        loan_no, product_code, product_code_nm, ead = row
        return {
            "exposure": str(int(ead)),
            "loan_no": str(loan_no),
            "product_code": str(product_code),
            "product_code_nm": str(product_code_nm) if product_code_nm else "",
            "base_ym": latest_ym,
            "record_count": count,
        }
    finally:
        con.close()


def build_prefill_marker(db_result: dict) -> str:
    """
    DB 조회 결과에서 계산에 사용할 값만 추출해 마커 문자열을 생성한다.

    마커는 assistant 메시지 끝에 삽입되어, 이후 accumulate_field_values()가
    히스토리에서 파싱해 초기 accumulated 값으로 사용한다.

    계산에 사용되는 필드: exposure (EAD)만 포함
    """
    payload = {"exposure": db_result["exposure"]}
    return _PREFILL_START + json.dumps(payload, ensure_ascii=False) + _PREFILL_END


def extract_prefill_from_message(content: str) -> dict:
    """
    assistant 메시지에서 DB_PREFILL 마커를 파싱해 dict로 반환한다.

    마커가 없거나 파싱 실패 시 빈 dict 반환.
    accumulate_field_values()에서 flow_start 메시지를 대상으로 호출된다.
    """
    start = content.find(_PREFILL_START)
    if start == -1:
        return {}
    start += len(_PREFILL_START)
    end = content.find(_PREFILL_END, start)
    if end == -1:
        return {}
    try:
        return json.loads(content[start:end])
    except (json.JSONDecodeError, ValueError):
        return {}
