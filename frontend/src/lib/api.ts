/**
 * FastAPI 백엔드 API 클라이언트
 * Next.js rewrites를 통해 /api/* → http://localhost:8000/api/*
 */
import {
  ChatHistoryItem,
  ChatMode,
  ChatStreamEvent,
  DbQueryRequest,
  DbQueryResponse,
  RwaRequest,
  RwaResult,
} from "@/types/api";

const BASE_URL = "/api";

export async function getBaseYmList(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/db-query/base-ym-list`);
  if (!res.ok) return [];
  return res.json();
}

export async function getProductCodeNmList(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/db-query/product-code-nm-list`);
  if (!res.ok) return [];
  return res.json();
}

export async function queryDb(req: DbQueryRequest): Promise<DbQueryResponse> {
  const res = await fetch(`${BASE_URL}/db-query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "DB 조회 오류");
  }
  return res.json();
}

// ──────────────────────────────────────────────────────────────────────────────

export async function calculateRwa(req: RwaRequest): Promise<RwaResult> {
  const res = await fetch(`${BASE_URL}/calculate/rwa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "RWA 산출 오류");
  }
  return res.json();
}

async function* streamSseJson(
  path: string,
  body: Record<string, unknown>
): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "스트리밍 연결 실패");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;
      try {
        yield JSON.parse(data);
      } catch {
        // ignore malformed JSON
      }
    }
  }
}

export async function* streamChat(
  query: string,
  history: ChatHistoryItem[] = [],
  mode: ChatMode = "agent"
): AsyncGenerator<ChatStreamEvent> {
  yield* streamSseJson("/chat/stream", { query, history, mode });
}
