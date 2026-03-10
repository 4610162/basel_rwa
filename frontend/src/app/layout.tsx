import type { Metadata, Viewport } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";

export const metadata: Metadata = {
  title: "Basel III RWA Calculator",
  description: "은행업감독업무시행세칙 기반 신용위험 RWA 산출 시스템 (표준방법, SA)",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className="dark">
      <body className="min-h-screen bg-navy-900 text-slate-200 antialiased">
        {children}
      </body>
    </html>
  );
}
