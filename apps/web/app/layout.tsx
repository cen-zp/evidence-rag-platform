import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Evidence RAG",
  description: "基于资料提供可追溯证据的知识问答。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
