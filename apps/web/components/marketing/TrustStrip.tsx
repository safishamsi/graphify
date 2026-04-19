"use client";

import { motion } from "framer-motion";

const STACK = [
  "Next.js · TypeScript · Python",
  "Supabase · Postgres · Storage",
  "SARIF · CodeQL · Trivy",
  "GitHub Actions · GitLab CI",
  "OpenAI · Anthropic · vLLM",
  "Iceberg · DuckDB · Parquet",
];

export function TrustStrip() {
  return (
    <section className="relative border-y border-white/[0.06] bg-ink-800/40 py-6">
      <p className="mb-4 text-center font-mono text-[10px] uppercase tracking-[0.24em] text-fog-500">
        Built for the polyglot stack
      </p>
      <div
        aria-hidden
        className="relative overflow-hidden"
        style={{
          maskImage:
            "linear-gradient(to right, transparent, black 12%, black 88%, transparent)",
          WebkitMaskImage:
            "linear-gradient(to right, transparent, black 12%, black 88%, transparent)",
        }}
      >
        <motion.div
          className="flex w-max gap-12 whitespace-nowrap font-mono text-sm text-fog-300"
          animate={{ x: ["0%", "-50%"] }}
          transition={{ duration: 38, repeat: Infinity, ease: "linear" }}
        >
          {[...STACK, ...STACK].map((s, i) => (
            <span key={i} className="flex items-center gap-3">
              <span className="h-1 w-1 rounded-full bg-brand-mint/60" />
              {s}
            </span>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
