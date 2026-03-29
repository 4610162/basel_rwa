"use client";

import { useState } from "react";
import { BookOpen, LineChart } from "lucide-react";
import { ChatMode } from "@/types/api";

const MODE_CARDS: {
  icon: React.ElementType;
  label: string;
  description: string;
  mode: ChatMode;
}[] = [
  {
    icon: BookOpen,
    label: "AI 규정·계산",
    description: "바젤3 규정 해석과 위험가중치 계산을 함께 지원합니다.",
    mode: "agent",
  },
  {
    icon: LineChart,
    label: "AI 데이터 분석",
    description: "대출번호나 상품코드 기준으로 기간별 데이터를 조회합니다.",
    mode: "data_analysis",
  },
];

const EXAMPLE_PROMPTS_BY_MODE: Record<ChatMode, string[]> = {
  agent: [
    "외부등급 없는 기업 익스포져 위험가중치 알려줘",
    "일반 상장 주식의 위험가중치는?",
    "기업 익스포져 100억에 신용등급 BBB+인경우 RWA는?",
    "부도 차주의 경우에도 보증으로 CRM 적용 가능한지",
  ],
  data_analysis: [
    "카드론의 최근 12개월 RWA 추이 보여줘",
    "영업상품코드 4147279의 BS잔액과 RWA 변동원인 분석해줘",
    "대출번호 23471046의 월별 EAD와 RWA 보여줘",
    "상품코드별 최근 6개월 평균 RW 비교해줘",
  ],
};

export default function ChatInitialScreen({
  onSubmit,
  onModeChange,
}: {
  onSubmit: (query: string) => void;
  onModeChange?: (mode: ChatMode) => void;
}) {
  const [selectedMode, setSelectedMode] = useState<ChatMode>("agent");

  function handleModeSelect(mode: ChatMode) {
    setSelectedMode(mode);
    onModeChange?.(mode);
  }

  function handleExampleSelect(prompt: string) {
    onModeChange?.(selectedMode);
    onSubmit(prompt);
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 px-4 pb-16">
      {/* Hero */}
      <div className="text-center max-w-lg">
        <div className="w-14 h-14 rounded-2xl bg-brand-600/20 border border-brand-600/30 flex items-center justify-center mx-auto mb-4">
          <span className="text-brand-400 font-bold text-xl">RA</span>
        </div>
        <h2 className="text-xl font-semibold text-white mb-2">무엇을 도와드릴까요?</h2>
        <p className="text-slate-400 text-sm max-w-sm leading-relaxed">
          원하는 모드를 선택하면, 예시 질문을 고를 수 있습니다.
        </p>
      </div>

      {/* Mode Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
        {MODE_CARDS.map(({ icon: Icon, label, description, mode }) => (
          <button
            key={label}
            onClick={() => handleModeSelect(mode)}
            className={`text-left rounded-2xl border px-4 py-4 transition-all ${
              selectedMode === mode
                ? "bg-navy-800 border-brand-600/60 shadow-[0_0_0_1px_rgba(59,130,246,0.15)]"
                : "bg-navy-800/80 border-surface-border hover:border-brand-600/40 hover:bg-navy-800"
            }`}
          >
            <div className="flex items-start gap-3">
              <div className="flex-none w-9 h-9 rounded-xl bg-brand-600/15 border border-brand-600/20 flex items-center justify-center mt-0.5">
                <Icon className="w-4.5 h-4.5 text-brand-400" />
              </div>
              <div className="min-w-0 flex-1 flex flex-col">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="text-base font-semibold text-slate-100">{label}</div>
                  {selectedMode === mode && (
                    <span className="text-[11px] px-2 py-1 rounded-full bg-brand-600/15 text-brand-300 border border-brand-600/20">
                      선택됨
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-400 leading-snug">
                  {description}
                </p>
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Example Prompts */}
      <div className="w-full max-w-2xl">
        <div className="flex items-center justify-between gap-3 mb-3">
          <p className="text-xs text-slate-500">
            선택한 모드의 예시 질문
          </p>
          <p className="text-xs text-brand-300">
            {selectedMode === "agent" ? "AI 규정·계산" : "AI 데이터 분석"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_PROMPTS_BY_MODE[selectedMode].map((q) => (
            <button
              key={q}
              onClick={() => handleExampleSelect(q)}
              className="text-xs px-3 py-1.5 rounded-full bg-navy-800 border border-surface-border text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-all"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
