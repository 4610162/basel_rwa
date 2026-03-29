"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, BookOpen, ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { streamChat } from "@/lib/api";
import {
  CHAT_INPUT_PLACEHOLDER,
  CHAT_MODE_OPTIONS,
  CHAT_MODE_STATUS,
} from "@/lib/chatConfig";
import { preprocessMathContent } from "@/lib/chatMath";
import { cn } from "@/lib/utils";
import { ChatMode, ChatRole, DataWidget, SourceDoc } from "@/types/api";
import ChatInitialScreen from "@/components/ChatInitialScreen";
import DataTable from "@/components/DataTable";
import LineChart from "@/components/LineChart";
import BarChart from "@/components/BarChart";

interface Message {
  id: string;
  role: ChatRole;
  content: string;
  status?: string;
  sources?: SourceDoc[];
  widgets?: DataWidget[];
  streaming?: boolean;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<ChatMode>("agent");
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

  async function handleSubmit(query: string = input) {
    if (!query.trim() || isLoading) return;
    setInput("");

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: query,
    };
    const assistantMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: "",
      status: CHAT_MODE_STATUS[mode],
      streaming: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      for await (const event of streamChat(query, history, mode)) {
        if (event.type === "sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? {
                    ...m,
                    sources: event.sources,
                    status: m.content
                      ? undefined
                      : "추론 결과를 바탕으로 답변을 정리하는 중입니다...",
                  }
                : m
            )
          );
        } else if (event.type === "status") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, status: event.text } : m
            )
          );
        } else if (event.type === "chunk") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content + event.text, status: undefined }
                : m
            )
          );
        } else if (event.type === "widgets") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, widgets: event.widgets } : m
            )
          );
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: `❌ 오류: ${err instanceof Error ? err.message : "알 수 없는 오류"}` }
            : m
        )
      );
    } finally {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id ? { ...m, streaming: false } : m
        )
      );
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const placeholder = CHAT_INPUT_PLACEHOLDER[mode];

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={messagesRef} className="flex-1 min-h-0 overflow-y-auto px-3 py-4 sm:px-4 space-y-5 sm:space-y-6">
        {messages.length === 0 && (
          <ChatInitialScreen onSubmit={handleSubmit} onModeChange={setMode} />
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Input Area */}
      <div className="flex-none border-t border-surface-border bg-navy-800/50 px-3 py-3 sm:p-4 pb-safe">
        <div className="max-w-3xl mx-auto space-y-2">
          {/* Mode selector */}
          <div className="flex items-center gap-2">
            {CHAT_MODE_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setMode(option.value)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium transition-all border",
                  mode === option.value
                    ? "bg-brand-600/20 border-brand-600/50 text-brand-300"
                    : "border-surface-border text-slate-500 hover:text-slate-300 hover:border-slate-500"
                )}
                title={option.description}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="flex gap-2 sm:gap-3 items-end">
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                title="대화 초기화"
                className="flex-none w-10 h-10 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center bg-navy-700 border border-surface-border hover:border-slate-500 text-slate-500 hover:text-slate-300 transition-all"
              >
                <RotateCcw className="w-4 h-4 sm:w-5 sm:h-5" />
              </button>
            )}
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              rows={1}
              className="flex-1 resize-none bg-navy-900 border border-surface-border rounded-xl px-3 py-2.5 sm:px-4 sm:py-3 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-600 transition-colors text-sm leading-relaxed min-h-[44px] max-h-32"
              style={{ height: "auto" }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = `${el.scrollHeight}px`;
              }}
            />
            <button
              onClick={() => handleSubmit()}
              disabled={!input.trim() || isLoading}
              className={cn(
                "flex-none w-10 h-10 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center transition-all",
                input.trim() && !isLoading
                  ? "bg-brand-600 hover:bg-brand-500 text-white shadow-lg"
                  : "bg-navy-700 text-slate-600 cursor-not-allowed"
              )}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin" />
              ) : (
                <Send className="w-4 h-4 sm:w-5 sm:h-5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-2 sm:gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="flex-none w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-brand-700/50 border border-brand-600/30 flex items-center justify-center text-xs font-bold text-brand-300 mt-0.5">
          B3
        </div>
      )}
      <div className={cn("min-w-0 max-w-[85%] sm:max-w-2xl", isUser ? "sm:max-w-lg" : "")}>
        {isUser ? (
          <div className="bg-brand-700/40 border border-brand-600/30 rounded-2xl rounded-tr-sm px-4 py-3 text-slate-200 text-sm">
            {message.content}
          </div>
        ) : (
          <div className="space-y-3">
            {/* Answer text bubble */}
            <div className="bg-navy-800 border border-surface-border rounded-2xl rounded-tl-sm px-5 py-4">
              {message.content ? (
                <div className="prose-chat text-sm">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm, remarkMath]}
                    rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
                  >
                    {preprocessMathContent(message.content)}
                  </ReactMarkdown>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-slate-500 text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {message.status || "답변 생성 중..."}
                </div>
              )}
              {message.streaming && message.content && (
                <span className="inline-block w-1 h-4 bg-brand-400 animate-pulse ml-0.5 align-text-bottom" />
              )}
            </div>

            {/* Data widgets (data_analysis mode) */}
            {!message.streaming && message.widgets && message.widgets.length > 0 && (
              <div className="space-y-3">
                {message.widgets.map((widget, i) => (
                  <div key={i}>
                    {widget.type === "data_table" && <DataTable widget={widget} />}
                    {widget.type === "line_chart" && <LineChart widget={widget} />}
                    {widget.type === "bar_chart" && <BarChart widget={widget} />}
                  </div>
                ))}
              </div>
            )}

            {/* Sources (agent mode) */}
            {message.sources && message.sources.length > 0 && !message.streaming && (
              <div className="text-xs">
                <button
                  onClick={() => setShowSources((v) => !v)}
                  className="flex items-center gap-1.5 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  <BookOpen className="w-3.5 h-3.5" />
                  참조 세칙 {message.sources.length}건
                  {showSources ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
                {showSources && (
                  <div className="mt-2 space-y-2">
                    {message.sources.map((src, i) => (
                      <div
                        key={i}
                        className="bg-navy-900 border border-surface-border rounded-lg px-3 py-2"
                      >
                        <div className="text-slate-500 mb-1">참조 {i + 1}</div>
                        <p className="text-slate-400 leading-relaxed line-clamp-3">
                          {src.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
