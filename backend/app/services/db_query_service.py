"""DuckDB 기반 CSV 조회 서비스"""
import os
from typing import Optional

import duckdb

from app.schemas.db_query import DbQueryRequest, DbQueryResponse, DbQueryRow, DbQuerySummary

# CSV 파일 경로 (backend/ 기준 상대경로)
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "sql_db", "raw_data.csv")
CSV_PATH = os.path.normpath(CSV_PATH)


def _base_ym_to_int(base_ym: str) -> int:
    """'YYYY-MM' → 정수 YYYYMM 변환"""
    return int(base_ym.replace("-", ""))


def _int_to_base_ym(value: int) -> str:
    """정수 YYYYMM → 'YYYY-MM' 변환"""
    s = str(value)
    return s[:4] + "-" + s[4:]


def get_base_ym_list() -> list[str]:
    """CSV에서 distinct base_ym 목록을 YYYY-MM 형식으로 반환 (내림차순)"""
    if not os.path.exists(CSV_PATH):
        return []
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT DISTINCT base_ym FROM read_csv_auto('{CSV_PATH}') ORDER BY base_ym DESC"
        ).fetchall()
        return [_int_to_base_ym(int(r[0])) for r in rows]
    finally:
        con.close()


def _build_where(base_ym_int: int, query_type: str, value: Optional[str]) -> tuple[str, list]:
    """WHERE 절과 파라미터 리스트를 반환한다. value가 없으면 base_ym만 필터링."""
    if value:
        col = "loan_no" if query_type == "loan_no" else "product_code"
        return f"base_ym = ? AND CAST({col} AS VARCHAR) = ?", [base_ym_int, value]
    return "base_ym = ?", [base_ym_int]


def _get_summary(
    con: duckdb.DuckDBPyConnection,
    csv_path: str,
    base_ym_int: int,
    query_type: str,
    value: Optional[str],
) -> Optional[DbQuerySummary]:
    """요약 집계 쿼리"""
    where, params = _build_where(base_ym_int, query_type, value)
    sql = f"""
        SELECT
            COUNT(*) AS record_count,
            SUM(bs_balance) AS total_bs_balance,
            SUM(ead) AS total_ead,
            SUM(rwa) AS total_rwa,
            CASE WHEN SUM(ead) > 0 THEN SUM(rwa) / SUM(ead) ELSE NULL END AS avg_rw
        FROM read_csv_auto('{csv_path}')
        WHERE {where}
    """
    row = con.execute(sql, params).fetchone()
    if row is None or row[0] == 0:
        return None

    record_count, total_bs, total_ead, total_rwa, avg_rw = row
    return DbQuerySummary(
        total_bs_balance=float(total_bs or 0),
        total_ead=float(total_ead or 0),
        total_rwa=float(total_rwa or 0),
        avg_rw=float(avg_rw) if avg_rw is not None else None,
        record_count=int(record_count),
    )


def _get_rows(
    con: duckdb.DuckDBPyConnection,
    csv_path: str,
    base_ym_int: int,
    query_type: str,
    value: Optional[str],
) -> list[DbQueryRow]:
    """상세 행 조회 쿼리"""
    where, params = _build_where(base_ym_int, query_type, value)
    sql = f"""
        SELECT
            CAST(base_ym AS VARCHAR) AS base_ym,
            CAST(loan_no AS VARCHAR) AS loan_no,
            CAST(product_code AS VARCHAR) AS product_code,
            bs_balance,
            ead,
            rwa,
            CASE WHEN ead > 0 THEN rwa / ead ELSE NULL END AS rw
        FROM read_csv_auto('{csv_path}')
        WHERE {where}
        ORDER BY base_ym, loan_no
    """
    results = con.execute(sql, params).fetchall()
    return [
        DbQueryRow(
            base_ym=str(r[0]),
            loan_no=str(r[1]),
            product_code=str(r[2]),
            bs_balance=float(r[3]),
            ead=float(r[4]),
            rwa=float(r[5]),
            rw=float(r[6]) if r[6] is not None else None,
        )
        for r in results
    ]


def execute_db_query(req: DbQueryRequest) -> DbQueryResponse:
    """요청을 검증하고 DuckDB로 CSV를 조회한다."""
    if not req.base_ym or len(req.base_ym) != 7 or req.base_ym[4] != "-":
        return DbQueryResponse(
            success=False,
            query=req.model_dump(),
            error_code="INVALID_BASE_YM",
            message="기준월 형식이 올바르지 않습니다. YYYY-MM 형식으로 입력하세요.",
        )

    if not os.path.exists(CSV_PATH):
        return DbQueryResponse(
            success=False,
            query=req.model_dump(),
            error_code="CSV_NOT_FOUND",
            message=f"데이터 파일을 찾을 수 없습니다: {CSV_PATH}",
        )

    base_ym_int = _base_ym_to_int(req.base_ym)
    # 값이 없으면 None 처리 → 해당 필터 생략
    value = (req.loan_no or "").strip() or None if req.query_type == "loan_no" else (req.product_code or "").strip() or None

    con = duckdb.connect()
    try:
        summary = _get_summary(con, CSV_PATH, base_ym_int, req.query_type, value)
        if summary is None:
            return DbQueryResponse(
                success=True,
                query=req.model_dump(),
                summary=None,
                rows=[],
                message="조회 결과가 없습니다.",
            )

        rows = _get_rows(con, CSV_PATH, base_ym_int, req.query_type, value)
        return DbQueryResponse(
            success=True,
            query=req.model_dump(),
            summary=summary,
            rows=rows,
        )
    finally:
        con.close()
