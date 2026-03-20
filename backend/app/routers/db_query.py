"""DB조회 라우터"""
from fastapi import APIRouter, HTTPException

from app.schemas.db_query import DbQueryRequest, DbQueryResponse
from app.services.db_query_service import execute_db_query, get_base_ym_list

router = APIRouter()


@router.get("/base-ym-list", response_model=list[str])
async def base_ym_list() -> list[str]:
    """CSV에서 조회 가능한 기준월 목록을 반환한다. (YYYY-MM 형식, 내림차순)"""
    try:
        return get_base_ym_list()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"기준월 목록 조회 오류: {str(e)}")


@router.post("", response_model=DbQueryResponse)
async def db_query(req: DbQueryRequest) -> DbQueryResponse:
    """
    CSV 데이터를 DuckDB로 조회한다.
    - query_type: "loan_no" | "product_code"
    - base_ym: YYYY-MM 형식 (필수)
    - loan_no / product_code: 미입력 시 해당 기준월 전체 조회
    """
    try:
        return execute_db_query(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"조회 중 오류가 발생했습니다: {str(e)}")
