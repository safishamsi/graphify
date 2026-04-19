"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { GitBranch } from "lucide-react";

/**
 * Left-pane visual for split-screen auth pages.
 * Renders a slowly drifting node-graph composition + brand block.
 */
export function AuthVisual() {
  return (
    <aside className="relative hidden h-full overflow-hidden border-r border-edge-subtle bg-bg-secondary lg:flex lg:flex-col">
      {/* Atmospheric layers */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 grid-backdrop opacity-50 mask-fade-y"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 30% 20%, rgba(61,245,176,0.10), transparent 65%), radial-gradient(50% 40% at 80% 90%, rgba(139,124,255,0.10), transparent 70%)",
        }}
      />
      <motion.div
        aria-hidden
        animate={{ x: [0, 24, 0], y: [0, -16, 0] }}
        transition={{ duration: 24, repeat: Infinity, ease: "easeInOut" }}
        className="pointer-events-none absolute -left-32 top-1/4 h-[26rem] w-[26rem] rounded-full bg-brand-mint/15 blur-[120px]"
      />
      <motion.div
        aria-hidden
        animate={{ x: [0, -16, 0], y: [0, 20, 0] }}
        transition={{ duration: 28, repeat: Infinity, ease: "easeInOut" }}
        className="pointer-events-none absolute -right-32 bottom-1/4 h-[28rem] w-[28rem] rounded-full bg-brand-violet/12 blur-[140px]"
      />

      {/* Brand */}
      <header className="relative px-10 pt-10">
        <Link
          href="/"
          className="inline-flex items-center gap-2.5 text-text-primary"
        >
          <span className="relative grid h-8 w-8 place-items-center rounded-full bg-bg-elevated ring-1 ring-brand-mint/40">
            <GitBranch className="h-4 w-4 text-brand-mint" />
            <span className="absolute inset-0 animate-pulse-glow rounded-full bg-brand-mint/20 blur-md" />
          </span>
          <span className="font-semibold tracking-tight">depOS</span>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted">
            Dependency Map OS
          </span>
        </Link>
      </header>

      {/* Centerpiece graph */}
      <div className="relative flex flex-1 items-center justify-center px-10 pb-16">
        <AuthVisualGraph />
      </div>

      {/* Footer caption */}
      <footer className="relative border-t border-edge-subtle px-10 py-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
          Graph-native blast radius for real repos
        </p>
        <p className="mt-2 max-w-sm text-sm text-text-secondary">
          Snapshot a repository, fuse CI signals, and ship with org-isolated
          confidence.
        </p>
      </footer>
    </aside>
  );
}

/* ------------------------------------------------------------------------- *
 * Decorative graph composition — orbits + pulsing focus node               *
 * ------------------------------------------------------------------------- */

function AuthVisualGraph() {
  // Polar layout for the satellite ring.
  const ring = Array.from({ length: 7 }, (_, i) => {
    const a = (i / 7) * Math.PI * 2 - Math.PI / 2;
    return [Math.cos(a) * 110, Math.sin(a) * 110] as const;
  });

  return (
    <svg viewBox="-200 -200 400 400" className="h-full w-full max-w-md">
      <defs>
        <radialGradient id="auth-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#3DF5B0" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#3DF5B0" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* concentric rings */}
      {[60, 110, 165].map((r, i) => (
        <motion.circle
          key={r}
          cx={0}
          cy={0}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.07)"
          strokeWidth={1}
          strokeDasharray="2 6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, rotate: 360 }}
          transition={{
            opacity: { delay: i * 0.1, duration: 0.6 },
            rotate: { duration: 80 + i * 20, repeat: Infinity, ease: "linear" },
          }}
          style={{ transformOrigin: "center" }}
        />
      ))}

      {/* edges */}
      {ring.map(([x, y], i) => (
        <motion.line
          key={`e-${i}`}
          x1={0}
          y1={0}
          x2={x}
          y2={y}
          stroke="rgba(92,225,255,0.35)"
          strokeWidth={1}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 0.4 + i * 0.06, duration: 0.7 }}
        />
      ))}

      {/* satellites */}
      {ring.map(([x, y], i) => (
        <motion.circle
          key={`n-${i}`}
          cx={x}
          cy={y}
          r={5}
          fill="#0A0F14"
          stroke="#5CE1FF"
          strokeWidth={1.2}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{
            delay: 0.5 + i * 0.06,
            type: "spring",
            stiffness: 220,
            damping: 18,
          }}
          style={{ transformOrigin: `${x}px ${y}px` }}
        />
      ))}

      {/* center node + pulse halo */}
      <circle cx={0} cy={0} r={50} fill="url(#auth-glow)" />
      <motion.circle
        cx={0}
        cy={0}
        r={30}
        fill="rgba(61,245,176,0.18)"
        animate={{ scale: [0.9, 1.1, 0.9], opacity: [0.4, 0.7, 0.4] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "center" }}
      />
      <circle cx={0} cy={0} r={14} fill="#0A0F14" stroke="#3DF5B0" strokeWidth={1.6} />
      <circle cx={0} cy={0} r={5} fill="#3DF5B0" />

      {/* travelling particles */}
      {ring.slice(0, 4).map(([x, y], i) => (
        <motion.circle
          key={`p-${i}`}
          r={2}
          fill="#3DF5B0"
          initial={{ cx: 0, cy: 0, opacity: 0 }}
          animate={{ cx: [0, x], cy: [0, y], opacity: [0, 1, 0] }}
          transition={{
            duration: 2,
            delay: 1.5 + i * 0.4,
            repeat: Infinity,
            repeatDelay: 1.6,
            ease: "easeInOut",
          }}
        />
      ))}
    </svg>
  );
}
