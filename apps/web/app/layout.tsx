import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Evidence RAG Platform",
  description: "An inspectable knowledge-base chat workbench.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
