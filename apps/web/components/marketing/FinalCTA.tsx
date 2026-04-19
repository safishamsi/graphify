"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

export function FinalCTA() {
  return (
    <section
      id="docs"
      className="relative scroll-mt-24 overflow-hidden px-6 py-32"
    >
      {/* radial spotlight */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 60% at 50% 50%, rgba(61,245,176,0.18) 0%, transparent 70%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 grid-backdrop opacity-30 mask-radial"
      />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto max-w-3xl text-center"
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-brand-mint">
          Ready when you are
        </p>
        <h2 className="mt-4 font-display text-5xl tracking-tight text-fog-50 md:text-6xl">
          Ship like you can{" "}
          <span className="text-gradient-mint">see the graph.</span>
        </h2>
        <p className="mx-auto mt-5 max-w-lg text-fog-400">
          Open the console, snapshot a repo, and watch blast radius render in
          seconds.
        </p>

        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/auth/sign-in"
            className="group relative inline-flex items-center gap-2 rounded-full bg-brand-mint px-6 py-3.5 text-sm font-semibold text-ink-900 shadow-glow-mint transition-transform hover:scale-[1.02]"
          >
            Open console
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link
            href="/auth/sign-up"
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.10] bg-white/[0.03] px-6 py-3.5 text-sm font-medium text-fog-100 backdrop-blur transition-colors hover:border-white/[0.20] hover:bg-white/[0.06]"
          >
            Create account
          </Link>
        </div>

        <p className="mt-8 font-mono text-[11px] uppercase tracking-[0.2em] text-fog-500">
          docs · architecture.md · product.md · README.md
        </p>
      </motion.div>
    </section>
  );
}
