"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { GitBranch } from "lucide-react";

const NAV_LINKS = [
  { label: "Product", href: "#product" },
  { label: "Pipeline", href: "#pipeline" },
  { label: "Graph", href: "#graph" },
  { label: "Docs", href: "#docs" },
];

export function MarketingNav() {
  return (
    <motion.header
      initial={{ y: -16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="sticky top-0 z-50 w-full"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-6 py-4">
        <div className="glass-panel pointer-events-auto flex w-full items-center justify-between gap-6 rounded-full border border-white/[0.06] px-4 py-2.5 shadow-panel">
          <Link href="/" className="flex items-center gap-2">
            <span className="relative grid h-7 w-7 place-items-center rounded-full bg-ink-700 ring-1 ring-brand-mint/40">
              <GitBranch className="h-3.5 w-3.5 text-brand-mint" />
              <span className="absolute inset-0 animate-pulse-glow rounded-full bg-brand-mint/20 blur-md" />
            </span>
            <span className="text-sm font-semibold tracking-tight text-fog-50">
              depOS
            </span>
            <span className="hidden text-[10px] uppercase tracking-[0.16em] text-fog-400 sm:inline">
              Dependency Map OS
            </span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="rounded-full px-3 py-1.5 text-xs font-medium text-fog-300 transition-colors hover:bg-white/[0.04] hover:text-fog-50"
              >
                {link.label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Link
              href="/auth/sign-in"
              className="hidden rounded-full px-3 py-1.5 text-xs font-medium text-fog-300 transition-colors hover:text-fog-50 sm:inline-flex"
            >
              Sign in
            </Link>
            <Link
              href="/auth/sign-up"
              className="group inline-flex items-center gap-1.5 rounded-full bg-brand-mint px-3.5 py-1.5 text-xs font-semibold text-ink-900 shadow-glow-mint transition-transform hover:scale-[1.02]"
            >
              Open console
              <span className="transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </Link>
          </div>
        </div>
      </div>
    </motion.header>
  );
}
