"""
SA 은행(Bank) 익스포져 RWA 계산기

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제3절 (제35조~제36조)

mermaid 다이어그램 노드 대응:
    SA_BANK_1  은행 (외부등급)           → calc_rw_bank_ext()       [제35조 가.]
    SA_BANK_1  은행 (실사등급)           → calc_rw_bank_dd()        [제35조 나.]
    SA_BANK_1  은행 (단기원화, 외부등급)  → calc_rw_bank_short_ext() [제35조 라.(1)]
    SA_BANK_1  은행 (단기원화, 실사등급)  → calc_rw_bank_short_dd()  [제35조 라.(2)]
    SA_BANK_1  커버드본드 (외부등급)      → calc_rw_covered_bond_ext()     [제35의2. 가.]
    SA_BANK_1  커버드본드 (무등급)        → calc_rw_covered_bond_unrated() [제35의2. 나.]
    SA_BANK_2  증권회사·기타금융회사      → calc_rw_securities_firm()      [제36조]
    SA_BANK_3  은행간주공공기관           → rwa/sa/gov/calculator.py 참조
    SA_BANK_4  국제개발은행 (0% 제외)     → rwa/sa/gov/calculator.py 참조
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rwa.common.grade import GradeBucket, resolve_bucket
from rwa.common.types import RwaResult
from rwa.sa.gov.constants import GOV_RW
from .constants import (
    BANK_EXT_RW,
    BANK_DD_RW,
    BANK_DD_A_HIGH_QUALITY_RW,
    BANK_SHORT_EXT_RW,
    BANK_SHORT_DD_RW,
    COVERED_BOND_EXT_RW,
    COVERED_BOND_UNRATED_RW,
)


# ── 실사 등급 열거형 ────────────────────────────────────────────────────

class DueDiligenceGrade(Enum):
    """
    제35조 나. 실사(Due Diligence) 등급
    - A등급: 최소 규제자본비율(완충자본 포함) 충족
    - B등급: 최소 규제자본비율(완충자본 제외) 충족
    - C등급: B등급 요건 미충족 또는 외부감사인 부적정 의견 등
    """
    A = "A"
    B = "B"
    C = "C"


# ── 기관 유형 열거형 ────────────────────────────────────────────────────

class BankEntityType(Enum):
    """은행 익스포져 기관·거래 유형"""
    BANK_EXT           = "bank_ext"           # SA_BANK_1: 은행, 외부신용등급 [제35조 가.]
    BANK_DD            = "bank_dd"            # SA_BANK_1: 은행, 실사등급 [제35조 나.]
    BANK_SHORT_EXT     = "bank_short_ext"     # SA_BANK_1: 단기원화, 외부신용등급 [제35조 라.(1)]
    BANK_SHORT_DD      = "bank_short_dd"      # SA_BANK_1: 단기원화, 실사등급 [제35조 라.(2)]
    COVERED_BOND_EXT   = "covered_bond_ext"   # 커버드본드, 외부신용등급 [제35의2. 가.]
    COVERED_BOND_UNRATED = "covered_bond_unrated"  # 커버드본드, 무등급 [제35의2. 나.]
    SECURITIES_FIRM    = "securities_firm"    # SA_BANK_2: 증권회사·기타금융회사 [제36조]


# ── 입력 데이터 클래스 ──────────────────────────────────────────────────

@dataclass
class BankExposureInput:
    """
    은행 익스포져 RWA 산출 입력값

    Fields:
        exposure:              익스포져 금액 (원화, 단위: 원)
        entity_type:           기관·거래 유형 (BankEntityType)
        external_credit_rating:              적격외부신용등급 (예: "AA-"), None=무등급
        oecd_grade:            OECD 국가신용도등급 (0~7), None=무등급
        dd_grade:              실사등급 ("A"/"B"/"C"), 무등급 은행에 한해 사용
        cet1_ratio:            CET1비율 (예: 0.14 = 14%), A등급 우량 판별용
        leverage_ratio:        단순기본자본비율 (예: 0.05 = 5%), A등급 우량 판별용
        is_foreign_currency:   외화 익스포져 여부 (True 시 제35조 다. 하한 적용 대상)
        is_trade_lc:           무역관련 단기 신용장거래 여부 (True 시 다. 하한 미적용)
        country_gov_external_credit_rating:  거래상대방 은행 설립국 중앙정부 적격외부신용등급 (다. 하한 산출용)
        country_gov_oecd_grade:거래상대방 은행 설립국 OECD 국가신용도등급
        issuing_bank_rw:       커버드본드 발행은행 위험가중치 (제35의2. 나. 적용 시)
        is_bank_equiv_regulated: 증권회사가 은행과 동등한 규제를 받는지 여부 (제36조)
        entity_name:           기관명 (참고용)
    """
    exposure: float
    entity_type: BankEntityType
    external_credit_rating: Optional[str] = None
    oecd_grade: Optional[int] = None
    dd_grade: Optional[str] = None             # "A", "B", "C"
    cet1_ratio: Optional[float] = None         # CET1비율 (0~1)
    leverage_ratio: Optional[float] = None     # 단순기본자본비율 (0~1)
    is_foreign_currency: bool = False          # 외화 익스포져 → 제35조 다. 하한 적용 조건
    is_trade_lc: bool = False                  # 무역 단기신용장 → 다. 하한 미적용
    country_gov_external_credit_rating: Optional[str] = None
    country_gov_oecd_grade: Optional[int] = None
    issuing_bank_rw: Optional[float] = None    # 제35의2. 나. 커버드본드 발행은행 RW
    is_bank_equiv_regulated: bool = True       # 제36조: 동등 규제 충족 여부
    entity_name: Optional[str] = None


# ── 메인 산출 클래스 ───────────────────────────────────────────────────

class BankCalculator:
    """
    신용 RWA 표준방법(SA) — 은행(Bank) 익스포져 위험가중치·RWA 계산기

    적용 범위:
        제35조 가.   은행 익스포져, 외부신용등급 기반
        제35조 나.   은행 익스포져, 실사등급 기반 (무등급)
        제35조 다.   실사등급 적용 시 설립국 위험가중치 하한
        제35조 라.   단기 원화 익스포져 우대 위험가중치
        제35의2.     커버드본드(이중상환청구권부채권) 위험가중치
        제36조       증권회사·기타금융회사 익스포져 (제35조 준용)
    """

    # ── 제35조 가.: 외부신용등급 기반 ────────────────────────────────────

    def calc_rw_bank_ext(
        self,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
    ) -> float:
        """
        [제35조 가.] 은행 익스포져 위험가중치 — 외부신용등급 기반

        적격외부신용평가기관 등급이 있는 경우에 적용한다.
        정부소유 정책은행 제외; 정부의 암묵적 지원을 반영한 등급 사용 불가.

        | 표준신용등급 | AAA~AA- | A+~A- | BBB+~BBB- | BB+~B- | B-미만 |
        |------------|---------|-------|-----------|--------|--------|
        | 위험가중치  |   20%   |  30%  |    50%    |  100%  |  150%  |

        Args:
            external_credit_rating:   적격외부신용등급 (예: "AA-")
            oecd_grade: OECD 국가신용도등급 (0~7)

        Returns:
            위험가중치 (0.0~1.5)

        Raises:
            KeyError: 무등급(UNRATED)인 경우 — 나.의 실사등급 체계 사용 필요
        """
        bucket = resolve_bucket(external_credit_rating, oecd_grade)
        rw = BANK_EXT_RW.get(bucket)
        if rw is None:
            raise ValueError(
                "제35조 가.: 무등급 은행은 외부신용등급 기반 위험가중치를 적용할 수 없습니다. "
                "실사등급(제35조 나.)을 사용하세요."
            )
        return rw

    # ── 제35조 나.·다.: 실사등급 기반 + 설립국 하한 ─────────────────────

    def calc_rw_bank_dd(
        self,
        dd_grade: str,
        cet1_ratio: Optional[float] = None,
        leverage_ratio: Optional[float] = None,
        country_gov_external_credit_rating: Optional[str] = None,
        country_gov_oecd_grade: Optional[int] = None,
        is_foreign_currency: bool = False,
        is_trade_lc: bool = False,
    ) -> float:
        """
        [제35조 나.·다.] 은행 익스포져 위험가중치 — 실사(Due Diligence) 등급 기반

        무등급 은행에 대해 거래은행이 자체 산정한 실사등급을 적용한다.

        실사등급별 위험가중치:
        | 실사등급 | A등급 | B등급 | C등급 |
        |--------|-------|-------|-------|
        | 기본   |  40%  |  75%  | 150%  |
        | A우량* |  30%  |   —   |   —   |
        * CET1비율 ≥14% 및 단순기본자본비율 ≥5% 충족 시

        [제35조 다.] 설립국 위험가중치 하한:
        - 외화 익스포져인 경우 max(실사등급RW, 설립국 중앙정부 RW) 적용
        - 단, 무역관련 단기 신용장거래는 하한 미적용

        Args:
            dd_grade:              실사등급 ("A", "B", "C")
            cet1_ratio:            CET1비율 (0.14 = 14%), A등급 우량 판별용
            leverage_ratio:        단순기본자본비율 (0.05 = 5%), A등급 우량 판별용
            country_gov_external_credit_rating:  설립국 중앙정부 적격외부신용등급 (다. 하한 산출용)
            country_gov_oecd_grade:설립국 OECD 국가신용도등급
            is_foreign_currency:   외화 익스포져 여부 (True 시 다. 하한 적용)
            is_trade_lc:           무역 단기신용장 여부 (True 시 다. 하한 미적용)

        Returns:
            위험가중치 (0.0~1.5)

        Raises:
            ValueError: 허용되지 않는 dd_grade 값
        """
        grade = dd_grade.strip().upper()
        base_rw = BANK_DD_RW.get(grade)
        if base_rw is None:
            raise ValueError(
                f"제35조 나.: 허용되지 않는 실사등급 {dd_grade!r}. "
                "허용값: 'A', 'B', 'C'"
            )

        # ▶ 제35조 나.(1) A등급 우량 은행: CET1 ≥14% + 단순기본자본비율 ≥5% → 30%
        if grade == "A":
            if (
                cet1_ratio is not None
                and leverage_ratio is not None
                and cet1_ratio >= 0.14
                and leverage_ratio >= 0.05
            ):
                base_rw = BANK_DD_A_HIGH_QUALITY_RW  # 30%

        # ▶ 제35조 다.: 외화 익스포져 시 설립국 위험가중치 하한 적용
        #   (단, 무역관련 단기 신용장거래는 하한 미적용)
        if is_foreign_currency and not is_trade_lc:
            country_rw = self._get_country_rw(country_gov_external_credit_rating, country_gov_oecd_grade)
            if country_rw is not None:
                base_rw = max(base_rw, country_rw)

        return base_rw

    # ── 제35조 라.: 단기 원화 익스포져 우대 위험가중치 ──────────────────────

    def calc_rw_bank_short_ext(
        self,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
    ) -> float:
        """
        [제35조 라.(1)] 단기 원화 익스포져 — 외부신용등급 기반 우대 위험가중치

        적용 조건:
        - 원화로 표시되고 조달된 익스포져
        - 원만기 3개월 이내, 또는 6개월 이내의 무역거래에서 발생한 익스포져
        - 채권이 계속 연장·대환되어 만기가 3개월을 초과하는 경우 제외

        | 표준신용등급 | AAA~AA- | A+~A- | BBB+~BBB- | BB+~B- | B-미만 |
        |------------|---------|-------|-----------|--------|--------|
        | 위험가중치  |   20%   |  20%  |    20%    |   50%  |  150%  |

        Args:
            external_credit_rating:   적격외부신용등급
            oecd_grade: OECD 국가신용도등급

        Returns:
            위험가중치 (0.0~1.5)

        Raises:
            ValueError: 무등급인 경우
        """
        bucket = resolve_bucket(external_credit_rating, oecd_grade)
        rw = BANK_SHORT_EXT_RW.get(bucket)
        if rw is None:
            raise ValueError(
                "제35조 라.(1): 무등급 은행은 단기 외부등급 위험가중치를 적용할 수 없습니다. "
                "실사등급(제35조 라.(2))을 사용하세요."
            )
        return rw

    def calc_rw_bank_short_dd(self, dd_grade: str) -> float:
        """
        [제35조 라.(2)] 단기 원화 익스포져 — 실사등급 기반 우대 위험가중치

        | 실사등급 | A등급 | B등급 | C등급 |
        |--------|-------|-------|-------|
        | 위험가중치 | 20% |  50%  | 150%  |

        Args:
            dd_grade: 실사등급 ("A", "B", "C")

        Returns:
            위험가중치 (0.0~1.5)

        Raises:
            ValueError: 허용되지 않는 dd_grade 값
        """
        grade = dd_grade.strip().upper()
        rw = BANK_SHORT_DD_RW.get(grade)
        if rw is None:
            raise ValueError(
                f"제35조 라.(2): 허용되지 않는 실사등급 {dd_grade!r}. "
                "허용값: 'A', 'B', 'C'"
            )
        return rw

    # ── 제35의2.: 커버드본드(이중상환청구권부채권) ─────────────────────────

    def calc_rw_covered_bond_ext(
        self,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
    ) -> float:
        """
        [제35의2. 가.] 커버드본드 위험가중치 — 외부신용등급 기반

        「이중상환청구권부 채권 발행에 관한 법률」에 따라 발행된 커버드본드에 적용.
        기초자산(커버풀)은 다음 중 하나의 적격요건을 충족해야 함:
          (1) 정부·중앙은행·공공기관·국제개발은행 직접 익스포져 또는 보증
          (2) LTV 80% 이하 주거용주택담보 대출 (40.가. 적격 요건 충족)
          (3) LTV 60% 이하 상업용부동산담보 대출 (40.가. 적격 요건 충족)
          (4) 위험가중치 30% 이하 은행 직접 익스포져 또는 보증 (발행액의 15% 이내)

        | 표준신용등급 | AAA~AA- | A+~A- | BBB+~BBB- | BB+~B- | B-미만 |
        |------------|---------|-------|-----------|--------|--------|
        | 위험가중치  |   10%   |  20%  |    20%    |   50%  |  100%  |

        Args:
            external_credit_rating:   적격외부신용등급
            oecd_grade: OECD 국가신용도등급

        Returns:
            위험가중치 (0.0~1.0)

        Raises:
            ValueError: 무등급인 경우
        """
        bucket = resolve_bucket(external_credit_rating, oecd_grade)
        rw = COVERED_BOND_EXT_RW.get(bucket)
        if rw is None:
            raise ValueError(
                "제35의2. 가.: 무등급 커버드본드는 외부등급 기반 위험가중치를 적용할 수 없습니다. "
                "발행은행 위험가중치 기반(제35의2. 나.)을 사용하세요."
            )
        return rw

    def calc_rw_covered_bond_unrated(self, issuing_bank_rw: float) -> float:
        """
        [제35의2. 나.] 커버드본드 위험가중치 — 무등급, 발행은행 위험가중치 기반

        | 발행은행 RW | 20% | 30% | 40% | 50% | 75% | 100% | 150% |
        |-----------|-----|-----|-----|-----|-----|------|------|
        | 커버드본드 RW | 10% | 15% | 20% | 25% | 35% |  50% | 100% |

        Args:
            issuing_bank_rw: 발행은행의 위험가중치 (0.20, 0.30, 0.40, 0.50, 0.75, 1.00, 1.50 중 하나)

        Returns:
            위험가중치 (0.0~1.0)

        Raises:
            ValueError: 매핑 테이블에 없는 발행은행 위험가중치
        """
        rw = COVERED_BOND_UNRATED_RW.get(issuing_bank_rw)
        if rw is None:
            raise ValueError(
                f"제35의2. 나.: 발행은행 위험가중치 {issuing_bank_rw!r}는 "
                f"커버드본드 매핑 테이블에 없습니다. "
                f"허용값: {sorted(COVERED_BOND_UNRATED_RW.keys())}"
            )
        return rw

    # ── 제36조: 증권회사·기타 금융회사 ──────────────────────────────────

    def calc_rw_securities_firm(
        self,
        is_bank_equiv_regulated: bool,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
        dd_grade: Optional[str] = None,
        cet1_ratio: Optional[float] = None,
        leverage_ratio: Optional[float] = None,
        country_gov_external_credit_rating: Optional[str] = None,
        country_gov_oecd_grade: Optional[int] = None,
        is_foreign_currency: bool = False,
        is_trade_lc: bool = False,
    ) -> tuple[float, str]:
        """
        [제36조] 증권회사·기타 금융회사 익스포져 위험가중치

        - 은행과 동등한 자기자본규제·유동성규제를 받는 경우: 제35조 준용
        - 그 외 (동등 규제 미충족): 제37조(기업 익스포져) 준용
          → 기업 익스포져는 본 모듈 범위가 아니므로 basis 문자열로 안내만 제공

        Args:
            is_bank_equiv_regulated: 은행과 동등한 수준의 규제 충족 여부
            external_credit_rating:                적격외부신용등급
            oecd_grade:              OECD 국가신용도등급
            dd_grade:                실사등급 ("A"/"B"/"C"), 무등급 시 사용
            cet1_ratio:              CET1비율 (A등급 우량 판별용)
            leverage_ratio:          단순기본자본비율 (A등급 우량 판별용)
            country_gov_external_credit_rating:    설립국 중앙정부 적격외부신용등급
            country_gov_oecd_grade:  설립국 OECD 국가신용도등급
            is_foreign_currency:     외화 익스포져 여부
            is_trade_lc:             무역 단기신용장 여부

        Returns:
            (위험가중치, 적용근거) 튜플

        Raises:
            NotImplementedError: 동등 규제 미충족 시 (제37조 기업 계산기 사용 필요)
        """
        if not is_bank_equiv_regulated:
            raise NotImplementedError(
                "제36조: 은행과 동등한 규제를 받지 않는 증권회사·금융회사는 "
                "제37조(기업 익스포져)를 준용하세요. "
                "→ rwa/sa/corp/calculator.py 의 CorporateCalculator.calc_rw_corp() 사용"
            )

        # ▶ 제36조: 제35조 준용 (동등 규제 충족 시)
        if dd_grade is not None:
            rw = self.calc_rw_bank_dd(
                dd_grade=dd_grade,
                cet1_ratio=cet1_ratio,
                leverage_ratio=leverage_ratio,
                country_gov_external_credit_rating=country_gov_external_credit_rating,
                country_gov_oecd_grade=country_gov_oecd_grade,
                is_foreign_currency=is_foreign_currency,
                is_trade_lc=is_trade_lc,
            )
            return rw, "제36조 (제35조 나.·다. 준용)"

        rw = self.calc_rw_bank_ext(external_credit_rating, oecd_grade)
        return rw, "제36조 (제35조 가. 준용)"

    # ── 통합 진입점 ────────────────────────────────────────────────────

    def calc_rwa(self, inp: BankExposureInput) -> RwaResult:
        """
        BankExposureInput을 받아 RW와 RWA를 산출하는 통합 진입점.
        entity_type에 따라 각 calc_rw_*() 메서드를 호출한다.

        Args:
            inp: BankExposureInput 데이터클래스

        Returns:
            RwaResult — entity_type, risk_weight, rwa, basis 포함
        """
        dispatch = {
            BankEntityType.BANK_EXT:            self._handle_bank_ext,
            BankEntityType.BANK_DD:             self._handle_bank_dd,
            BankEntityType.BANK_SHORT_EXT:      self._handle_bank_short_ext,
            BankEntityType.BANK_SHORT_DD:       self._handle_bank_short_dd,
            BankEntityType.COVERED_BOND_EXT:    self._handle_covered_bond_ext,
            BankEntityType.COVERED_BOND_UNRATED: self._handle_covered_bond_unrated,
            BankEntityType.SECURITIES_FIRM:     self._handle_securities_firm,
        }
        handler = dispatch.get(inp.entity_type)
        if handler is None:
            raise ValueError(f"처리되지 않은 BankEntityType: {inp.entity_type}")
        rw, basis = handler(inp)
        return RwaResult(
            entity_type=inp.entity_type.value,
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=basis,
        )

    # ── 내부 핸들러 ───────────────────────────────────────────────────

    def _handle_bank_ext(self, inp: BankExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_bank_ext(inp.external_credit_rating, inp.oecd_grade)
        return rw, "제35조 가. (외부신용등급 기반)"

    def _handle_bank_dd(self, inp: BankExposureInput) -> tuple[float, str]:
        if inp.dd_grade is None:
            raise ValueError("BankEntityType.BANK_DD: dd_grade가 필요합니다.")
        rw = self.calc_rw_bank_dd(
            dd_grade=inp.dd_grade,
            cet1_ratio=inp.cet1_ratio,
            leverage_ratio=inp.leverage_ratio,
            country_gov_external_credit_rating=inp.country_gov_external_credit_rating,
            country_gov_oecd_grade=inp.country_gov_oecd_grade,
            is_foreign_currency=inp.is_foreign_currency,
            is_trade_lc=inp.is_trade_lc,
        )
        has_floor = inp.is_foreign_currency and not inp.is_trade_lc
        basis = "제35조 나.·다. (실사등급 기반" + (", 설립국 하한 적용)" if has_floor else ")")
        return rw, basis

    def _handle_bank_short_ext(self, inp: BankExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_bank_short_ext(inp.external_credit_rating, inp.oecd_grade)
        return rw, "제35조 라.(1) (단기원화, 외부신용등급)"

    def _handle_bank_short_dd(self, inp: BankExposureInput) -> tuple[float, str]:
        if inp.dd_grade is None:
            raise ValueError("BankEntityType.BANK_SHORT_DD: dd_grade가 필요합니다.")
        rw = self.calc_rw_bank_short_dd(inp.dd_grade)
        return rw, "제35조 라.(2) (단기원화, 실사등급)"

    def _handle_covered_bond_ext(self, inp: BankExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_covered_bond_ext(inp.external_credit_rating, inp.oecd_grade)
        return rw, "제35의2. 가. (커버드본드, 외부신용등급)"

    def _handle_covered_bond_unrated(self, inp: BankExposureInput) -> tuple[float, str]:
        if inp.issuing_bank_rw is None:
            raise ValueError(
                "BankEntityType.COVERED_BOND_UNRATED: issuing_bank_rw(발행은행 위험가중치)가 필요합니다."
            )
        rw = self.calc_rw_covered_bond_unrated(inp.issuing_bank_rw)
        return rw, "제35의2. 나. (커버드본드, 발행은행RW 기반)"

    def _handle_securities_firm(self, inp: BankExposureInput) -> tuple[float, str]:
        rw, basis = self.calc_rw_securities_firm(
            is_bank_equiv_regulated=inp.is_bank_equiv_regulated,
            external_credit_rating=inp.external_credit_rating,
            oecd_grade=inp.oecd_grade,
            dd_grade=inp.dd_grade,
            cet1_ratio=inp.cet1_ratio,
            leverage_ratio=inp.leverage_ratio,
            country_gov_external_credit_rating=inp.country_gov_external_credit_rating,
            country_gov_oecd_grade=inp.country_gov_oecd_grade,
            is_foreign_currency=inp.is_foreign_currency,
            is_trade_lc=inp.is_trade_lc,
        )
        return rw, basis

    # ── 내부 유틸리티 ─────────────────────────────────────────────────

    def _get_country_rw(
        self,
        external_credit_rating: Optional[str],
        oecd_grade: Optional[int],
    ) -> Optional[float]:
        """
        제35조 다. 설립국 중앙정부 위험가중치 산출 (제29조 기준).
        등급이 없으면 None 반환 (하한 산출 불가).
        """
        if external_credit_rating is None and oecd_grade is None:
            return None
        bucket = resolve_bucket(external_credit_rating, oecd_grade)
        return GOV_RW[bucket]
