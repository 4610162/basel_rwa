"""
SA 기타(Other) 익스포져 RWA 계산기 — [미구현 stub]

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제5절 (제39조~제42조의2)

mermaid 다이어그램 노드:
    SA_OTH  기타 익스포져

포함 자산군 (예시):
    - 소매 익스포져         (제39조)
    - 주택담보대출          (제40조)
    - 상업용 부동산 담보대출 (제40조의2)
    - 연체 익스포져         (제41조)
    - 기타 자산             (제42조)
    - 이중상환청구권부 채권  (제35조의2)
"""
from __future__ import annotations


class OtherCalculator:
    """
    SA 기타 익스포져 RWA 계산기
    """

    def calc_rw_retail(self, *args, **kwargs) -> float:
        """
        소매 익스포져 위험가중치
        근거: 제39조
        """
        raise NotImplementedError("SA_OTH: 미구현 — 제39조 소매 로직 추가 필요")

    def calc_rw_residential_mortgage(self, *args, **kwargs) -> float:
        """
        주택담보대출 위험가중치
        근거: 제40조
        """
        raise NotImplementedError("SA_OTH: 미구현 — 제40조 주택담보 로직 추가 필요")

    def calc_rw_commercial_re(self, *args, **kwargs) -> float:
        """
        상업용 부동산 담보대출 위험가중치
        근거: 제40조의2
        """
        raise NotImplementedError("SA_OTH: 미구현 — 제40조의2 상업용부동산 로직 추가 필요")

    def calc_rw_past_due(self, *args, **kwargs) -> float:
        """
        연체 익스포져 위험가중치
        근거: 제41조
        """
        raise NotImplementedError("SA_OTH: 미구현 — 제41조 연체 로직 추가 필요")

    def calc_rw_other_assets(self, *args, **kwargs) -> float:
        """
        기타 자산 위험가중치
        근거: 제42조
        """
        raise NotImplementedError("SA_OTH: 미구현 — 제42조 기타자산 로직 추가 필요")
