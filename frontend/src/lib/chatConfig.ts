import { ChatMode } from "@/types/api";

export const CHAT_MODE_OPTIONS: Array<{
  value: ChatMode;
  label: string;
  description: string;
}> = [
  {
    value: "agent",
    label: "AI 규정·계산",
    description: "규정 검색, 해석, 계산 연계, 비교 분석을 통합 지원합니다.",
  },
  {
    value: "data_analysis",
    label: "AI 데이터분석",
    description:
      "대출번호 또는 영업상품코드 기준으로 기간별 데이터를 조회하고 시각화합니다.",
  },
];

export const CHAT_MODE_STATUS: Record<ChatMode, string | undefined> = {
  agent: "질문을 분석하고 관련 규정을 찾는 중입니다...",
  data_analysis: "데이터를 조회하는 중입니다...",
};

export const CHAT_INPUT_PLACEHOLDER: Record<ChatMode, string> = {
  agent: "규정, 계산, 해석, 비교 분석 질문을 입력하세요.",
  data_analysis:
    '예: "카드론의 최근 3개월 RWA 추이 보여줘"',
};

export const CHAT_EXAMPLE_PROMPTS = [
  "외부등급 없는 기업 익스포져 위험가중치 알려줘",
  "일반 상장 주식의 위험가중치는?",
  "소매 익스포져 위험가중치 기준은?",
  "기업 익스포져 100억에 신용등급 BBB+인경우 RWA는?",
];
