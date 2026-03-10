"""
RWA 산출 라우터
"""
from fastapi import APIRouter, HTTPException

from app.schemas.rwa import RwaCalculationRequest, RwaResult
from app.services.rwa_service import calculate_rwa

router = APIRouter()


@router.post("/rwa", response_model=RwaResult)
async def rwa_calculate(req: RwaCalculationRequest):
    """익스포져 유형별 RWA 산출 (SA 표준방법)."""
    try:
        return calculate_rwa(req)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"내부 오류: {e}")
