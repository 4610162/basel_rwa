"""
SA 정부(Sovereign) 익스포져 RWA 계산기

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제1절 (제29조~제34조)

mermaid 다이어그램 노드 대응:
    SA_GOV_1  무위험기관         → calc_rw_zero_risk_entity()   [제30조]
    SA_GOV_2  국제개발은행        → calc_rw_mdb()                [제34조]
    SA_GOV_3  중앙정부·중앙은행   → calc_rw_gov()                [제29조]
    SA_GOV_4  정부간주공공기관    → calc_rw_pse()                [제31~33조]
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rwa.common.grade import GradeBucket, resolve_bucket
from rwa.common.types import RwaResult
from .constants import (
    BANK_RW, GOV_RW, MDB_RW,
    ZERO_RISK_ENTITIES, ZERO_RISK_ENTITY_ALIAS, ZERO_RISK_MDBS,
)


# ── 기관 유형 열거형 ──────────────────────────────────────────────────

class GovEntityType(Enum):
    """정부 익스포져 기관 유형 (SA_GOV 하위 노드 대응)"""
    CENTRAL_GOV          = "central_gov"          # SA_GOV_3: 중앙정부·중앙은행
    ZERO_RISK_ENTITY     = "zero_risk_entity"     # SA_GOV_1: 무위험기관 (제30조)
    MDB_ZERO             = "mdb_zero"             # SA_GOV_2: 0% MDB (제34조 나.)
    MDB_GENERAL          = "mdb_general"          # SA_GOV_2: 일반 MDB (제34조 가.)
    PSE_GOV_LIKE         = "pse_gov_like"         # SA_GOV_4: 정부간주공공기관 (제32조 가./제31조)
    PSE_BANK_LIKE        = "pse_bank_like"        # SA_GOV_4: 은행간주공공기관 (제32조 나.)
    PSE_HIGHER           = "pse_higher"           # SA_GOV_4: 제32조 다. (max(은행RW, 50%))
    PSE_FOREIGN          = "pse_foreign"          # SA_GOV_4: 외국 공공기관 (제33조 가.)
    PSE_FOREIGN_GOV_LIKE = "pse_foreign_gov_like" # SA_GOV_4: 외국 지방정부 정부간주 (제33조 나.)


# ── 입력 데이터 클래스 ────────────────────────────────────────────────

@dataclass
class GovExposureInput:
    """정부 익스포져 RWA 산출 입력값"""
    exposure: float                              # 익스포져 금액 (원화, 단위: 원)
    entity_type: GovEntityType                  # 기관 유형
    external_credit_rating: Optional[str] = None             # 적격외부신용등급(예: "AA-"), None=무등급
    oecd_grade: Optional[int] = None           # OECD 국가신용도등급 (0~7), None=무등급
    is_local_currency: bool = False            # 자국통화(원화/현지통화) 표시·조달 여부
    is_korea: bool = True                      # 대한민국 정부 여부 (제29조 나. 특례 판별)
    entity_name: Optional[str] = None         # 기관명 (제30조·제34조 목록 조회용)
    pse_category: Optional[str] = None        # PSE 세부 분류 (calc_rw_pse 직접 호출 시 사용)
    country_gov_external_credit_rating: Optional[str] = None  # 외국 공공기관의 해당 국가 중앙정부 적격외부신용등급


# ── 메인 산출 클래스 ─────────────────────────────────────────────────

class SovereignCalculator:
    """
    신용 RWA 표준방법(SA) — 정부(Sovereign) 익스포져 위험가중치·RWA 계산기

    적용 범위:
        SA_GOV_1  무위험기관         BIS, IMF, ECB, EU, ESM, EFSF
        SA_GOV_2  국제개발은행        일반 MDB 및 0% 우량 MDB
        SA_GOV_3  중앙정부·중앙은행   국내외 중앙정부·중앙은행
        SA_GOV_4  정부간주공공기관    국내 지자체, 국내 공공기관, 외국 공공기관
    """

    # ── SA_GOV_3: 중앙정부·중앙은행 ──────────────────────────────────

    def calc_rw_gov(
        self,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
        is_local_currency: bool = False,
        is_korea: bool = True,
    ) -> float:
        """
        [SA_GOV_3] 중앙정부·중앙은행 익스포져 위험가중치 산출
        근거: 제29조 (중앙정부 및 중앙은행 익스포져)

        특수 로직:
        - 제29조 나.: 대한민국 정부 익스포져 중 원화 기준으로 표시되고 조달된 것 → 0%
        - 제29조 다.: 외국 중앙정부 익스포져 중 현지통화 기준으로 표시되고 조달된 것
                      → 해당 국가 감독당국이 정한 값 준용 가능.
                        본 메서드는 외부 등급 기반값을 반환하며,
                        준용 여부는 호출자가 별도 판단할 것.

        Args:
            external_credit_rating:          적격외부신용등급 (예: "AA-"), None=무등급
            oecd_grade:        OECD 국가신용도등급 (0~7), None=무등급
            is_local_currency: 자국통화(원화/현지통화) 표시·조달 여부
            is_korea:          대한민국 정부 여부 (True: 제29조 나. 특례 적용 대상)

        Returns:
            위험가중치 (0.0~1.5, 예: 20% → 0.20)
        """
        # ▶ 제29조 나.: 대한민국 정부 원화표시 익스포져 특례 → 0%
        if is_korea and is_local_currency:
            return 0.00

        # ▶ 제29조 가.: 외부 신용등급 기반 위험가중치
        # (제29조 다. 준용 여부는 호출자 판단)
        bucket = resolve_bucket(external_credit_rating, oecd_grade)
        return GOV_RW[bucket]

    # ── SA_GOV_1: 무위험기관 ─────────────────────────────────────────

    def calc_rw_zero_risk_entity(self, entity_name: str) -> float:
        """
        [SA_GOV_1] 무위험기관 익스포져 위험가중치 산출
        근거: 제30조 (국제결제은행 등 익스포져)

        BIS, IMF, ECB, EU, ESM, EFSF → 0%
        목록에 없는 기관명은 ValueError 발생.

        Args:
            entity_name: 기관명 (영문 약어 또는 한글 기관명)
                         예: "BIS", "IMF", "국제결제은행"

        Returns:
            0.0 (항상 0%)
        """
        normalized = ZERO_RISK_ENTITY_ALIAS.get(entity_name.strip(),
                                                  entity_name.strip().upper())
        if normalized not in ZERO_RISK_ENTITIES:
            raise ValueError(
                f"제30조 무위험기관 목록에 없는 기관: {entity_name!r}\n"
                f"허용 기관: {sorted(ZERO_RISK_ENTITIES)}"
            )
        return 0.00  # 제30조 — 항상 0%

    # ── SA_GOV_2: 국제개발은행 ────────────────────────────────────────

    def calc_rw_mdb(
        self,
        entity_name: Optional[str] = None,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
        is_zero_risk_eligible: bool = False,
    ) -> float:
        """
        [SA_GOV_2] 국제개발은행(MDB) 익스포져 위험가중치 산출
        근거: 제34조 (국제개발은행 익스포져)

        특수 로직:
        - 제34조 나.: 다음 요건을 모두 충족하는 MDB → 0%
            (1) 채무자 신용등급 AAA
            (2) AA- 이상 중앙정부가 상당 지분 보유 또는 레버리지 없는 납입자본 우세
            (3) 충분한 납입자본금·capital call·지속 출자 약정 입증
            (4) 건전한 자본적정성 및 유동성 보유
          → 요건 충족 여부는 ZERO_RISK_MDBS 목록으로 관리.
            is_zero_risk_eligible=True 또는 entity_name이 목록에 포함된 경우 0%.
        - 그 외: 제34조 가. 등급별 위험가중치 적용

        Args:
            entity_name:           MDB 기관명 (ZERO_RISK_MDBS 목록 조회용, 선택)
            external_credit_rating:              적격외부신용등급
            oecd_grade:            OECD 국가신용도등급
            is_zero_risk_eligible: 제34조 나. 0% 요건 충족 여부를 직접 지정할 경우 True

        Returns:
            위험가중치 (0.0~1.5)
        """
        # ▶ 제34조 나.: 0% 우량 MDB 해당 여부 확인
        if is_zero_risk_eligible:
            return 0.00
        if entity_name is not None and entity_name.strip() in ZERO_RISK_MDBS:
            return 0.00

        # ▶ 제34조 가.: 일반 MDB 등급별 위험가중치
        bucket = resolve_bucket(external_credit_rating, oecd_grade)
        return MDB_RW[bucket]

    # ── SA_GOV_4: 공공기관(PSE) ───────────────────────────────────────

    def calc_rw_pse(
        self,
        pse_category: str,
        external_credit_rating: Optional[str] = None,
        oecd_grade: Optional[int] = None,
        country_gov_external_credit_rating: Optional[str] = None,
    ) -> float:
        """
        [SA_GOV_4] 공공기관(PSE) 익스포져 위험가중치 산출
        근거:
            제31조 (국내 지방자치단체 익스포져)
            제32조 (국내 공공기관 익스포져)
            제33조 (외국 공공기관 익스포져)

        pse_category 분류 체계:
        ┌──────────────────────┬──────────────────────────────────────────────────┐
        │ 코드                 │ 설명 및 적용 RW                                  │
        ├──────────────────────┼──────────────────────────────────────────────────┤
        │ local_gov_krw        │ 국내 지자체, 원화 표시·조달 → 0%  [제31조 가.]   │
        │ local_gov_other      │ 국내 지자체, 원화 외 → 정부 RW   [제31조 나.]    │
        │ pse_type1            │ 결손보전 가능 공공기관 → 정부 RW  [제32조 가.]    │
        │                      │ (신보·기보·수출보험·예보 등 포함)                 │
        │ pse_type2            │ 공공기관운영법·정부출자 50%↑ 등 → 은행 RW        │
        │                      │                                   [제32조 나.]    │
        │ pse_type3            │ 업무감독+재정지원 기관             [제32조 다.]    │
        │                      │ → max(은행 RW, 50%)                              │
        │ foreign_pse          │ 외국 공공기관 → 해당국 정부 등급 기준 은행 RW     │
        │                      │                                   [제33조 가.]    │
        │ foreign_local_gov_like│ 외국 지방정부 정부간주             [제33조 나.]  │
        │                      │ → 해당국 정부 등급 기준 정부 RW                  │
        └──────────────────────┴──────────────────────────────────────────────────┘

        Args:
            pse_category:         공공기관 분류 코드 (위 표 참조)
            external_credit_rating:             적격외부신용등급
                                  (국내 공공기관의 경우 대한민국 정부 등급)
            oecd_grade:           OECD 국가신용도등급
            country_gov_external_credit_rating: 외국 공공기관의 해당 국가 중앙정부 적격외부신용등급

        Returns:
            위험가중치 (0.0~1.5)
        """
        cat = pse_category.strip().lower()

        # ── 제31조: 국내 지방자치단체 ──────────────────────────────
        if cat == "local_gov_krw":
            # 제31조 가.: 원화 표시·조달 → 0%
            return 0.00

        if cat == "local_gov_other":
            # 제31조 나.: 대한민국 정부 신용등급 기준 제29조 RW
            return GOV_RW[resolve_bucket(external_credit_rating, oecd_grade)]

        # ── 제32조: 국내 공공기관 ───────────────────────────────────
        if cat == "pse_type1":
            # 제32조 가.: 결손발생 시 정부 제도적 결손보전 가능 기관
            #   예: 신용보증기금, 기술신용보증기금, 수출보험공사, 예금보험공사 등
            # → 대한민국 정부 신용등급 기준 제29조 RW
            return GOV_RW[resolve_bucket(external_credit_rating, oecd_grade)]

        if cat == "pse_type2":
            # 제32조 나.: 공공기관운영법 4조1항1~3호, 정부출자 50% 이상 특수공공법인,
            #             지방공기업, 정부결손보전 단위조합 등
            # → 대한민국 정부 신용등급 기준 제35조(은행) RW
            # 무등급 시 보수적으로 150% 적용
            return BANK_RW.get(resolve_bucket(external_credit_rating, oecd_grade), 1.50)

        if cat == "pse_type3":
            # 제32조 다.: 업무감독 + 재정·세제지원 받는 특수공공법인,
            #             정부·예금보험공사 출자 50% 이상 보증보험사 등
            # → max(제35조 은행 RW, 50%)
            bank_rw = BANK_RW.get(resolve_bucket(external_credit_rating, oecd_grade), 1.50)
            return max(bank_rw, 0.50)

        # ── 제33조: 외국 공공기관 ───────────────────────────────────
        if cat == "foreign_local_gov_like":
            # 제33조 나.: 외국 지방정부 중 조세징수 능력 + 중앙정부 결손보전
            # → 해당국 중앙정부 등급 기준 제29조 RW
            if country_gov_external_credit_rating is None and oecd_grade is None:
                raise ValueError(
                    "foreign_local_gov_like: "
                    "해당 국가 중앙정부 등급(country_gov_external_credit_rating 또는 oecd_grade)이 필요합니다."
                )
            return GOV_RW[resolve_bucket(country_gov_external_credit_rating, oecd_grade)]

        if cat == "foreign_pse":
            # 제33조 가.: 외국 지방정부 및 공공기관
            # → 해당국 중앙정부 등급 기준 제35조(은행) RW
            if country_gov_external_credit_rating is None and oecd_grade is None:
                raise ValueError(
                    "foreign_pse: "
                    "해당 국가 중앙정부 등급(country_gov_external_credit_rating 또는 oecd_grade)이 필요합니다."
                )
            return BANK_RW.get(resolve_bucket(country_gov_external_credit_rating, oecd_grade), 1.50)

        raise ValueError(
            f"알 수 없는 pse_category: {pse_category!r}\n"
            "허용값: local_gov_krw | local_gov_other | pse_type1 | pse_type2 | "
            "pse_type3 | foreign_pse | foreign_local_gov_like"
        )

    # ── 통합 진입점 ───────────────────────────────────────────────────

    def calc_rwa(self, inp: GovExposureInput) -> RwaResult:
        """
        GovExposureInput을 받아 RW와 RWA를 산출하는 통합 진입점.
        entity_type에 따라 각 calc_rw_*() 메서드를 호출한다.

        Args:
            inp: GovExposureInput 데이터클래스

        Returns:
            RwaResult — entity_type, risk_weight, rwa, basis 포함
        """
        etype = inp.entity_type
        dispatch: dict = {
            GovEntityType.ZERO_RISK_ENTITY: self._handle_zero_risk_entity,
            GovEntityType.MDB_ZERO:         self._handle_mdb_zero,
            GovEntityType.MDB_GENERAL:      self._handle_mdb_general,
            GovEntityType.CENTRAL_GOV:      self._handle_central_gov,
            GovEntityType.PSE_GOV_LIKE:     self._handle_pse_gov_like,
            GovEntityType.PSE_BANK_LIKE:    self._handle_pse_bank_like,
            GovEntityType.PSE_HIGHER:       self._handle_pse_higher,
            GovEntityType.PSE_FOREIGN:      self._handle_pse_foreign,
            GovEntityType.PSE_FOREIGN_GOV_LIKE: self._handle_pse_foreign_gov_like,
        }
        handler = dispatch.get(etype)
        if handler is None:
            raise ValueError(f"처리되지 않은 GovEntityType: {etype}")
        rw, basis = handler(inp)
        return RwaResult(
            entity_type=etype.value,
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=basis,
        )

    # ── 내부 핸들러 ───────────────────────────────────────────────────

    def _handle_zero_risk_entity(self, inp: GovExposureInput) -> tuple[float, str]:
        return self.calc_rw_zero_risk_entity(inp.entity_name or ""), "제30조"

    def _handle_mdb_zero(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_mdb(
            entity_name=inp.entity_name,
            external_credit_rating=inp.external_credit_rating,
            oecd_grade=inp.oecd_grade,
            is_zero_risk_eligible=True,
        )
        return rw, "제34조 나."

    def _handle_mdb_general(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_mdb(
            entity_name=inp.entity_name,
            external_credit_rating=inp.external_credit_rating,
            oecd_grade=inp.oecd_grade,
            is_zero_risk_eligible=False,
        )
        return rw, "제34조 가."

    def _handle_central_gov(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_gov(
            external_credit_rating=inp.external_credit_rating,
            oecd_grade=inp.oecd_grade,
            is_local_currency=inp.is_local_currency,
            is_korea=inp.is_korea,
        )
        return rw, "제29조"

    def _handle_pse_gov_like(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_pse("pse_type1", inp.external_credit_rating, inp.oecd_grade)
        return rw, "제32조 가. (정부간주공공기관)"

    def _handle_pse_bank_like(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_pse("pse_type2", inp.external_credit_rating, inp.oecd_grade)
        return rw, "제32조 나. (은행간주공공기관)"

    def _handle_pse_higher(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_pse("pse_type3", inp.external_credit_rating, inp.oecd_grade)
        return rw, "제32조 다. (max(은행RW, 50%))"

    def _handle_pse_foreign(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_pse(
            "foreign_pse", inp.external_credit_rating, inp.oecd_grade,
            country_gov_external_credit_rating=inp.country_gov_external_credit_rating,
        )
        return rw, "제33조 가. (외국 공공기관)"

    def _handle_pse_foreign_gov_like(self, inp: GovExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_pse(
            "foreign_local_gov_like", inp.external_credit_rating, inp.oecd_grade,
            country_gov_external_credit_rating=inp.country_gov_external_credit_rating,
        )
        return rw, "제33조 나. (외국 지방정부 정부간주)"
