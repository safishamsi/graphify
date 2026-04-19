"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";
import { GridBackdrop } from "./GridBackdrop";
import { GlowOrbs } from "./GlowOrbs";
import { HeroGraph } from "./HeroGraph";

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden pt-28 pb-24 md:pt-32 md:pb-32">
      <GridBackdrop />
      <GlowOrbs />

      <div className="relative mx-auto max-w-6xl px-6">
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="show"
          className="mx-auto flex max-w-3xl flex-col items-center text-center"
        >
          <motion.span
            variants={fadeUp}
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-fog-300 backdrop-blur"
          >
            <Sparkles className="h-3 w-3 text-brand-mint" />
            Dependency Map OS
            <span className="h-1 w-1 rounded-full bg-brand-mint shadow-[0_0_8px_#3DF5B0]" />
            v0.4
          </motion.span>

          <motion.h1
            variants={fadeUp}
            className="mt-6 font-display text-5xl leading-[1.02] tracking-tight md:text-7xl"
          >
            <span className="block text-fog-50">Graph-native</span>
            <span className="block text-gradient-mint">blast radius</span>
            <span className="block text-fog-200">for real repos.</span>
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="mt-6 max-w-xl text-balance text-base text-fog-300 md:text-lg"
          >
            See exactly what breaks when a single file changes. Snapshot, fuse
            CI signals, and ship with org-isolated confidence.
          </motion.p>

          <motion.div
            variants={fadeUp}
            className="mt-9 flex flex-col items-center gap-3 sm:flex-row"
          >
            <Link
              href="/auth/sign-in"
              className="group relative inline-flex items-center gap-2 rounded-full bg-brand-mint px-5 py-3 text-sm font-semibold text-ink-900 shadow-glow-mint transition-transform hover:scale-[1.02]"
            >
              Open console
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/auth/sign-up"
              className="inline-flex items-center gap-2 rounded-full border border-white/[0.10] bg-white/[0.03] px-5 py-3 text-sm font-medium text-fog-100 backdrop-blur transition-colors hover:border-white/[0.20] hover:bg-white/[0.06]"
            >
              Create account
            </Link>
          </motion.div>

          <motion.p
            variants={fadeUp}
            className="mt-5 font-mono text-[11px] uppercase tracking-[0.2em] text-fog-500"
          >
            Supabase auth · org isolation · signed snapshots
          </motion.p>
        </motion.div>

        {/* Centerpiece graph */}
        <motion.div
          initial={{ opacity: 0, y: 32, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: 0.3, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto mt-16 max-w-5xl"
        >
          {/* Frame */}
          <div className="glass-panel relative overflow-hidden rounded-2xl border border-white/[0.08] shadow-panel">
            {/* Window chrome */}
            <div className="flex items-center justify-between border-b border-white/[0.06] bg-ink-800/60 px-4 py-2.5">
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-state-error/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-state-warning/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-state-success/80" />
              </div>
              <span className="font-mono text-[11px] text-fog-400">
                graph › blast-radius › auth/session.ts
              </span>
              <span className="font-mono text-[11px] text-fog-500">
                ●&nbsp;live
              </span>
            </div>

            <div className="relative bg-ink-700/60 p-6 md:p-10">
              <HeroGraph />
            </div>

            {/* Side stat strip */}
            <div className="grid grid-cols-2 gap-px border-t border-white/[0.06] bg-white/[0.04] sm:grid-cols-4">
              {[
                { k: "Blast radius", v: "12", hint: "modules" },
                { k: "Direct importers", v: "4", hint: "ring 1" },
                { k: "Risk score", v: "0.78", hint: "high" },
                { k: "CI overlap", v: "63%", hint: "test paths" },
              ].map((item) => (
                <div key={item.k} className="bg-ink-800/80 px-4 py-3">
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-fog-500">
                    {item.k}
                  </p>
                  <p className="mt-0.5 flex items-baseline gap-2">
                    <span className="text-lg font-semibold text-fog-50">
                      {item.v}
                    </span>
                    <span className="text-[11px] text-fog-400">{item.hint}</span>
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Floating side cards */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 1.2, duration: 0.6 }}
            className="glass-panel absolute -left-6 top-32 hidden rounded-xl border border-white/[0.08] px-3 py-2 shadow-glow-cyan lg:block"
          >
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-brand-cyan">
              SARIF
            </p>
            <p className="text-xs text-fog-200">3 diagnostics fused</p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 1.4, duration: 0.6 }}
            className="glass-panel absolute -right-4 bottom-24 hidden rounded-xl border border-white/[0.08] px-3 py-2 shadow-glow-violet lg:block"
          >
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-brand-violet">
              Post-CI
            </p>
            <p className="text-xs text-fog-200">overlap: 63%</p>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
