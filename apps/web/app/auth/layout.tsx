import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { AuthVisual } from "@/components/auth/AuthVisual";

export const metadata: Metadata = {
  title: "depOS — Auth",
  description: "Access the depOS console.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Lock dark UI to dark scrollbars / form controls in supported browsers.
  themeColor: "#0A0F14",
  colorScheme: "dark",
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-[100dvh] grid-cols-1 bg-bg-primary lg:grid-cols-[minmax(0,1fr)_minmax(480px,560px)]">
      {/* Skip-link for keyboard users — bypasses the visual + header. */}
      <a
        href="#auth-content"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:left-4 focus-visible:top-4 focus-visible:z-50 focus-visible:rounded-md focus-visible:bg-bg-elevated focus-visible:px-3 focus-visible:py-2 focus-visible:text-sm focus-visible:text-text-primary focus-visible:shadow-ring-mint"
      >
        Skip to form
      </a>

      <AuthVisual />

      <main className="relative flex min-h-[100dvh] flex-col">
        {/* Mobile-only header (the visual pane is hidden on small screens) */}
        <header className="flex items-center justify-between px-5 pt-5 sm:px-6 sm:pt-6 lg:hidden">
          <Link
            href="/"
            className="rounded font-display text-base text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            depOS
          </Link>
          <Link
            href="/"
            className="rounded font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted hover:text-text-secondary focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            ← Back
          </Link>
        </header>

        {/* Atmospheric layer for the right pane on mobile */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 grid-backdrop opacity-[0.18] mask-fade-y lg:hidden"
        />

        <div
          id="auth-content"
          className="relative flex flex-1 items-center justify-center px-4 py-8 sm:px-6 sm:py-12 lg:px-10"
        >
          {children}
        </div>

        <footer className="relative flex flex-col items-start gap-2 border-t border-edge-subtle px-5 py-4 text-[11px] text-text-muted sm:flex-row sm:items-center sm:justify-between sm:px-10">
          <span className="font-mono uppercase tracking-[0.16em]">
            depOS · graph-native
          </span>
          <div className="flex gap-4">
            <Link
              href="/"
              className="rounded hover:text-text-secondary focus-visible:shadow-ring-mint focus-visible:outline-none"
            >
              Home
            </Link>
            <a
              href="mailto:hi@depos.dev"
              className="rounded hover:text-text-secondary focus-visible:shadow-ring-mint focus-visible:outline-none"
            >
              Support
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}
