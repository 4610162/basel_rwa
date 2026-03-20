"""DB조회 API 스키마"""
from typing import Literal, Optional
from pydantic import BaseModel


class DbQueryRequest(BaseModel):
    query_type: Literal["loan_no", "product_code"]
    base_ym: str  # YYYY-MM 형식
    loan_no: Optional[str] = None
    product_code: Optional[str] = None


class DbQuerySummary(BaseModel):
    total_bs_balance: float
    total_ead: float
    total_rwa: float
    avg_rw: Optional[float]  # SUM(rwa)/SUM(ead), ead=0이면 null
    record_count: int


class DbQueryRow(BaseModel):
    base_ym: str
    loan_no: str
    product_code: str
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
