"""
데이터 분석 서비스 — 데이터 분석 모드 전용

흐름:
1. AI Call #1 (ai_parse_query): 자연어 → 구조화된 DataQuerySpec
2. validate_spec: 파라미터 검증 및 정규화
3. execute_query: 코드 생성 SQL로 DuckDB 조회 (LLM 생성 SQL 실행 금지)
4. build_summary_stats: 요약 통계 생성
5. AI Call #2 (ai_generate_answer): 요약 통계 → 자연어 최종 답변 스트리밍
6. build_table_widget / build_chart_widget: 위젯 페이로드 생성
"""
from __future__ import annotations

import json
import os
import re
from typing import AsyncGenerator, Optional

import duckdb
from pydantic import BaseModel, field_validator, model_validator

# CSV 경로 — db_query_service.py와 동일한 위치 참조
CSV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "sql_db", "raw_data.csv")
)

# ── 허용 메트릭 매핑 ────────────────────────────────────────────────────────────
# 사용자 요청 키워드 → DB 컬럼명
METRIC_ALIASES: dict[str, str] = {
    "잔액": "bs_balance",
    "bs잔액": "bs_balance",
    "bs_balance": "bs_balance",
    "balance": "bs_balance",
    "ead": "ead",
    "rw": "rw",
    "rw율": "rw",
    "rwa": "rwa",
    "pd": "pd",
    "부도율": "pd",
    "lgd": "lgd",
    "부도시손실율": "lgd",
    "손실율": "lgd",
    "ccf": "ccf",
    "신용환산율": "ccf",
}
ALLOWED_METRICS: list[str] = ["bs_balance", "ead", "rw", "rwa", "pd", "lgd", "ccf"]

METRIC_LABELS: dict[str, str] = {
    "bs_balance": "BS잔액",
    "ead": "부도시익스포져(EAD)",
    "rw": "RW율",
    "rwa": "위험가중자산(RWA)",
    "pd": "부도율(PD)",
    "lgd": "부도시손실율(LGD)",
    "ccf": "CCF(신용환산율)",
}


# ── 드라이버 메트릭 (변동원인분석용) ───────────────────────────────────────────
DRIVER_METRICS: list[str] = ["bs_balance", "ead", "pd", "lgd"]

DRIVER_METRIC_LABELS: dict[str, str] = {
    "bs_balance": "BS잔액",
    "ead": "부도시익스포져(EAD)",
    "pd": "부도율(PD)",
    "lgd": "부도시손실율(LGD)",
}


# ── 구조화 쿼리 스펙 ────────────────────────────────────────────────────────────

class DataQuerySpec(BaseModel):
    identifier_type: str          # "loan_no" | "product_code" | "product_code_nm" | "all_products"
    identifier_value: str
    start_month: str              # "YYYY-MM"
    end_month: str                # "YYYY-MM"
    metrics: list[str]            # DB 컬럼명 목록 (ALLOWED_METRICS 서브셋)
    chart_type: str = "line"      # "line" | "bar"

    @field_validator("identifier_type")
    @classmethod
    def check_identifier_type(cls, v: str) -> str:
        if v not in ("loan_no", "product_code", "product_code_nm", "all_products"):
            raise ValueError(f"지원하지 않는 식별자 유형: {v}")
        return v

    @field_validator("metrics")
    @classmethod
    def check_metrics(cls, v: list[str]) -> list[str]:
        invalid = [m for m in v if m not in ALLOWED_METRICS]
        if invalid:
            raise ValueError(f"지원하지 않는 메트릭: {invalid}")
        if not v:
            raise ValueError("메트릭이 하나 이상 필요합니다.")
        return v

    @model_validator(mode="after")
    def check_date_order(self) -> "DataQuerySpec":
        if self.start_month > self.end_month:
            raise ValueError("start_month는 end_month보다 앞이어야 합니다.")
        return self


# ── AI Call #1: 자연어 → DataQuerySpec ─────────────────────────────────────────

_AI_PARSE_PROMPT = """\
당신은 RWA 데이터 분석 시스템의 쿼리 파서입니다.
사용자의 자연어 요청을 아래 JSON 형식으로만 변환하세요. JSON 외 다른 텍스트는 출력하지 마세요.

## 출력 형식
{{
  "identifier_type": "loan_no" | "product_code" | "product_code_nm" | "all_products",
  "identifier_value": "string",
  "start_month": "YYYY-MM",
  "end_month": "YYYY-MM",
  "metrics": ["bs_balance", "ead", "rw", "rwa", "pd", "lgd", "ccf"],
  "chart_type": "line" | "bar"
}}

## 규칙
- identifier_type 결정 (우선순위 순):
  1. "대출번호 [숫자]" 패턴 → "loan_no"
  2. "영업상품코드 [값]" 또는 "상품코드 [값]" 패턴 (숫자 코드) → "product_code"
  3. 상품명({product_code_nm_list}) 등 한글 상품명이 언급되면 → "product_code_nm", identifier_value = 상품명
  4. "상품코드별", "상품별", "전체 상품", "모든 상품", "상품 비교", "상품들" 등 복수 상품 비교 → "all_products", identifier_value = ""
- identifier_value: 식별자 값 (숫자 또는 한글 상품명). all_products인 경우 빈 문자열 ""
- start_month / end_month: 항상 "YYYY-MM" 형식
  - "최근 N개월": end_month = "{latest_month}", start_month = end_month에서 (N-1)개월 이전
  - "YYYY-MM ~ YYYY-MM" 또는 "YYYY-MM부터 YYYY-MM까지" 형식 처리
  - "YYYYMM" 형식: YYYY-MM으로 변환
  - "YYYY.MM" 형식: YYYY-MM으로 변환
  - 단일 월 요청 시: start_month = end_month = 해당 월
- metrics: 요청된 지표만 포함. 언급 없으면 ["rwa"] 기본값
  - "잔액" → "bs_balance", "EAD" → "ead", "RW" 또는 "RW율" 또는 "평균 RW" → "rw", "RWA" → "rwa"
  - "PD" 또는 "부도율" → "pd"
  - "LGD" 또는 "부도시손실율" 또는 "손실율" → "lgd"
  - "CCF" 또는 "신용환산율" → "ccf"
- chart_type 결정:
  - "비교", "상품별", "상품코드별", "비교 분석", "비교해줘", "비교하고 싶어", "상품들" 등이 포함되면 → "bar"
  - 단일 대출번호/상품코드/상품명의 기간별 추이 조회 → "line"
  - identifier_type이 "all_products"이면 반드시 "bar"

## 사용자 요청
{query}
"""


def _parse_json_from_text(text: str) -> dict:
    """LLM 응답에서 JSON 블록 추출 (classification_agent.py 패턴 재사용)."""
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return json.loads(text)


async def ai_parse_query(query: str) -> DataQuerySpec | None:
    """
    AI Call #1: 자연어를 DataQuerySpec으로 변환.
    실패 시 None 반환 (호출자가 안내 응답 생성).
    """
    from app.core.config import get_gemini_client, get_settings
    from app.services.db_query_service import get_base_ym_list

    settings = get_settings()
    client = get_gemini_client()

    # 최신 기준월 파악 (최근 N개월 계산에 필요)
    base_ym_list = get_base_ym_list()
    latest_month = base_ym_list[0] if base_ym_list else "2025-12"

    # 영업상품코드명 목록 (LLM이 상품명 감지에 활용)
    from app.services.db_query_service import get_product_code_nm_list
    product_code_nm_list = get_product_code_nm_list()
    product_code_nm_str = ", ".join(product_code_nm_list) if product_code_nm_list else "카드론, 오토금융, 일시불, 신판할부, 현금서비스"

    prompt = _AI_PARSE_PROMPT.format(
        query=query,
        latest_month=latest_month,
        product_code_nm_list=product_code_nm_str,
    )

    raw_text = ""
    try:
        response = await client.aio.models.generate_content(
            model=settings.primary_model,
            contents=prompt,
        )
        raw_text = response.text or ""
    except Exception:
        try:
            response = await client.aio.models.generate_content(
                model=settings.fallback_model,
                contents=prompt,
            )
            raw_text = response.text or ""
        except Exception:
            return None

    try:
        raw = _parse_json_from_text(raw_text)
    except (json.JSONDecodeError, ValueError):
        return None

    # 메트릭 정규화: 사용자 표현 → DB 컬럼명
    raw_metrics: list[str] = raw.get("metrics", ["rwa"])
    normalized_metrics = _normalize_metrics(raw_metrics)
    if not normalized_metrics:
        normalized_metrics = ["rwa"]
    raw["metrics"] = normalized_metrics

    # 날짜 정규화
    raw["start_month"] = _normalize_ym(str(raw.get("start_month", "")))
    raw["end_month"] = _normalize_ym(str(raw.get("end_month", "")))

    if not raw.get("start_month") or not raw.get("end_month"):
        return None

    try:
        return DataQuerySpec(**raw)
    except Exception:
        return None


def _normalize_metrics(raw: list[str]) -> list[str]:
    """메트릭 목록을 DB 컬럼명으로 정규화하고 허용되지 않는 값 제거."""
    result = []
    for m in raw:
        key = m.lower().strip()
        col = METRIC_ALIASES.get(key)
        if col and col not in result:
            result.append(col)
    return result


def _normalize_ym(ym: str) -> str:
    """다양한 날짜 형식을 'YYYY-MM'으로 정규화."""
    ym = ym.strip()
    # YYYY-MM (이미 정규화)
    if re.match(r"^\d{4}-\d{2}$", ym):
        return ym
    # YYYYMM
    if re.match(r"^\d{6}$", ym):
        return f"{ym[:4]}-{ym[4:]}"
    # YYYY.MM
    if re.match(r"^\d{4}\.\d{2}$", ym):
        return ym.replace(".", "-")
    return ym


# ── DB 조회 ─────────────────────────────────────────────────────────────────────

def execute_query(spec: DataQuerySpec) -> list[dict]:
    """
    검증된 DataQuerySpec으로 안전하게 SQL 생성 후 DuckDB 조회.
    LLM 생성 SQL 실행 금지 — 이 함수만 SQL을 생성한다.
    """
    if not os.path.exists(CSV_PATH):
        return []

    start_int = int(spec.start_month.replace("-", ""))
    end_int = int(spec.end_month.replace("-", ""))

    if spec.identifier_type == "loan_no":
        id_col = "loan_no"
    elif spec.identifier_type == "product_code":
        id_col = "product_code"
    else:
        id_col = "product_code_nm"

    # 요청 메트릭 + 변동원인분석용 드라이버 메트릭 항상 포함
    all_metrics = list(spec.metrics)
    for dm in DRIVER_METRICS:
        if dm not in all_metrics:
            all_metrics.append(dm)

    # 요청 메트릭별 SELECT 절 생성
    # rw: rwa/ead 파생값, pd/lgd: EAD 가중평균, ccf: BS잔액 가중평균, 나머지: SUM
    select_parts = ["CAST(base_ym AS VARCHAR) AS base_ym"]
    for metric in all_metrics:
        if metric == "rw":
            select_parts.append(
                "CASE WHEN SUM(ead) > 0 THEN SUM(rwa) / SUM(ead) ELSE NULL END AS rw"
            )
        elif metric in ("pd", "lgd"):
            select_parts.append(
                f"CASE WHEN SUM(ead) > 0 THEN SUM({metric} * ead) / SUM(ead) ELSE NULL END AS {metric}"
            )
        elif metric == "ccf":
            select_parts.append(
                "CASE WHEN SUM(bs_balance) > 0 THEN SUM(ccf * bs_balance) / SUM(bs_balance) ELSE NULL END AS ccf"
            )
        else:
            select_parts.append(f"SUM({metric}) AS {metric}")

    select_clause = ", ".join(select_parts)
    # Note: read_csv_auto() does not support ? placeholders — interpolate the
    # hardcoded constant path directly (same pattern as db_query_service.py).
    sql = f"""
        SELECT {select_clause}
        FROM read_csv_auto('{CSV_PATH}')
        WHERE base_ym >= ? AND base_ym <= ?
          AND CAST({id_col} AS VARCHAR) = ?
        GROUP BY base_ym
        ORDER BY base_ym ASC
    """
    params = [start_int, end_int, spec.identifier_value]

    con = duckdb.connect()
    try:
        cursor = con.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        con.close()


# ── 요약 통계 ───────────────────────────────────────────────────────────────────

def build_summary_stats(rows: list[dict], spec: DataQuerySpec) -> dict:
    """AI Call #2에 넘길 요약 통계 생성."""
    if not rows:
        return {
            "row_count": 0,
            "start_period": spec.start_month,
            "end_period": spec.end_month,
            "metrics": {},
        }

    def _fmt_ym(raw: str) -> str:
        s = str(raw)
        return f"{s[:4]}-{s[4:]}" if len(s) == 6 else s

    stats: dict = {
        "row_count": len(rows),
        "start_period": _fmt_ym(str(rows[0]["base_ym"])),
        "end_period": _fmt_ym(str(rows[-1]["base_ym"])),
        "metrics": {},
    }

    for metric in spec.metrics:
        values = [r[metric] for r in rows if r.get(metric) is not None]
        if not values:
            stats["metrics"][metric] = {}
            continue
        stats["metrics"][metric] = {
            "first": values[0],
            "last": values[-1],
            "min": min(values),
            "max": max(values),
        }

    # 변동원인분석용 드라이버 메트릭 트렌드
    # pd/lgd: %p(포인트) 기준, bs_balance/ead: % 기준
    _PP_METRICS = {"pd", "lgd"}  # 소수 비율 → %p 비교
    driver_trends: dict = {}
    for dm in DRIVER_METRICS:
        vals = [r[dm] for r in rows if r.get(dm) is not None]
        if len(vals) < 2:
            continue
        first, last = vals[0], vals[-1]
        if dm in _PP_METRICS:
            # %p 변동 (소수값 차이를 100 곱해 %p로 변환)
            change_pp = round((last - first) * 100, 2)
            threshold = 0.05  # 0.05%p 미만은 변동없음
            if abs(change_pp) < threshold:
                trend = "변동없음"
            elif change_pp > 0:
                trend = "상승"
            else:
                trend = "하락"
            driver_trends[dm] = {
                "trend": trend,
                "first": round(first, 4),
                "last": round(last, 4),
                "change_display": f"{change_pp:+.2f}%p",
            }
        else:
            change_pct = (last - first) / first * 100 if first != 0 else 0.0
            if abs(change_pct) < 2.0:
                trend = "변동없음"
            elif change_pct > 0:
                trend = "상승"
            else:
                trend = "하락"
            driver_trends[dm] = {
                "trend": trend,
                "first": round(first, 4),
                "last": round(last, 4),
                "change_display": f"{change_pct:+.1f}%",
            }
    stats["driver_trends"] = driver_trends

    return stats


# ── 위젯 페이로드 생성 ───────────────────────────────────────────────────────────

def _fmt_base_ym(raw: str) -> str:
    """YYYYMM → YYYY-MM"""
    s = str(raw)
    return f"{s[:4]}-{s[4:]}" if len(s) == 6 else s


_TABLE_FIXED_COLS: list[str] = ["bs_balance", "ead", "rwa"]


def build_table_widget(rows: list[dict], spec: DataQuerySpec) -> dict:
    """data_table 위젯 페이로드.

    표시 컬럼: 기준월 + BS잔액·EAD·RWA 고정 + 사용자 요청 메트릭(중복 제외)
    """
    # 고정 컬럼 먼저, 그 뒤 사용자 요청 메트릭 중 고정 컬럼에 없는 것 추가
    extra = [m for m in spec.metrics if m not in _TABLE_FIXED_COLS]
    table_metrics = _TABLE_FIXED_COLS + extra

    columns = ["base_ym"] + table_metrics
    column_labels = {"base_ym": "기준월"}
    column_labels.update({m: METRIC_LABELS.get(m, m) for m in table_metrics})

    normalized_rows = []
    for r in rows:
        row: dict = {"base_ym": _fmt_base_ym(str(r.get("base_ym", "")))}
        for m in table_metrics:
            val = r.get(m)
            row[m] = round(val, 4) if val is not None else None
        normalized_rows.append(row)

    return {
        "type": "data_table",
        "title": "월별 조회 결과",
        "columns": columns,
        "columnLabels": column_labels,
        "rows": normalized_rows,
    }


def build_chart_widget(rows: list[dict], spec: DataQuerySpec) -> dict:
    """line_chart 위젯 페이로드."""
    chart_data = []
    for r in rows:
        point: dict = {"baseMonth": _fmt_base_ym(str(r.get("base_ym", "")))}
        for m in spec.metrics:
            val = r.get(m)
            point[m] = round(val, 4) if val is not None else None
        chart_data.append(point)

    y_labels = {m: METRIC_LABELS.get(m, m) for m in spec.metrics}

    return {
        "type": "line_chart",
        "title": f"기간별 {' · '.join(METRIC_LABELS.get(m, m) for m in spec.metrics)} 추이",
        "xKey": "baseMonth",
        "yKeys": spec.metrics,
        "yLabels": y_labels,
        "data": chart_data,
    }


# ── AI Call #2: 요약 통계 → 자연어 답변 스트리밍 ────────────────────────────────

_AI_ANSWER_PROMPT = """\
당신은 RWA 데이터 분석 보고서를 작성하는 AI입니다.
아래 조회 결과 요약을 바탕으로 아래 형식에 맞춰 한국어 보고서를 작성하세요.

## 입력 데이터
- 식별자: {identifier_type_label} "{identifier_value}"
- 조회 기간: {start_period} ~ {end_period} ({row_count}개월)
- 요청 지표: {metrics_label}

## 지표별 조회 결과
{metric_stats}

## 드라이버 메트릭 추이 (변동원인분석용)
{driver_stats}

---

## 출력 형식 (아래 마크다운 구조를 반드시 따르세요)

### 📊 {identifier_value} 분석 ({start_period} ~ {end_period})

**▶ RWA 추이**
- 각 요청 지표의 기간 내 흐름을 1~2문장으로 기술 (첫값 → 마지막값, 최소/최대 언급)
- bs_balance/ead/rwa는 "억 원" 단위로 정수만 표기, pd/lgd는 소수 4자리 또는 %p 표기

**▶ 변동 원인 분석**
- BS잔액, EAD, PD, LGD 각각의 변동(상승/하락/변동없음)을 드라이버 메트릭 추이 기준으로 명시
- 상승/하락 드라이버와 변동없는 드라이버를 구분하여 기술
- PD·LGD는 %p 단위로 변동 폭 언급
- 예시: "카드론의 RWA는 {start_period} 대비 {end_period} 상승하였으며, 이는 BS잔액 및 EAD 증가에 기인합니다. PD는 +0.50%p 상승하였으나 LGD는 변동이 없었습니다."

**▶ 참고**
- 상세 수치는 아래 표 및 차트를 참고하시기 바랍니다.

---

## 작성 규칙
- 수치는 제공된 데이터 기반으로만 작성 (추측 금지)
- 데이터가 없으면 해당 섹션에 "조회 결과 없음"으로 표기
- 전체 3~6 문장 이내로 간결하게 유지
"""


# bs_balance, ead, rwa는 정수 + "억 원" 표시
_AMOUNT_METRICS: frozenset[str] = frozenset({"bs_balance", "ead", "rwa"})


def _fmt_metric_value(metric: str, value) -> str:
    """메트릭 값을 표시용 문자열로 변환."""
    if value is None:
        return "-"
    if metric in _AMOUNT_METRICS:
        return f"{int(round(value)):,}억 원"
    return str(value)


async def ai_generate_answer(
    spec: DataQuerySpec, stats: dict
) -> AsyncGenerator[str, None]:
    """AI Call #2: 요약 통계를 바탕으로 최종 답변을 스트리밍 생성."""
    from app.core.config import get_gemini_client, get_settings

    settings = get_settings()
    client = get_gemini_client()

    if spec.identifier_type == "loan_no":
        id_label = "대출번호"
    elif spec.identifier_type == "product_code":
        id_label = "영업상품코드"
    else:
        id_label = "영업상품코드명"
    metrics_label = ", ".join(METRIC_LABELS.get(m, m) for m in spec.metrics)

    metric_stats_lines: list[str] = []
    for metric, s in stats.get("metrics", {}).items():
        if not s:
            metric_stats_lines.append(f"- {METRIC_LABELS.get(metric, metric)}: 데이터 없음")
            continue
        metric_stats_lines.append(
            f"- {METRIC_LABELS.get(metric, metric)}: "
            f"첫값={_fmt_metric_value(metric, s.get('first'))}, "
            f"마지막값={_fmt_metric_value(metric, s.get('last'))}, "
            f"최소={_fmt_metric_value(metric, s.get('min'))}, "
            f"최대={_fmt_metric_value(metric, s.get('max'))}"
        )

    driver_stats_lines: list[str] = []
    for dm, dt in stats.get("driver_trends", {}).items():
        label = DRIVER_METRIC_LABELS.get(dm, dm)
        driver_stats_lines.append(
            f"- {label}: {dt['trend']} "
            f"(첫값={_fmt_metric_value(dm, dt['first'])}, "
            f"마지막값={_fmt_metric_value(dm, dt['last'])}, "
            f"변동={dt['change_display']})"
        )

    prompt = _AI_ANSWER_PROMPT.format(
        identifier_type_label=id_label,
        identifier_value=spec.identifier_value,
        start_period=stats.get("start_period", spec.start_month),
        end_period=stats.get("end_period", spec.end_month),
        metrics_label=metrics_label,
        row_count=stats.get("row_count", 0),
        metric_stats="\n".join(metric_stats_lines) if metric_stats_lines else "- 없음",
        driver_stats="\n".join(driver_stats_lines) if driver_stats_lines else "- 데이터 부족 (단일 기간 조회)",
    )

    if stats.get("row_count", 0) == 0:
        yield (
            f"{id_label} `{spec.identifier_value}`에 대한 "
            f"{spec.start_month} ~ {spec.end_month} 기간의 데이터가 없습니다.\n\n"
            "식별자 값 또는 조회 기간을 확인하고 다시 시도해주세요."
        )
        return

    try:
        response = await client.aio.models.generate_content(
            model=settings.primary_model,
            contents=prompt,
        )
        yield response.text or ""
    except Exception:
        try:
            response = await client.aio.models.generate_content(
                model=settings.fallback_model,
                contents=prompt,
            )
            yield response.text or ""
        except Exception as e:
            yield f"답변 생성 중 오류가 발생했습니다: {e}"


# ── 비교 분석 (bar chart) ────────────────────────────────────────────────────────

def execute_comparison_query(spec: DataQuerySpec) -> list[dict]:
    """
    비교 분석용 쿼리 — 기간 집계 후 상품별(product_code_nm) 비교.
    spec.identifier_type == "all_products" 또는 chart_type == "bar" 일 때 호출.
    """
    if not os.path.exists(CSV_PATH):
        return []

    start_int = int(spec.start_month.replace("-", ""))
    end_int = int(spec.end_month.replace("-", ""))

    # 비교 지표 — 사용자 요청 메트릭 + rwa/bs_balance/ead 고정 포함
    comparison_fixed = ["bs_balance", "ead", "rwa"]
    all_metrics = list(spec.metrics)
    for fm in comparison_fixed:
        if fm not in all_metrics:
            all_metrics.append(fm)

    select_parts = ["CAST(product_code_nm AS VARCHAR) AS product_code_nm"]
    for metric in all_metrics:
        if metric == "rw":
            select_parts.append(
                "CASE WHEN SUM(ead) > 0 THEN SUM(rwa) / SUM(ead) ELSE NULL END AS rw"
            )
        elif metric in ("pd", "lgd"):
            select_parts.append(
                f"CASE WHEN SUM(ead) > 0 THEN SUM({metric} * ead) / SUM(ead) ELSE NULL END AS {metric}"
            )
        elif metric == "ccf":
            select_parts.append(
                "CASE WHEN SUM(bs_balance) > 0 THEN SUM(ccf * bs_balance) / SUM(bs_balance) ELSE NULL END AS ccf"
            )
        else:
            select_parts.append(f"SUM({metric}) AS {metric}")

    select_clause = ", ".join(select_parts)
    sql = f"""
        SELECT {select_clause}
        FROM read_csv_auto('{CSV_PATH}')
        WHERE base_ym >= ? AND base_ym <= ?
        GROUP BY product_code_nm
        ORDER BY rwa DESC
    """
    params = [start_int, end_int]

    con = duckdb.connect()
    try:
        cursor = con.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        con.close()


def build_comparison_stats(rows: list[dict], spec: DataQuerySpec) -> dict:
    """비교 분석용 요약 통계 (AI Call #2에 전달)."""
    if not rows:
        return {
            "row_count": 0,
            "start_period": spec.start_month,
            "end_period": spec.end_month,
            "products": [],
        }

    products = []
    for r in rows:
        product_stats: dict = {"product_code_nm": r.get("product_code_nm", "")}
        for m in spec.metrics:
            val = r.get(m)
            product_stats[m] = round(val, 4) if val is not None else None
        products.append(product_stats)

    return {
        "row_count": len(rows),
        "start_period": spec.start_month,
        "end_period": spec.end_month,
        "products": products,
    }


def build_bar_chart_widget(rows: list[dict], spec: DataQuerySpec) -> dict:
    """bar_chart 위젯 페이로드 — 상품별 비교 분석."""
    chart_data = []
    for r in rows:
        point: dict = {"product_code_nm": r.get("product_code_nm", "")}
        for m in spec.metrics:
            val = r.get(m)
            point[m] = round(val, 4) if val is not None else None
        chart_data.append(point)

    y_labels = {m: METRIC_LABELS.get(m, m) for m in spec.metrics}

    return {
        "type": "bar_chart",
        "title": (
            f"상품별 {' · '.join(METRIC_LABELS.get(m, m) for m in spec.metrics)} 비교"
            f" ({spec.start_month} ~ {spec.end_month})"
        ),
        "xKey": "product_code_nm",
        "yKeys": spec.metrics,
        "yLabels": y_labels,
        "data": chart_data,
    }


def build_comparison_table_widget(rows: list[dict], spec: DataQuerySpec) -> dict:
    """data_table 위젯 페이로드 — 비교 분석용 (행 = 상품)."""
    comparison_fixed = ["bs_balance", "ead", "rwa"]
    extra = [m for m in spec.metrics if m not in comparison_fixed]
    table_metrics = comparison_fixed + extra

    columns = ["product_code_nm"] + table_metrics
    column_labels = {"product_code_nm": "영업상품코드명"}
    column_labels.update({m: METRIC_LABELS.get(m, m) for m in table_metrics})

    normalized_rows = []
    for r in rows:
        row: dict = {"product_code_nm": r.get("product_code_nm", "")}
        for m in table_metrics:
            val = r.get(m)
            row[m] = round(val, 4) if val is not None else None
        normalized_rows.append(row)

    return {
        "type": "data_table",
        "title": f"상품별 비교 결과 ({spec.start_month} ~ {spec.end_month})",
        "columns": columns,
        "columnLabels": column_labels,
        "rows": normalized_rows,
    }


_AI_COMPARISON_ANSWER_PROMPT = """\
당신은 RWA 데이터 분석 보고서를 작성하는 AI입니다.
아래 상품별 비교 결과를 바탕으로 한국어 보고서를 작성하세요.

## 입력 데이터
- 조회 기간: {start_period} ~ {end_period}
- 비교 지표: {metrics_label}
- 상품 수: {product_count}개

## 상품별 조회 결과
{product_stats}

---

## 출력 형식 (아래 마크다운 구조를 반드시 따르세요)

### 📊 상품별 {metrics_label} 비교 ({start_period} ~ {end_period})

**▶ 주요 현황**
- 각 상품의 지표값을 간략히 비교 (최상위/최하위 상품 언급)
- bs_balance/ead/rwa는 "억 원" 단위로 정수만 표기, rw는 소수 4자리 또는 % 표기

**▶ 참고**
- 상세 수치는 아래 차트 및 표를 참고하시기 바랍니다.

---

## 작성 규칙
- 수치는 제공된 데이터 기반으로만 작성 (추측 금지)
- 데이터가 없으면 "조회 결과 없음"으로 표기
- 전체 3~5 문장 이내로 간결하게 유지
"""


async def ai_generate_comparison_answer(
    spec: DataQuerySpec, stats: dict
) -> AsyncGenerator[str, None]:
    """AI Call #2 (비교 분석): 상품별 통계를 바탕으로 자연어 답변 스트리밍."""
    from app.core.config import get_gemini_client, get_settings

    settings = get_settings()
    client = get_gemini_client()

    if stats.get("row_count", 0) == 0:
        yield (
            f"{spec.start_month} ~ {spec.end_month} 기간의 상품별 비교 데이터가 없습니다.\n\n"
            "조회 기간을 확인하고 다시 시도해주세요."
        )
        return

    metrics_label = ", ".join(METRIC_LABELS.get(m, m) for m in spec.metrics)

    product_stats_lines: list[str] = []
    for p in stats.get("products", []):
        parts = [f"상품명: {p.get('product_code_nm', '-')}"]
        for m in spec.metrics:
            val = p.get(m)
            parts.append(f"{METRIC_LABELS.get(m, m)}: {_fmt_metric_value(m, val)}")
        product_stats_lines.append("- " + " | ".join(parts))

    prompt = _AI_COMPARISON_ANSWER_PROMPT.format(
        start_period=stats.get("start_period", spec.start_month),
        end_period=stats.get("end_period", spec.end_month),
        metrics_label=metrics_label,
        product_count=stats.get("row_count", 0),
        product_stats="\n".join(product_stats_lines) if product_stats_lines else "- 없음",
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.primary_model,
            contents=prompt,
        )
        yield response.text or ""
    except Exception:
        try:
            response = await client.aio.models.generate_content(
                model=settings.fallback_model,
                contents=prompt,
            )
            yield response.text or ""
        except Exception as e:
            yield f"답변 생성 중 오류가 발생했습니다: {e}"


# ── 파싱 실패 안내 메시지 ────────────────────────────────────────────────────────

PARSE_FAILURE_GUIDANCE = """\
**AI 데이터분석** 모드에서는 대출번호, 영업상품코드, 또는 영업상품코드명(상품명)을 기반으로 기간별 데이터를 조회하고 변동 원인을 분석합니다.

예시 질문:
- "카드론의 최근 6개월 RWA 추이 보여줘"
- "오토금융 2025-01부터 2025-06까지 잔액과 RWA 분석해줘"
- "대출번호 123456의 최근 12개월 RWA 추이 보여줘"
- "영업상품코드 4679332의 2025-01부터 2025-06까지 잔액과 RWA 보여줘"
- "상품코드 1234의 LGD, CCF 추이 보여줘"

---
**지원 식별자:** 대출번호 / 영업상품코드(숫자) / 영업상품코드명 (카드론, 오토금융, 일시불, 신판할부, 현금서비스 등)
**지원 기간 표현:** 최근 N개월 / YYYY-MM ~ YYYY-MM / YYYY-MM부터 YYYY-MM까지
**지원 메트릭:** 잔액 (bs_balance), EAD, RW율, RWA, PD (부도율), LGD (부도시손실율), CCF (신용환산율)
**변동원인분석:** BS잔액, EAD, PD, LGD 변동을 기반으로 자동 분석됩니다.
"""
