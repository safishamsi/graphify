import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "depOS — Dependency Map OS",
  description: "Architecture intelligence, blast radius, diagnostics-aware graphs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="root">{children}</body>
    </html>
  );
}
