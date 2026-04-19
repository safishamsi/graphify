"use client";

import { motion } from "framer-motion";
import {
  ChevronRight,
  Folder,
  Activity,
  GitBranch,
  Terminal,
  Database,
} from "lucide-react";

const NAV = [
  { icon: <Folder className="h-3.5 w-3.5" />, label: "Snapshots", count: 12 },
  { icon: <Activity className="h-3.5 w-3.5" />, label: "Analyze", count: 3, active: true },
  { icon: <GitBranch className="h-3.5 w-3.5" />, label: "Federation" },
  { icon: <Database className="h-3.5 w-3.5" />, label: "Drift" },
  { icon: <Terminal className="h-3.5 w-3.5" />, label: "Intelligence" },
];

const RUNS = [
  { id: "run_8a1f", branch: "main", risk: 0.78, files: 12, status: "ready" },
  { id: "run_71c0", branch: "feat/auth-rotation", risk: 0.42, files: 6, status: "ready" },
  { id: "run_60be", branch: "fix/ws-conn", risk: 0.18, files: 2, status: "running" },
];

export function ConsoleMock() {
  return (
    <section
      id="graph"
      className="relative scroll-mt-24 overflow-hidden px-6 py-24 md:py-32"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-radial-violet opacity-50"
      />

      <div className="relative mx-auto grid max-w-6xl gap-12 lg:grid-cols-[1fr_1.4fr] lg:items-center">
        {/* Copy */}
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-brand-violet">
            Inside the console
          </p>
          <h2 className="mt-3 font-display text-4xl tracking-tight text-fog-50 md:text-5xl">
            One surface for graph, risk, and runs.
          </h2>
          <p className="mt-4 max-w-md text-fog-400">
            Browse snapshots, open the analyzer, and watch a run land — all
            scoped to your org. Raw JSON is one click away.
          </p>

          <ul className="mt-8 space-y-3 text-sm text-fog-300">
            {[
              "Sidebar nav with active rail accent",
              "Layered risk + diagnostics overlays",
              "JSON drawer for every analyze result",
            ].map((line) => (
              <li key={line} className="flex items-start gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-brand-mint shadow-[0_0_6px_#3DF5B0]" />
                {line}
              </li>
            ))}
          </ul>
        </div>

        {/* Mock */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="glass-panel relative overflow-hidden rounded-2xl border border-white/[0.08] shadow-panel"
        >
          {/* chrome */}
          <div className="flex items-center justify-between border-b border-white/[0.06] bg-ink-800/60 px-4 py-2.5">
            <div className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-state-error/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-state-warning/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-state-success/70" />
            </div>
            <span className="font-mono text-[11px] text-fog-400">
              acme · /orgs/acme/analyze
            </span>
            <span className="font-mono text-[11px] text-fog-500">●&nbsp;synced</span>
          </div>

          <div className="grid grid-cols-[140px_1fr] divide-x divide-white/[0.05] bg-ink-700/40">
            {/* Sidebar */}
            <aside className="bg-ink-800/60 p-2.5">
              <p className="px-2 pb-2 font-mono text-[9px] uppercase tracking-[0.2em] text-fog-500">
                acme/
              </p>
              <ul className="space-y-0.5">
                {NAV.map((n) => (
                  <li key={n.label}>
                    <div
                      className={[
                        "group flex items-center gap-2 rounded-md border-l-2 px-2 py-1.5 text-xs",
                        n.active
                          ? "border-brand-mint bg-white/[0.04] text-fog-50"
                          : "border-transparent text-fog-400 hover:bg-white/[0.03] hover:text-fog-100",
                      ].join(" ")}
                    >
                      <span
                        className={
                          n.active ? "text-brand-mint" : "text-fog-500"
                        }
                      >
                        {n.icon}
                      </span>
                      <span className="flex-1">{n.label}</span>
                      {n.count != null && (
                        <span className="font-mono text-[10px] text-fog-500">
                          {n.count}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </aside>

            {/* Main */}
            <div className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-fog-500">
                    Analyze runs
                  </p>
                  <h4 className="text-sm font-semibold text-fog-50">
                    Last 24h
                  </h4>
                </div>
                <span className="rounded-full border border-brand-mint/40 bg-brand-mint/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-brand-mint">
                  ● live
                </span>
              </div>

              <div className="overflow-hidden rounded-lg border border-white/[0.06]">
                <table className="w-full text-xs">
                  <thead className="bg-ink-800/80">
                    <tr className="text-left font-mono text-[10px] uppercase tracking-[0.16em] text-fog-500">
                      <th className="px-3 py-2">Run</th>
                      <th className="px-3 py-2">Branch</th>
                      <th className="px-3 py-2">Risk</th>
                      <th className="px-3 py-2">Files</th>
                      <th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {RUNS.map((r, i) => (
                      <motion.tr
                        key={r.id}
                        initial={{ opacity: 0, x: -8 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: 0.2 + i * 0.1 }}
                        className="border-t border-white/[0.04] text-fog-200"
                      >
                        <td className="px-3 py-2 font-mono text-[11px] text-fog-100">
                          {r.id}
                        </td>
                        <td className="px-3 py-2 font-mono text-[11px] text-fog-300">
                          {r.branch}
                        </td>
                        <td className="px-3 py-2">
                          <RiskBar value={r.risk} />
                        </td>
                        <td className="px-3 py-2 font-mono text-[11px]">
                          {r.files}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span
                            className={[
                              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px]",
                              r.status === "ready"
                                ? "border-brand-mint/40 bg-brand-mint/10 text-brand-mint"
                                : "border-brand-cyan/40 bg-brand-cyan/10 text-brand-cyan",
                            ].join(" ")}
                          >
                            {r.status === "running" && (
                              <span className="h-1.5 w-1.5 animate-pulse-glow rounded-full bg-brand-cyan" />
                            )}
                            {r.status}
                          </span>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* JSON drawer preview */}
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.6, duration: 0.5 }}
                className="mt-3 overflow-hidden rounded-lg border border-white/[0.06] bg-ink-900/70"
              >
                <div className="flex items-center gap-2 border-b border-white/[0.05] px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-fog-500">
                  <ChevronRight className="h-3 w-3" />
                  raw json · run_8a1f
                </div>
                <pre className="overflow-hidden px-3 py-2 font-mono text-[10px] leading-relaxed text-fog-300">
{`{
  "blast_radius": 12,
  "risk": 0.78,
  "epicenter": "auth/session.ts",
  "ci_overlap": 0.63,
  "diagnostics": [ … 3 sarif results ]
}`}
                </pre>
              </motion.div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function RiskBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  const color =
    value > 0.6 ? "bg-state-error" : value > 0.3 ? "bg-state-warning" : "bg-brand-mint";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-16 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${pct}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className={`h-full ${color}`}
        />
      </div>
      <span className="font-mono text-[10px] text-fog-300">{value.toFixed(2)}</span>
    </div>
  );
}
