import type { Metadata, Viewport } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";

export const metadata: Metadata = {
  title: "RWA AI Agent",
  description: "Basel III 신용위험 RWA 분석 · 표준방법(SA) · 은행업감독업무시행세칙",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className="dark">
      <body className="h-[100dvh] overflow-hidden bg-navy-900 text-slate-200 antialiased">
        {children}
      </body>
    </html>
  );
}
