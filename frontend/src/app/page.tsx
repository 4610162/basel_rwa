"use client";

import { useState } from "react";
import { BarChart3, MessageSquare, Database } from "lucide-react";
import Chat from "@/components/Chat";
import Calculator from "@/components/Calculator";
import DbQuery from "@/components/DbQuery";
import { cn } from "@/lib/utils";

type ActiveTab = "calculator" | "chat" | "dbquery";

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("calculator");

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <header className="flex-none border-b border-surface-border bg-navy-800/80 backdrop-blur-sm">
        <div className="max-w-screen-2xl mx-auto px-3 py-3 sm:px-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div className="w-8 h-8 flex-none rounded-lg bg-brand-600 flex items-center justify-center">
              <span className="text-white font-bold text-sm">B3</span>
            </div>
            <div className="min-w-0">
              <h1 className="text-white font-semibold text-sm sm:text-base leading-none truncate">
                Basel III RWA Calculator
              </h1>
              <p className="hidden sm:block text-slate-400 text-xs mt-0.5">
                은행업감독업무시행세칙 [별표 3] · 신용위험 표준방법 (SA)
              </p>
            </div>
          </div>

          {/* Tab Toggle */}
          <nav className="flex-none flex items-center gap-1 bg-navy-900/60 rounded-lg p-1">
            <TabButton
              active={activeTab === "calculator"}
              onClick={() => setActiveTab("calculator")}
              icon={<BarChart3 className="w-4 h-4" />}
              label="RWA 계산기
              "
            />
            <TabButton
              active={activeTab === "chat"}
              onClick={() => setActiveTab("chat")}
              icon={<MessageSquare className="w-4 h-4" />}
              label="세칙 Q&A"
            />
            <TabButton
              active={activeTab === "dbquery"}
              onClick={() => setActiveTab("dbquery")}
              icon={<Database className="w-4 h-4" />}
              label="DB조회"
            />
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 min-h-0 overflow-hidden">
        <div className={cn("h-full", activeTab !== "calculator" && "hidden")}>
          <Calculator />
        </div>
        <div className={cn("h-full", activeTab !== "chat" && "hidden")}>
          <Chat />
        </div>
        <div className={cn("h-full", activeTab !== "dbquery" && "hidden")}>
          <DbQuery />
        </div>
      </main>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
        active
          ? "bg-brand-600 text-white shadow-sm"
          : "text-slate-400 hover:text-slate-200 hover:bg-navy-700"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
