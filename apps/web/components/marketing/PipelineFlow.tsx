"use client";

import { motion } from "framer-motion";
import { KeyRound, Building2, Database, Cpu } from "lucide-react";
import type { ReactNode } from "react";

type Stage = {
  key: string;
  label: string;
  caption: string;
  icon: ReactNode;
  detail: string;
};

const STAGES: Stage[] = [
  {
    key: "auth",
    label: "Auth",
    caption: "Supabase",
    icon: <KeyRound className="h-4 w-4" />,
    detail: "Sign in, scoped JWT",
  },
  {
    key: "org",
    label: "Org",
    caption: "Tenant scope",
    icon: <Building2 className="h-4 w-4" />,
    detail: "Create / join org",
  },
  {
    key: "snapshot",
    label: "Snapshot",
    caption: "PUT graph JSON",
    icon: <Database className="h-4 w-4" />,
    detail: "Signed → verify → ready",
  },
  {
    key: "analyze",
    label: "Analyze",
    caption: "Blast + drift + CI",
    icon: <Cpu className="h-4 w-4" />,
    detail: "Runs surface to org",
  },
];

export function PipelineFlow() {
  return (
    <section
      id="pipeline"
      className="relative scroll-mt-24 overflow-hidden border-t border-white/[0.05] bg-gradient-to-b from-ink-900 to-ink-800/40 px-6 py-24 md:py-32"
    >
      <div
        aria-hidden
        className="dot-backdrop pointer-events-none absolute inset-0 mask-radial opacity-60"
      />

      <div className="relative mx-auto max-w-6xl">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-brand-cyan">
            Pipeline
          </p>
          <h2 className="mt-3 font-display text-4xl tracking-tight text-fog-50 md:text-5xl">
            From sign-in to blast radius in four hops.
          </h2>
        </div>

        {/* Track */}
        <div className="relative mx-auto max-w-5xl">
          {/* connector */}
          <div className="pointer-events-none absolute left-0 right-0 top-[44px] hidden h-px bg-gradient-to-r from-transparent via-white/10 to-transparent md:block" />
          <motion.div
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1.6, ease: [0.22, 1, 0.36, 1] }}
            className="pointer-events-none absolute left-0 right-0 top-[44px] hidden h-px origin-left bg-gradient-to-r from-brand-mint via-brand-cyan to-brand-violet md:block"
          />

          <ol className="grid grid-cols-1 gap-6 md:grid-cols-4">
            {STAGES.map((s, i) => (
              <motion.li
                key={s.key}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ delay: 0.15 + i * 0.18, duration: 0.5 }}
                className="relative flex flex-col items-center text-center"
              >
                {/* Node */}
                <div className="relative mb-5">
                  <span className="absolute inset-0 -m-3 animate-pulse-glow rounded-full bg-brand-mint/15 blur-md" />
                  <div className="relative grid h-[88px] w-[88px] place-items-center rounded-full border border-white/[0.10] bg-ink-700/90 shadow-card-lift">
                    <span className="absolute inset-2 rounded-full border border-white/[0.05]" />
                    <span className="absolute inset-4 rounded-full bg-ink-800/80" />
                    <div className="relative grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-brand-mint/20 to-brand-cyan/10 text-brand-mint">
                      {s.icon}
                    </div>
                  </div>
                  <span className="absolute -right-1 -top-1 inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/10 bg-ink-900 font-mono text-[10px] text-fog-400">
                    {i + 1}
                  </span>
                </div>

                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-fog-500">
                  {s.caption}
                </p>
                <h3 className="mt-1 text-lg font-semibold text-fog-50">
                  {s.label}
                </h3>
                <p className="mt-1 text-xs text-fog-400">{s.detail}</p>

                {/* Travelling pulse on the connector */}
                {i < STAGES.length - 1 && (
                  <motion.span
                    aria-hidden
                    className="pointer-events-none absolute right-0 top-[44px] hidden h-1.5 w-1.5 rounded-full bg-brand-mint shadow-[0_0_10px_#3DF5B0] md:block"
                    initial={{ x: 0, opacity: 0 }}
                    whileInView={{
                      x: ["-50%", "50%"],
                      opacity: [0, 1, 0],
                    }}
                    viewport={{ once: false }}
                    transition={{
                      duration: 1.6,
                      repeat: Infinity,
                      delay: i * 0.5,
                      ease: "easeInOut",
                    }}
                  />
                )}
              </motion.li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
