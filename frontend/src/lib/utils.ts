import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatKRW(value: number): string {
  if (Math.abs(value) >= 1_000_000_000_000) {
    return `${(value / 1_000_000_000_000).toFixed(2)}조원`;
  }
  if (Math.abs(value) >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(2)}억원`;
  }
  if (Math.abs(value) >= 10_000) {
    return `${(value / 10_000).toFixed(1)}만원`;
  }
  return `${value.toLocaleString("ko-KR")}원`;
}

export function parseKRWInput(raw: string): number {
  // 콤마 제거 후 숫자 파싱
  return parseFloat(raw.replace(/,/g, "")) || 0;
}

export function formatRoundedNumber(value: number): string {
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

export function formatRatioPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

export function formatBaseYm(value: string): string {
  if (value.length === 6) {
    return `${value.slice(0, 4)}-${value.slice(4)}`;
  }
  return value;
}
