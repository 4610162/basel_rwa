"""
익스포져 유형별 입력 스키마 정의

챗봇의 RWA 계산 안내 체크리스트 생성을 위한 단일 소스.
계산기 폼(exposureConfig.ts)과는 독립적으로 관리한다.

사용 방법:
    from app.services.exposure_schema import EXPOSURE_SCHEMAS, ExposureSchema
    schema = EXPOSURE_SCHEMAS["corporate"]
    # schema.required_fields, schema.optional_fields, schema.conditional_fields 참조

지원 유형:
    corporate, bank, sovereign, retail, real_estate, equity, ciu

이후 확장:
    - 새 익스포져 유형 추가 → EXPOSURE_SCHEMAS에 ExposureSchema 항목 추가
    - 프론트엔드 재사용 → /api/exposure-schemas 엔드포인트로 노출 가능
    - 계산기 연결 → category_id / field name이 exposureConfig.ts의 id / name과 매핑
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field


# ── 타입 정의 ─────────────────────────────────────────────────────────────────

@dataclass
class FieldSchema:
    """
    단일 입력 필드 스키마.

    name      : API 파라미터명 — exposureConfig.ts의 FieldConfig.name과 일치
    label     : 한국어 표시명
    hint      : 예시값 또는 보충 설명
    options   : 선택형 필드의 선택지 목록. 비어있으면 자유 입력
    """
    name: str
    label: str
    hint: str = ""
    options: list[str] = dc_field(default_factory=list)


@dataclass
class ConditionalFieldSchema:
    """
    조건부로 표시되는 입력 필드 스키마.

    condition : 이 필드가 필요해지는 조건을 사람이 읽을 수 있는 문자열로 기술
                예: "entity_type = IPRE 또는 HVCRE 선택 시"
    """
    name: str
    label: str
    hint: str = ""
    options: list[str] = dc_field(default_factory=list)
    condition: str = ""


@dataclass
class ExposureSchema:
    """
    익스포져 유형별 입력 스키마.

    id              : 내부 식별자. EXPOSURE_SCHEMAS dict의 key와 동일
    label           : 한국어 표시명 (예: "기업 익스포져")
    category_id     : exposureConfig.ts CategoryConfig.id와 매핑 (미래 계산기 연결용)
                      retail / sovereign은 계산기 미구현 상태이므로 None
    description     : 적용 규정 조문 요약 (1~2줄)
    required_fields : 반드시 입력해야 하는 필드 목록
    optional_fields : 있으면 더 정확한 계산이 가능한 선택 필드
    conditional_fields: 특정 선택에 따라 추가로 필요해지는 필드
    """
    id: str
    label: str
    category_id: str | None
    description: str
    required_fields: list[FieldSchema]
    optional_fields: list[FieldSchema] = dc_field(default_factory=list)
    conditional_fields: list[ConditionalFieldSchema] = dc_field(default_factory=list)


# ── 공통 옵션 상수 ────────────────────────────────────────────────────────────

_CREDIT_RATING_OPTIONS = [
    "AAA", "AA+", "AA", "AA-",
    "A+", "A", "A-",
    "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-",
    "B+", "B", "B-",
    "CCC이하", "무등급",
]

_OECD_GRADE_OPTIONS = ["0", "1", "2", "3", "4", "5", "6", "7"]

_DD_GRADE_OPTIONS = [
    "A등급 (완충자본 포함 최소 규제자본 충족)",
    "B등급 (완충자본 미포함 최소 규제자본 충족)",
    "C등급 (B등급 요건 미충족)",
]


# ── 익스포져 스키마 정의 ──────────────────────────────────────────────────────

EXPOSURE_SCHEMAS: dict[str, ExposureSchema] = {

    # ── 1. 기업 익스포져 (Corporate) ─────────────────────────────────────────
    "corporate": ExposureSchema(
        id="corporate",
        label="기업 익스포져",
        category_id="corp",
        description="[별표 3] 제37조~제38조의2 — 표준방법(SA) 20%~150%",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 100억원 / 10,000,000,000",
            ),
            FieldSchema(
                name="entity_type",
                label="차주 구분",
                hint="일반법인, 중소기업(SME), 특수목적금융 유형 선택",
                options=[
                    "일반법인",
                    "중소기업(SME)",
                    "특수목적금융-PF (프로젝트금융)",
                    "특수목적금융-OF (오브젝트금융)",
                    "특수목적금융-CF (상품금융)",
                    "IPRE (수익창출 부동산금융)",
                    "HVCRE (고변동성 상업용부동산)",
                ],
            ),
            FieldSchema(
                name="external_credit_rating",
                label="외부신용등급",
                hint="없으면 '무등급' 선택",
                options=_CREDIT_RATING_OPTIONS,
            ),
        ],
        optional_fields=[
            FieldSchema(
                name="is_sme_legal",
                label="중소기업기본법상 중소기업 해당 여부",
                hint="해당 시 무등급 기업에 85% 우대 적용",
                options=["해당", "미해당"],
            ),
            FieldSchema(
                name="is_delinquent",
                label="연체 여부",
                options=["없음", "있음 (90일 초과)"],
            ),
            FieldSchema(
                name="is_short_term",
                label="단기 익스포져 여부",
                hint="만기 90일 이하인 경우",
                options=["아니오", "예 (90일 이하)"],
            ),
        ],
        conditional_fields=[
            ConditionalFieldSchema(
                name="slotting_grade",
                label="슬롯팅 등급",
                hint="",
                options=["우량(Strong)", "양호(Good)", "보통(Satisfactory)", "취약(Weak)", "부도(Default)"],
                condition="entity_type = IPRE 또는 HVCRE 선택 시",
            ),
            ConditionalFieldSchema(
                name="pf_stage",
                label="PF 운영 단계",
                hint="무등급 PF에만 적용",
                options=["운영전(Pre-operational) 130%", "운영중(Operational) 100%", "우량운영(High Quality) 80%"],
                condition="entity_type = 특수목적금융-PF이고 외부등급 = 무등급 시",
            ),
        ],
    ),

    # ── 2. 은행 익스포져 (Bank) ───────────────────────────────────────────────
    "bank": ExposureSchema(
        id="bank",
        label="은행 익스포져",
        category_id="bank",
        description="[별표 3] 제35조~제36조 — 실사등급(DD) 또는 외부등급 기반 40%~150%",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 50억원 / 5,000,000,000",
            ),
            FieldSchema(
                name="entity_subtype",
                label="세부 유형",
                options=[
                    "일반 (외부등급 보유)",
                    "일반 (무등급 — 실사등급 적용)",
                    "커버드본드 (외부등급 보유)",
                    "커버드본드 (무등급)",
                    "단기원화 (만기 3개월 이내)",
                    "증권사·기타금융회사",
                ],
            ),
        ],
        optional_fields=[
            FieldSchema(
                name="external_credit_rating",
                label="외부신용등급",
                hint="외부등급 보유 시 입력",
                options=_CREDIT_RATING_OPTIONS,
            ),
            FieldSchema(
                name="dd_grade",
                label="실사등급 (DD Grade)",
                hint="무등급 은행에 대한 자체 실사 결과",
                options=_DD_GRADE_OPTIONS,
            ),
            FieldSchema(
                name="is_foreign_currency",
                label="외화 익스포져 여부",
                options=["원화", "외화"],
            ),
        ],
        conditional_fields=[
            ConditionalFieldSchema(
                name="country_gov_external_credit_rating",
                label="설립국 중앙정부 신용등급",
                hint="외화 익스포져 시 설립국 하한 적용을 위해 필요",
                options=_CREDIT_RATING_OPTIONS,
                condition="is_foreign_currency = 외화 선택 시",
            ),
            ConditionalFieldSchema(
                name="issuing_bank_rw",
                label="발행은행 위험가중치 (%)",
                hint="커버드본드(무등급) 시 발행은행 RW 기준으로 산출",
                options=["20%", "30%", "40%", "50%", "75%", "100%", "150%"],
                condition="세부유형 = 커버드본드(무등급) 선택 시",
            ),
        ],
    ),

    # ── 3. 정부·공공기관 익스포져 (Sovereign) ────────────────────────────────
    "sovereign": ExposureSchema(
        id="sovereign",
        label="정부·공공기관 익스포져",
        category_id="gov",
        description="[별표 3] 제29조~제34조 — 중앙정부 0%~150%, PSE·MDB 유형별 상이",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 200억원 / 20,000,000,000",
            ),
            FieldSchema(
                name="entity_subtype",
                label="기관 유형",
                options=[
                    "국내 중앙정부·중앙은행 (한국)",
                    "외국 중앙정부·중앙은행",
                    "무위험기관 (BIS, IMF, ECB, EU, ESM, EFSF)",
                    "국내 공공기관 — 정부간주 (신보, 기보 등)",
                    "국내 공공기관 — 은행간주 (정부출자 50% 이상)",
                    "국내 공공기관 — 업무감독+재정지원",
                    "외국 지방정부·공공기관",
                    "우량 국제개발은행 (World Bank, IFC 등, 0%)",
                    "일반 국제개발은행 (등급 기반)",
                ],
            ),
        ],
        optional_fields=[
            FieldSchema(
                name="is_local_currency",
                label="자국통화(원화/현지통화) 표시·조달 여부",
                hint="국내 중앙정부 선택 시: 원화 표시·조달이면 0% 적용",
                options=["예 (자국통화)", "아니오 (외화)"],
            ),
            FieldSchema(
                name="external_credit_rating",
                label="해당 국가/기관 외부신용등급",
                hint="외국 정부·공공기관·MDB에 적용",
                options=_CREDIT_RATING_OPTIONS,
            ),
            FieldSchema(
                name="oecd_grade",
                label="OECD 국가신용도등급",
                hint="해당 국가의 OECD 등급 (외부등급 대비 우선 적용 불가)",
                options=_OECD_GRADE_OPTIONS,
            ),
        ],
        conditional_fields=[
            ConditionalFieldSchema(
                name="country_gov_external_credit_rating",
                label="해당 국가 중앙정부 신용등급",
                hint="외국 공공기관의 위험가중치 결정 기준",
                options=_CREDIT_RATING_OPTIONS,
                condition="기관유형 = 외국 지방정부·공공기관 선택 시",
            ),
        ],
    ),

    # ── 4. 소매 익스포져 (Retail) ─────────────────────────────────────────────
    "retail": ExposureSchema(
        id="retail",
        label="소매 익스포져",
        category_id=None,   # 현재 계산기 미구현 — 추후 연결 시 category_id 지정
        description="[별표 3] 제39조 — 적격 소매: 75%, 비적격: 차주 기준 RW",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 5억원 / 500,000,000",
            ),
            FieldSchema(
                name="borrower_type",
                label="차주 구분",
                options=["개인", "소기업 (총 익스포져 ≤ 0.2%, ≤ 10억원)"],
            ),
            FieldSchema(
                name="product_type",
                label="상품 유형",
                options=[
                    "회전신용 (신용카드, 한도대출 등)",
                    "개인용 기한부대출",
                    "소기업 대출",
                    "기타 소매",
                ],
            ),
        ],
        optional_fields=[
            FieldSchema(
                name="is_delinquent",
                label="연체 여부",
                hint="연체 시 위험가중치 상향 가능",
                options=["없음", "있음 (90일 초과)"],
            ),
            FieldSchema(
                name="total_exposure_to_borrower",
                label="동일 차주 총 익스포져 (억원)",
                hint="소기업 적격 소매 판정 기준 (10억원 이하)",
            ),
        ],
        conditional_fields=[],
    ),

    # ── 5. 부동산 익스포져 (Real Estate) ─────────────────────────────────────
    "real_estate": ExposureSchema(
        id="real_estate",
        label="부동산 익스포져",
        category_id="realestate",
        description="[별표 3] 제41조~제41조의2 — LTV·유형별 20%~150%",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 200억원 / 20,000,000,000",
            ),
            FieldSchema(
                name="re_exposure_type",
                label="부동산 유형",
                options=[
                    "상업용 비IPRE (Non-IPRE CRE)",
                    "상업용 IPRE (수익창출형 CRE)",
                    "부동산개발금융 ADC",
                    "PF 조합사업비",
                ],
            ),
            FieldSchema(
                name="ltv_ratio",
                label="LTV 비율 (%)",
                hint="예: 60 (60%를 의미). 0~200 범위",
            ),
        ],
        optional_fields=[
            FieldSchema(
                name="is_eligible",
                label="적격 요건 충족 여부",
                hint="제41조 적격 요건 미충족 시 150% 적용",
                options=["충족", "미충족"],
            ),
            FieldSchema(
                name="borrower_risk_weight",
                label="차주 위험가중치 (%)",
                hint="비IPRE 상업용 부동산에서 차주 RW와 비교 적용",
                options=["20%", "50%", "75%", "85%", "100%", "150%"],
            ),
        ],
        conditional_fields=[
            ConditionalFieldSchema(
                name="has_construction_guarantee",
                label="시공사 연대보증 적용 여부",
                options=["예", "아니오"],
                condition="부동산유형 = PF 조합사업비 선택 시",
            ),
            ConditionalFieldSchema(
                name="contractor_credit_rating",
                label="시공사 외부신용등급",
                hint="연대보증 적용 시 시공사 RW 결정",
                options=_CREDIT_RATING_OPTIONS,
                condition="PF 조합사업비 + 시공사 연대보증 = 예 선택 시",
            ),
            ConditionalFieldSchema(
                name="is_residential_exception",
                label="주거용 예외 요건 충족 여부",
                hint="충족 시 ADC 위험가중치 150% → 100% 경감",
                options=["충족", "미충족"],
                condition="부동산유형 = ADC 선택 시",
            ),
        ],
    ),

    # ── 6. 주식 익스포져 (Equity) ─────────────────────────────────────────────
    "equity": ExposureSchema(
        id="equity",
        label="주식 익스포져",
        category_id="equity",
        description="[별표 3] 제38조의3 — 상장 250%, 비상장 250%, 투기성 400%",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 30억원 / 3,000,000,000",
            ),
            FieldSchema(
                name="equity_type",
                label="주식 유형",
                options=[
                    "일반 상장주식 (250%)",
                    "비상장 장기보유·출자전환 (250%)",
                    "투기적 비상장주식 / VC (400%)",
                    "정부보조 프로그램 주식 (100%)",
                    "후순위채권·기타 자본조달수단 (150%)",
                    "비금융자회사 대규모 출자 초과분 (1250%)",
                ],
            ),
        ],
        optional_fields=[],
        conditional_fields=[],
    ),

    # ── 7. CIU 익스포져 (집합투자기구) ───────────────────────────────────────
    "ciu": ExposureSchema(
        id="ciu",
        label="CIU 익스포져 (집합투자기구)",
        category_id="ciu",
        description="[별표 3] 제38조의4 — LTA/MBA/FBA 접근법 선택 적용",
        required_fields=[
            FieldSchema(
                name="exposure",
                label="익스포져 금액",
                hint="예: 50억원 / 5,000,000,000",
            ),
            FieldSchema(
                name="ciu_approach",
                label="접근법",
                options=[
                    "LTA — 투시법 (기초자산 직접 조회)",
                    "MBA — 위임기준법 (투자제한 기반)",
                    "FBA — 폴백법 (정보 없는 경우, 1250% 적용)",
                ],
            ),
        ],
        optional_fields=[
            FieldSchema(
                name="has_leverage",
                label="펀드 레버리지 여부",
                hint="레버리지 사용 시 위험가중치 조정",
                options=["없음", "있음"],
            ),
        ],
        conditional_fields=[
            ConditionalFieldSchema(
                name="weighted_avg_rw",
                label="기초자산 가중평균 위험가중치 (%)",
                hint="LTA: 각 기초자산 RW의 투자 비중 가중평균 / MBA: 위임장 기반 최대 허용 RW",
                condition="접근법 = LTA 또는 MBA 선택 시",
            ),
        ],
    ),
}


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────

def get_schema(exposure_type: str) -> ExposureSchema | None:
    """익스포져 유형 id로 스키마를 반환한다. 없으면 None."""
    return EXPOSURE_SCHEMAS.get(exposure_type)


def list_exposure_ids() -> list[str]:
    """지원하는 모든 익스포져 유형 id 목록을 반환한다."""
    return list(EXPOSURE_SCHEMAS.keys())


def build_template_string(schema: ExposureSchema) -> str:
    """
    ExposureSchema로부터 챗봇용 복붙 가능 입력 템플릿 문자열을 생성한다.

    형식:
        ```
        [<label> RWA 계산 입력값]
        [필수]
        - 필드명: (힌트 / 옵션)
        [선택]
        - 필드명: (힌트)
        [조건부]
        - 필드명 (조건): (힌트)
        ```
    """
    lines: list[str] = [f"[{schema.label} RWA 계산 입력값]", ""]

    # 필수 필드
    lines.append("■ 필수 입력")
    for f in schema.required_fields:
        option_hint = " / ".join(f.options) if f.options else f.hint
        suffix = f" ({option_hint})" if option_hint else ""
        lines.append(f"- {f.label}:{suffix}")

    # 선택 필드
    if schema.optional_fields:
        lines.append("")
        lines.append("■ 선택 입력 (더 정확한 계산을 위해)")
        for f in schema.optional_fields:
            option_hint = " / ".join(f.options) if f.options else f.hint
            suffix = f" ({option_hint})" if option_hint else ""
            lines.append(f"- {f.label}:{suffix}")

    # 조건부 필드
    if schema.conditional_fields:
        lines.append("")
        lines.append("■ 조건부 입력")
        for f in schema.conditional_fields:
            option_hint = " / ".join(f.options) if f.options else f.hint
            value_suffix = f" ({option_hint})" if option_hint else ""
            cond_suffix = f"  ← {f.condition}" if f.condition else ""
            lines.append(f"- {f.label}:{value_suffix}{cond_suffix}")

    return "```\n" + "\n".join(lines) + "\n```"
