"""
RWA 계산 입력 필드 파싱 모듈

사용자가 자유 텍스트나 체크리스트 형식으로 입력한 값을
ExposureSchema의 필드 이름에 매핑한다.

주의:
- LLM 추정 없음: 명확히 매핑되는 값만 저장
- 애매한 값은 파싱하지 않음
"""
from __future__ import annotations

import re

from app.services.exposure_schema import ExposureSchema, FieldSchema


# ── 입력 정규화 ────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """
    사용자 입력 텍스트를 비교용으로 정규화한다.

    - 소문자 변환
    - 하이픈/언더스코어/슬래시/중간점 → 공백
    - 연속 공백 → 단일 공백
    - 앞뒤 공백 제거
    """
    text = text.lower()
    text = re.sub(r"[-_/·•–—]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── 필드 레이블 별칭 사전 ──────────────────────────────────────────────────────
# 스키마의 공식 label 외에 사용자가 쓸 수 있는 대체 표현을 정의한다.
# 정규화된 소문자로 저장한다.

_FIELD_LABEL_ALIASES: dict[str, list[str]] = {
    "exposure": [
        "금액", "노출금액", "대출금액", "익스포져금액",
        "amount", "loan amount", "exposure amount",
    ],
    "external_credit_rating": [
        "외부등급", "신용등급", "등급", "외부 등급", "외부신용등급",
        "rating", "cr", "credit rating", "external rating",
    ],
    "entity_type": [
        "차주구분", "차주 구분", "차주유형", "차주 유형",
        "법인유형", "법인 유형", "borrower type", "구분",
    ],
    "entity_subtype": [
        "세부유형", "세부 유형", "기관유형", "기관 유형", "subtype",
    ],
    "ltv_ratio": [
        "ltv", "ltv비율", "ltv 비율", "담보인정비율", "loan to value",
    ],
    "is_delinquent": [
        "연체", "연체여부", "연체 여부", "delinquent", "delinquency",
    ],
    "is_short_term": [
        "단기", "단기여부", "단기 여부", "단기익스포져", "short term", "만기",
    ],
    "is_sme_legal": [
        "중소기업해당", "중소기업여부", "sme해당", "sme 해당", "중소기업기본법",
    ],
    "is_foreign_currency": [
        "외화", "통화", "currency", "외화여부", "원화여부",
    ],
    "dd_grade": [
        "실사등급", "dd등급", "dd 등급", "due diligence", "dd",
    ],
    "slotting_grade": [
        "슬롯팅", "슬롯팅등급", "slotting", "슬롯",
    ],
    "pf_stage": [
        "pf단계", "pf 단계", "운영단계", "운영 단계", "pf stage",
    ],
    "re_exposure_type": [
        "부동산유형", "부동산 유형", "담보유형", "담보 유형", "부동산종류",
    ],
    "ciu_approach": [
        "접근법", "ciu접근법", "ciu 접근법", "approach", "방법",
    ],
    "is_eligible": [
        "적격", "적격여부", "적격 여부", "eligible", "적격요건",
    ],
    "borrower_risk_weight": [
        "차주위험가중치", "차주 위험가중치", "차주rw", "차주 rw", "borrower rw",
    ],
    "has_construction_guarantee": [
        "시공사보증", "연대보증", "보증", "보증여부", "guarantee",
    ],
    "has_leverage": [
        "레버리지", "leverage",
    ],
    "weighted_avg_rw": [
        "가중평균", "가중평균위험가중치", "평균rw", "평균 rw", "weighted rw", "avg rw",
    ],
    "equity_type": [
        "주식유형", "주식 유형", "equity유형", "equity 유형", "주식종류",
    ],
    "is_local_currency": [
        "자국통화", "자국통화여부", "원화", "원화여부", "local currency", "현지통화",
    ],
    "borrower_type": [
        "차주", "차주구분", "borrower",
    ],
    "product_type": [
        "상품유형", "상품 유형", "상품종류", "product",
    ],
    "oecd_grade": [
        "oecd", "oecd등급", "oecd 등급", "국가신용도",
    ],
    "country_gov_external_credit_rating": [
        "국가등급", "중앙정부등급", "설립국등급", "설립국 등급",
    ],
    "issuing_bank_rw": [
        "발행은행rw", "발행은행 rw", "발행은행위험가중치",
    ],
    "contractor_credit_rating": [
        "시공사등급", "시공사 등급", "시공사신용등급",
    ],
    "is_residential_exception": [
        "주거용예외", "주거용 예외", "residential exception",
    ],
    "total_exposure_to_borrower": [
        "총익스포져", "총 익스포져", "차주총익스포져", "동일차주",
    ],
}


# ── 옵션 동의어 사전 ───────────────────────────────────────────────────────────
# 특정 옵션 텍스트(정규화된 소문자)에 매핑될 수 있는 추가 키워드를 정의한다.
# 형식: {정규화된_옵션_시작_키워드: [추가_매칭_키워드, ...]}

_OPTION_EXTRA_KEYWORDS: dict[str, list[str]] = {
    # 신용등급 — 무등급
    "무등급": ["없음", "없다", "없어", "unrated", "no rating", "nr", "등급없음", "등급 없음"],

    # 예/아니오 계열
    "해당": ["예", "네", "yes", "y", "있음", "맞음", "o"],
    "미해당": ["아니오", "아니", "no", "n", "없음", "x"],
    "충족": ["예", "네", "yes", "y", "적격", "ok"],
    "미충족": ["아니오", "아니", "no", "n", "비적격", "fail"],

    # 있음/없음 계열 (연체·보증·레버리지 등)
    "있음": ["예", "네", "yes", "y", "유"],
    "없음": ["아니오", "아니", "no", "n", "무"],

    # 자국통화 여부
    "예 (자국통화)": ["예", "네", "yes", "y", "자국통화", "원화", "local"],
    "아니오 (외화)": ["아니오", "no", "외화", "foreign", "외화"],

    # 원화/외화 구분
    "원화": ["국내", "krw", "kor", "domestic", "원"],
    "외화": ["해외", "foreign", "usd", "eur", "외국"],

    # 기업 entity_type
    "중소기업(sme)": ["sme", "중소", "소기업"],
    "일반법인": ["일반", "법인", "일반 법인", "general"],
    "ipre (수익창출 부동산금융)": ["ipre"],
    "hvcre (고변동성 상업용부동산)": ["hvcre"],

    # CIU 접근법
    "lta — 투시법 (기초자산 직접 조회)": ["lta", "투시법", "투시", "look through"],
    "mba — 위임기준법 (투자제한 기반)": ["mba", "위임기준법", "위임"],
    "fba — 폴백법 (정보 없는 경우, 1250% 적용)": ["fba", "폴백법", "폴백", "fallback"],

    # PF 운영 단계
    "운영전(pre-operational) 130%": ["운영전", "pre-op", "preop", "운영 전"],
    "운영중(operational) 100%": ["운영중", "operational", "운영 중"],
    "우량운영(high quality) 80%": ["우량운영", "high quality", "hq"],

    # 슬롯팅 등급
    "우량(strong)": ["우량", "strong"],
    "양호(good)": ["양호", "good"],
    "보통(satisfactory)": ["보통", "satisfactory"],
    "취약(weak)": ["취약", "weak"],
    "부도(default)": ["부도", "default", "부실"],

    # DD 등급
    "a등급 (완충자본 포함 최소 규제자본 충족)": ["a등급", "a grade"],
    "b등급 (완충자본 미포함 최소 규제자본 충족)": ["b등급", "b grade"],
    "c등급 (b등급 요건 미충족)": ["c등급", "c grade"],

    # 주식 유형
    "일반 상장주식 (250%)": ["상장주식", "상장", "listed"],
    "비상장 장기보유·출자전환 (250%)": ["비상장", "unlisted"],
    "투기적 비상장주식 / vc (400%)": ["투기", "vc", "벤처", "투기적"],

    # 부동산 유형
    "상업용 비ipre (non-ipre cre)": ["비ipre", "non-ipre", "일반상업용"],
    "상업용 ipre (수익창출형 cre)": ["ipre", "수익창출형"],
    "부동산개발금융 adc": ["adc", "개발금융"],
    "pf 조합사업비": ["pf 조합", "조합사업비"],
}


# ── 금액 파싱 ─────────────────────────────────────────────────────────────────

_UNIT_MAP = [
    (r"조", 1_000_000_000_000),
    (r"억", 100_000_000),
    (r"천만", 10_000_000),
    (r"만", 10_000),
]


def parse_korean_amount(text: str) -> int | None:
    """
    한국어 금액 표현을 정수(원 단위)로 변환한다.

    지원 형식:
        "10억" → 1,000,000,000
        "100억원" → 10,000,000,000
        "1억 5천만" → 150,000,000
        "10,000,000,000" → 10,000,000,000
    """
    cleaned = text.replace(",", "").replace(" ", "")

    total: int | None = None
    for unit_pat, multiplier in _UNIT_MAP:
        m = re.search(rf"(\d+(?:\.\d+)?){unit_pat}", cleaned)
        if m:
            val = int(float(m.group(1)) * multiplier)
            total = (total or 0) + val

    if total is None:
        # 7자리 이상 순수 숫자 (원 단위로 간주)
        m = re.search(r"\b(\d{7,})\b", cleaned)
        if m:
            total = int(m.group(1))

    return total


# ── 옵션 매칭 ─────────────────────────────────────────────────────────────────

def match_option_value(text: str, options: list[str]) -> str | None:
    """
    텍스트에서 옵션 목록 중 일치하는 값을 찾는다.

    우선순위:
    1. 옵션 전체 문자열이 텍스트에 포함 (정규화 후 비교)
    2. 옵션에서 괄호를 제거한 핵심 키워드가 텍스트에 포함 (1글자 한국어 허용)
    3. 옵션의 첫 번째 토큰(≥2자)이 텍스트에 포함
    4. _OPTION_EXTRA_KEYWORDS 동의어 매칭
    """
    text_norm = normalize_text(text)

    # 1. 정규화된 옵션 전체가 텍스트에 포함
    for opt in options:
        if normalize_text(opt) in text_norm:
            return opt

    # 2. 괄호 제거 핵심 키워드 매칭
    #    len 임계값: 순수 ASCII는 ≥2, 한글 포함 시 ≥1 허용
    for opt in options:
        core = re.sub(r"\(.*?\)", "", opt).strip()
        core_norm = normalize_text(core)
        if not core_norm:
            continue
        min_len = 1 if re.search(r"[가-힣]", core_norm) else 2
        if len(core_norm) >= min_len and core_norm in text_norm:
            return opt

    # 3. 첫 번째 토큰 매칭
    for opt in options:
        first_token = normalize_text(opt).split()[0] if normalize_text(opt).split() else ""
        if len(first_token) >= 2 and first_token in text_norm:
            return opt

    # 4. 동의어(_OPTION_EXTRA_KEYWORDS) 매칭
    for opt in options:
        opt_key = normalize_text(opt)
        # 옵션 자체가 사전의 키일 수도 있고, 핵심 키워드(괄호 제거)가 키일 수도 있음
        candidates = [opt_key]
        core_key = normalize_text(re.sub(r"\(.*?\)", "", opt).strip())
        if core_key and core_key != opt_key:
            candidates.append(core_key)

        for cand in candidates:
            extra_words = _OPTION_EXTRA_KEYWORDS.get(cand, [])
            for extra in extra_words:
                extra_norm = normalize_text(extra)
                if extra_norm and extra_norm in text_norm:
                    return opt

    return None


# ── 레이블 기반 값 추출 ────────────────────────────────────────────────────────

# 레이블 뒤에 올 수 있는 구분자 패턴
# ① ": ", "- " 등 기호 구분자
# ② 한국어 조사: 은/는/이/가/을/를/도 + 선택적 공백
_LABEL_SEP_PAT = r"\s*(?:[:\-]|은|는|이|가|을|를|도)\s*"


def _extract_labeled_value_multi(text: str, labels: list[str]) -> str | None:
    """
    텍스트에서 여러 레이블 중 하나가 구분자(기호 또는 한국어 조사) 뒤에
    값을 동반하는 패턴을 찾아 값 부분을 반환한다.

    지원 형식:
        "외부신용등급: BBB+"   (기호 구분자)
        "외부등급 - BBB+"      (대시 구분자)
        "외부등급은 BBB+"      (한국어 조사)
        "외부등급 BBB+"        (공백만)
    값은 다음 구분자(쉼표/세미콜론/줄바꿈) 또는 문자열 끝까지 포착.
    """
    for label in labels:
        label_escaped = re.escape(label)
        # 레이블 + 구분자 + 값 (조사/기호/공백)
        m = re.search(
            rf"{label_escaped}{_LABEL_SEP_PAT}(.+?)(?:[,;，。]\s*|\n|$)",
            text,
            re.IGNORECASE,
        )
        if m:
            val = m.group(1).strip()
            if val:
                return val
        # 레이블 뒤 공백만 있는 경우 (구분자 없음): 다음 한 단어까지만 포착
        # 단, 해당 단어가 3글자 이상이어야 의미 있는 값으로 간주
        m2 = re.search(
            rf"{label_escaped}\s+(\S{{3,}})",
            text,
            re.IGNORECASE,
        )
        if m2:
            return m2.group(1).strip()
    return None


# ── 메인 파싱 함수 ────────────────────────────────────────────────────────────

def parse_field_values(text: str, schema: ExposureSchema) -> dict[str, str]:
    """
    사용자 텍스트에서 ExposureSchema 필드에 해당하는 값을 파싱한다.

    반환: {field_name: parsed_value_str, ...}
    - required_fields + optional_fields 대상
    - LLM 추정 없음: 명확히 매핑되는 경우만 저장
    - 나중에 입력된 값이 이전 값을 덮어씀 (dict.update 방식)

    파싱 우선순위 (필드별):
    1. 레이블 명시: 공식 레이블 또는 별칭 + 구분자(기호·조사·공백) 형태
    2. 금액 필드(exposure): 레이블 없이도 금액 표현 자동 인식
    3. 선택형 필드: 정규화된 옵션 목록 매칭 (동의어 포함)
    """
    result: dict[str, str] = {}
    all_fields: list[FieldSchema] = list(schema.required_fields) + list(schema.optional_fields)

    # 입력 텍스트를 정규화한 버전도 준비 (레이블 없는 자유 텍스트 매칭에 사용)
    text_norm = normalize_text(text)

    for f in all_fields:
        if f.name in result:
            continue

        # ── 1. 레이블 기반 추출 (공식 레이블 + 별칭 + 유연한 구분자) ─────────
        all_labels = [f.label] + _FIELD_LABEL_ALIASES.get(f.name, [])
        labeled_val = _extract_labeled_value_multi(text, all_labels)

        if labeled_val:
            if f.name == "exposure":
                amount = parse_korean_amount(labeled_val)
                if amount is not None:
                    result["exposure"] = str(amount)
            elif f.options:
                matched = match_option_value(labeled_val, f.options)
                if matched:
                    result[f.name] = matched
            else:
                # 숫자형 필드 (ltv_ratio, weighted_avg_rw 등)
                num_m = re.search(r"(\d+(?:\.\d+)?)", labeled_val)
                if num_m:
                    result[f.name] = num_m.group(1)
                else:
                    result[f.name] = labeled_val
            continue

        # ── 2. 금액 필드: 레이블 없이도 금액 표현 인식 ─────────────────────
        if f.name == "exposure":
            amount = parse_korean_amount(text)
            if amount is not None:
                result["exposure"] = str(amount)

        # ── 3. 선택형 필드: 정규화된 텍스트로 옵션 매칭 (동의어 포함) ───────
        elif f.options:
            matched = match_option_value(text_norm, f.options)
            if matched:
                result[f.name] = matched

    return result


# ── 금액 포맷팅 헬퍼 ──────────────────────────────────────────────────────────

def format_amount(value_str: str) -> str:
    """숫자 문자열을 한국어 금액 표현으로 포맷팅한다. "1000000000" → "10억원" """
    try:
        amount = int(value_str)
    except ValueError:
        return value_str

    if amount >= 1_000_000_000_000:
        jo = amount // 1_000_000_000_000
        remainder = amount % 1_000_000_000_000
        eok = remainder // 100_000_000
        return f"{jo}조 {eok}억원" if eok else f"{jo}조원"
    elif amount >= 100_000_000:
        eok = amount // 100_000_000
        remainder = amount % 100_000_000
        man = remainder // 10_000
        return f"{eok}억 {man:,}만원" if man else f"{eok}억원"
    elif amount >= 10_000:
        man = amount // 10_000
        return f"{man:,}만원"
    else:
        return f"{amount:,}원"
