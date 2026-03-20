"use client";

import { useState, useRef, useEffect } from "react";

/**
 * LLM 응답에서 LaTeX 수식 형식을 정규화합니다.
 *
 * 처리 케이스:
 * 1. \begin{split}...\end{split} → \begin{aligned}...\end{aligned} (+ =& → &= 변환)
 * 2. $$ 없이 단독으로 등장하는 \begin{aligned/align/...}...\end{...} → $$...$$로 감싸기
 */
function preprocessMathContent(content: string): string {
  // 1. \begin{split} → \begin{aligned}, 정렬 기호 수정: "x =& expr" → "x &= expr"
  let result = content.replace(
    /\\begin\{split\}([\s\S]*?)\\end\{split\}/g,
    (_, body) => {
      const fixedBody = body.replace(/=\s*&\s*/g, " &= ");
      return `\\begin{aligned}${fixedBody}\\end{aligned}`;
    }
  );

  // 2. 이미 $$ 안에 있는 블록을 플레이스홀더로 보호 (이중 감싸기 방지)
  const protected_blocks: string[] = [];
  result = result.replace(/\$\$[\s\S]*?\$\$/g, (match) => {
    protected_blocks.push(match);
    return `\x00MATHBLOCK${protected_blocks.length - 1}\x00`;
  });

  // 3. $$ 없이 단독으로 등장하는 multi-line 환경을 $$ 블록으로 감싸기
  result = result.replace(
    /\\begin\{(aligned|align\*?|equation\*?|gather\*?)\}[\s\S]*?\\end\{\1\}/g,
    (match) => `\n$$\n${match}\n$$\n`
  );

  // 4. 플레이스홀더 복원
  result = result.replace(
    /\x00MATHBLOCK(\d+)\x00/g,
    (_, i) => protected_blocks[Number(i)]
  );

  // 5. 스트리밍 중 미완성 $$ 블록 자동 닫기 (홀수 개 = 열린 블록 존재)
  const ddCount = (result.match(/\$\$/g) || []).length;
  if (ddCount % 2 !== 0) {
    result += "\n$$";
  }

  return result;
}
import { Send, Loader2, BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { streamChat, SourceDoc } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceDoc[];
  streaming?: boolean;
}

const EXAMPLE_QUERIES = [
  "중앙정부 익스포져의 위험가중치 기준은?",
  "은행 실사등급(DD) A등급과 B등급의 차이는?",
  "커버드본드 적격 요건은 무엇인가요?",
  "프로젝트금융 무등급 시 위험가중치는?",
  "SME(중소기업) 익스포져 우대 기준은?",
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
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
      streaming: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      for await (const event of streamChat(query, history)) {
        if (event.type === "sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, sources: event.sources } : m
            )
          );
        } else if (event.type === "chunk") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content + event.text }
                : m
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

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={messagesRef} className="flex-1 min-h-0 overflow-y-auto px-3 py-4 sm:px-4 space-y-5 sm:space-y-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-6 pb-20">
            <div className="text-center">
              <div className="w-14 h-14 rounded-2xl bg-brand-600/20 border border-brand-600/30 flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-7 h-7 text-brand-400" />
              </div>
              <h2 className="text-xl font-semibold text-white mb-2">
                Basel III 세칙 Q&A
              </h2>
              <p className="text-slate-400 text-sm max-w-md">
                은행업감독업무시행세칙 [별표 3] 원문을 기반으로 RWA 산출 관련 질문에
                정확한 조항을 인용하여 답변합니다.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
              {EXAMPLE_QUERIES.map((q) => (
                <button
                  key={q}
                  onClick={() => handleSubmit(q)}
                  className="text-left text-sm px-4 py-3 rounded-xl bg-navy-800 border border-surface-border hover:border-brand-600/50 hover:bg-navy-700 text-slate-300 hover:text-white transition-all"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Input Area */}
      <div className="flex-none border-t border-surface-border bg-navy-800/50 px-3 py-3 sm:p-4">
        <div className="max-w-3xl mx-auto flex gap-2 sm:gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="세칙 관련 질문을 입력하세요..."
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
                  답변 생성 중...
                </div>
              )}
              {message.streaming && message.content && (
                <span className="inline-block w-1 h-4 bg-brand-400 animate-pulse ml-0.5 align-text-bottom" />
              )}
            </div>

            {/* Sources */}
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
