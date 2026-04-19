"use client";

import { motion } from "framer-motion";
import {
  Activity,
  GitBranch,
  Layers3,
  ShieldCheck,
  Workflow,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Feature = {
  icon: ReactNode;
  title: string;
  desc: string;
  visual: ReactNode;
  glow: "mint" | "cyan" | "violet";
};

/* ---------------- Mini visuals (one per card) ---------------- */

function MiniGraph() {
  return (
    <svg viewBox="0 0 140 70" className="h-full w-full">
      <defs>
        <linearGradient id="mg-edge" x1="0" x2="1">
          <stop offset="0%" stopColor="#3DF5B0" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#3DF5B0" stopOpacity="0.05" />
        </linearGradient>
      </defs>
      {[
        ["20,35", "60,18"],
        ["20,35", "60,52"],
        ["60,18", "100,12"],
        ["60,18", "100,30"],
        ["60,52", "100,46"],
        ["60,52", "100,62"],
      ].map(([a, b], i) => {
        const [x1, y1] = a.split(",").map(Number);
        const [x2, y2] = b.split(",").map(Number);
        return (
          <motion.line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="url(#mg-edge)"
            strokeWidth={1.2}
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08, duration: 0.7 }}
          />
        );
      })}
      {[
        [20, 35, 5, "#3DF5B0"],
        [60, 18, 3.5, "#5CE1FF"],
        [60, 52, 3.5, "#5CE1FF"],
        [100, 12, 2.5, "#9CA9BC"],
        [100, 30, 2.5, "#9CA9BC"],
        [100, 46, 2.5, "#9CA9BC"],
        [100, 62, 2.5, "#9CA9BC"],
      ].map(([x, y, r, fill], i) => (
        <circle
          key={i}
          cx={x as number}
          cy={y as number}
          r={r as number}
          fill={fill as string}
        />
      ))}
    </svg>
  );
}

function MiniSarif() {
  const rows = [
    { sev: "warn", path: "auth/session.ts", line: "L42" },
    { sev: "err", path: "api/login.ts", line: "L18" },
    { sev: "info", path: "ws/conn.ts", line: "L7" },
  ];
  return (
    <div className="flex h-full flex-col gap-1.5 p-2 font-mono text-[10px]">
      {rows.map((r, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -6 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.12, duration: 0.4 }}
          className="flex items-center gap-2 rounded border border-white/[0.05] bg-ink-800/60 px-2 py-1"
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              r.sev === "err" && "bg-state-error shadow-[0_0_6px_#F0556C]",
              r.sev === "warn" && "bg-state-warning",
              r.sev === "info" && "bg-brand-cyan",
            )}
          />
          <span className="truncate text-fog-200">{r.path}</span>
          <span className="ml-auto text-fog-500">{r.line}</span>
        </motion.div>
      ))}
    </div>
  );
}

function MiniRisk() {
  return (
    <div className="flex h-full items-end gap-1 px-3 pb-2">
      {[28, 42, 18, 64, 36, 78, 50, 92, 60].map((h, i) => (
        <motion.div
          key={i}
          initial={{ height: 0 }}
          whileInView={{ height: `${h}%` }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 + i * 0.05, duration: 0.6, ease: "easeOut" }}
          className={cn(
            "w-2 rounded-sm",
            h > 70
              ? "bg-state-error/80"
              : h > 45
                ? "bg-state-warning/80"
                : "bg-brand-mint/80",
          )}
        />
      ))}
    </div>
  );
}

function MiniOverlap() {
  return (
    <div className="relative grid h-full place-items-center">
      <svg viewBox="0 0 100 60" className="h-full w-full">
        <motion.circle
          cx="40"
          cy="30"
          r="20"
          fill="none"
          stroke="#5CE1FF"
          strokeWidth="1.4"
          initial={{ cx: 30, opacity: 0 }}
          whileInView={{ cx: 40, opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
        />
        <motion.circle
          cx="60"
          cy="30"
          r="20"
          fill="none"
          stroke="#3DF5B0"
          strokeWidth="1.4"
          initial={{ cx: 70, opacity: 0 }}
          whileInView={{ cx: 60, opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
        />
        <motion.path
          d="M 50 13 A 20 20 0 0 1 50 47 A 20 20 0 0 1 50 13"
          fill="rgba(61,245,176,0.18)"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.7, duration: 0.4 }}
        />
        <text
          x="50"
          y="34"
          textAnchor="middle"
          fontSize="9"
          fill="#3DF5B0"
          fontFamily="ui-monospace, monospace"
          fontWeight="600"
        >
          63%
        </text>
      </svg>
    </div>
  );
}

function MiniOrg() {
  return (
    <div className="flex h-full flex-col gap-1.5 p-2 font-mono text-[10px]">
      {["acme", "northwind", "globex"].map((org, i) => (
        <motion.div
          key={org}
          initial={{ opacity: 0, x: 6 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.1, duration: 0.4 }}
          className="flex items-center justify-between rounded border border-white/[0.05] bg-ink-800/60 px-2 py-1"
        >
          <span className="flex items-center gap-1.5 text-fog-200">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-violet" />
            {org}/
          </span>
          <span className="text-fog-500">RLS</span>
        </motion.div>
      ))}
    </div>
  );
}

function MiniIntel() {
  return (
    <div className="relative h-full overflow-hidden p-2">
      <motion.div
        animate={{ y: [-8, 8, -8] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
        className="font-mono text-[9px] leading-relaxed text-fog-300"
      >
        <pre className="whitespace-pre-wrap">{`{
  "summary": "Refactor blast …",
  "risk": 0.78,
  "files": ["auth/*", "api/*"],
  "rollback_path": "v0.4.2"
}`}</pre>
      </motion.div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-ink-800 to-transparent" />
    </div>
  );
}

const FEATURES: Feature[] = [
  {
    icon: <GitBranch className="h-4 w-4" />,
    title: "Per-org graph snapshots",
    desc: "Signed upload → verify → analyze, isolated per organization.",
    visual: <MiniGraph />,
    glow: "mint",
  },
  {
    icon: <Activity className="h-4 w-4" />,
    title: "Blast radius + error indices",
    desc: "Quantify what changes when one file moves.",
    visual: <MiniRisk />,
    glow: "mint",
  },
  {
    icon: <Layers3 className="h-4 w-4" />,
    title: "SARIF diagnostics fusion",
    desc: "Merge static analysis into the graph layer.",
    visual: <MiniSarif />,
    glow: "cyan",
  },
  {
    icon: <Workflow className="h-4 w-4" />,
    title: "Post-CI overlap scoring",
    desc: "Persist signals from real test runs.",
    visual: <MiniOverlap />,
    glow: "cyan",
  },
  {
    icon: <ShieldCheck className="h-4 w-4" />,
    title: "Org isolation, RLS-first",
    desc: "Federation and drift across ready snapshots.",
    visual: <MiniOrg />,
    glow: "violet",
  },
  {
    icon: <Sparkles className="h-4 w-4" />,
    title: "LLM-ready exports",
    desc: "Intelligence runs surfaced for the whole org.",
    visual: <MiniIntel />,
    glow: "violet",
  },
];

const glowClass: Record<Feature["glow"], string> = {
  mint: "group-hover:shadow-glow-mint",
  cyan: "group-hover:shadow-glow-cyan",
  violet: "group-hover:shadow-glow-violet",
};

const iconColor: Record<Feature["glow"], string> = {
  mint: "text-brand-mint",
  cyan: "text-brand-cyan",
  violet: "text-brand-violet",
};

export function FeatureGrid() {
  return (
    <section
      id="product"
      className="relative scroll-mt-24 px-6 py-24 md:py-32"
    >
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-brand-mint">
            What ships in the console
          </p>
          <h2 className="mt-3 font-display text-4xl tracking-tight text-fog-50 md:text-5xl">
            A graph engine, not a dashboard.
          </h2>
          <p className="mt-4 text-balance text-fog-400">
            Six surfaces that turn raw repositories into operable intelligence.
          </p>
        </div>

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-80px" }}
          variants={{
            hidden: {},
            show: { transition: { staggerChildren: 0.07 } },
          }}
          className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
        >
          {FEATURES.map((f, i) => (
            <motion.article
              key={f.title}
              variants={{
                hidden: { opacity: 0, y: 16 },
                show: { opacity: 1, y: 0 },
              }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className={cn(
                "group relative overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-800/50 p-5 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:border-white/[0.12]",
                glowClass[f.glow],
              )}
            >
              {/* Visual region */}
              <div className="relative mb-5 h-28 overflow-hidden rounded-lg border border-white/[0.05] bg-ink-900/60">
                {f.visual}
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink-900/40 to-transparent" />
              </div>

              <div className="flex items-center gap-2.5">
                <span
                  className={cn(
                    "grid h-7 w-7 place-items-center rounded-md border border-white/[0.06] bg-white/[0.03]",
                    iconColor[f.glow],
                  )}
                >
                  {f.icon}
                </span>
                <h3 className="text-sm font-semibold text-fog-50">{f.title}</h3>
              </div>
              <p className="mt-2 text-sm text-fog-400">{f.desc}</p>

              <span className="pointer-events-none absolute -inset-px rounded-2xl opacity-0 transition-opacity duration-500 group-hover:opacity-100">
                <span className="absolute inset-x-10 -top-px h-px bg-gradient-to-r from-transparent via-brand-mint/60 to-transparent" />
              </span>
            </motion.article>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
