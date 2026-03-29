"""DB조회 API 스키마"""
from typing import Literal, Optional
from pydantic import BaseModel


class DbQueryRequest(BaseModel):
    query_type: Optional[Literal["loan_no", "product_code"]] = None  # 하위호환용, 미사용
    base_ym: str = ""          # "YYYY-MM" 형식 또는 "" (전체 기간)
    loan_no: Optional[str] = None
    product_code: Optional[str] = None
    product_code_nm: Optional[str] = None  # 상품코드명 완전일치 필터


class DbQuerySummary(BaseModel):
    total_bs_balance: float
    total_ead: float
    total_rwa: float
    avg_rw: Optional[float]   # SUM(rwa)/SUM(ead), ead=0이면 null
    avg_pd: Optional[float]   # EAD 가중평균 PD
    avg_lgd: Optional[float]  # EAD 가중평균 LGD
    avg_ccf: Optional[float]  # 단순평균 CCF
    record_count: int


class DbQueryRow(BaseModel):
    base_ym: str
    loan_no: str
    product_code: str
    product_code_nm: str
    pd: float
    lgd: float
    ccf: float
    bs_balance: float
    ead: float
    rwa: float
    rw: Optional[float]  # rwa/ead, ead=0이면 null


class DbQueryResponse(BaseModel):
    success: bool
    query: dict
    summary: Optional[DbQuerySummary] = None
    rows: list[DbQueryRow] = []
    message: Optional[str] = None
    error_code: Optional[str] = None
