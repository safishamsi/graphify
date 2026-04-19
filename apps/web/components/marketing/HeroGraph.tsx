"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";

/**
 * Animated dependency graph for the hero centerpiece.
 *
 * Renders a deterministic node/edge layout in SVG so it can be
 * server-rendered, then layers framer-motion stagger reveals + a
 * "blast radius" pulse expanding from the central node.
 */

type Node = {
  id: string;
  x: number;
  y: number;
  r: number;
  label?: string;
  /** 0 = epicenter, 1 = first ring, 2 = second ring, 3 = outer */
  ring: 0 | 1 | 2 | 3;
  risk?: "ok" | "warn" | "risk";
};

type Edge = {
  from: string;
  to: string;
  /** when true, animates as part of the blast wave */
  hot?: boolean;
};

const VIEW_W = 720;
const VIEW_H = 460;
const CX = VIEW_W / 2;
const CY = VIEW_H / 2;

const NODES: Node[] = [
  // Epicenter
  { id: "core", x: CX, y: CY, r: 16, label: "auth/session.ts", ring: 0, risk: "risk" },

  // Ring 1 — direct importers (4)
  { id: "r1a", x: CX - 130, y: CY - 70, r: 9, ring: 1, risk: "warn", label: "api/login" },
  { id: "r1b", x: CX + 130, y: CY - 70, r: 9, ring: 1, risk: "warn", label: "api/me" },
  { id: "r1c", x: CX - 130, y: CY + 70, r: 9, ring: 1, risk: "warn", label: "mw/auth" },
  { id: "r1d", x: CX + 130, y: CY + 70, r: 9, ring: 1, risk: "warn", label: "ws/conn" },

  // Ring 2 — transitive (8)
  { id: "r2a", x: CX - 240, y: CY - 140, r: 6, ring: 2 },
  { id: "r2b", x: CX - 50,  y: CY - 170, r: 6, ring: 2 },
  { id: "r2c", x: CX + 60,  y: CY - 175, r: 6, ring: 2 },
  { id: "r2d", x: CX + 250, y: CY - 130, r: 6, ring: 2 },
  { id: "r2e", x: CX + 270, y: CY + 130, r: 6, ring: 2 },
  { id: "r2f", x: CX + 50,  y: CY + 180, r: 6, ring: 2 },
  { id: "r2g", x: CX - 70,  y: CY + 175, r: 6, ring: 2 },
  { id: "r2h", x: CX - 250, y: CY + 140, r: 6, ring: 2 },

  // Ring 3 — outer satellites (8)
  { id: "r3a", x: CX - 320, y: CY - 60,  r: 4, ring: 3 },
  { id: "r3b", x: CX - 200, y: CY - 220, r: 4, ring: 3 },
  { id: "r3c", x: CX + 0,   y: CY - 220, r: 4, ring: 3 },
  { id: "r3d", x: CX + 200, y: CY - 220, r: 4, ring: 3 },
  { id: "r3e", x: CX + 320, y: CY + 0,   r: 4, ring: 3 },
  { id: "r3f", x: CX + 200, y: CY + 220, r: 4, ring: 3 },
  { id: "r3g", x: CX + 0,   y: CY + 220, r: 4, ring: 3 },
  { id: "r3h", x: CX - 200, y: CY + 220, r: 4, ring: 3 },
];

const EDGES: Edge[] = [
  // Core → ring 1 (hot, direct blast)
  { from: "core", to: "r1a", hot: true },
  { from: "core", to: "r1b", hot: true },
  { from: "core", to: "r1c", hot: true },
  { from: "core", to: "r1d", hot: true },

  // Ring 1 → ring 2
  { from: "r1a", to: "r2a" },
  { from: "r1a", to: "r2b" },
  { from: "r1b", to: "r2c" },
  { from: "r1b", to: "r2d" },
  { from: "r1d", to: "r2e" },
  { from: "r1d", to: "r2f" },
  { from: "r1c", to: "r2g" },
  { from: "r1c", to: "r2h" },

  // Ring 2 → ring 3
  { from: "r2a", to: "r3a" },
  { from: "r2b", to: "r3b" },
  { from: "r2c", to: "r3c" },
  { from: "r2d", to: "r3d" },
  { from: "r2e", to: "r3e" },
  { from: "r2f", to: "r3f" },
  { from: "r2g", to: "r3g" },
  { from: "r2h", to: "r3h" },
];

const COLOR = {
  ringStroke: {
    0: "#F0556C",
    1: "#F2C94C",
    2: "rgba(92,225,255,0.6)",
    3: "rgba(156,169,188,0.4)",
  } as Record<Node["ring"], string>,
  ringFill: {
    0: "#F0556C",
    1: "#F2C94C",
    2: "#5CE1FF",
    3: "#9CA9BC",
  } as Record<Node["ring"], string>,
};

export function HeroGraph() {
  const nodeMap = useMemo(
    () => Object.fromEntries(NODES.map((n) => [n.id, n] as const)),
    [],
  );

  return (
    <div className="relative aspect-[720/460] w-full">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="absolute inset-0 h-full w-full overflow-visible"
        role="img"
        aria-label="Animated dependency graph showing blast radius around a central module"
      >
        <defs>
          <radialGradient id="nodeGlowRisk" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#F0556C" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#F0556C" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="nodeGlowMint" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#3DF5B0" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#3DF5B0" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="edgeHot" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#F0556C" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#F2C94C" stopOpacity="0.4" />
          </linearGradient>
          <linearGradient id="edgeCool" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#5CE1FF" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#5CE1FF" stopOpacity="0.05" />
          </linearGradient>
        </defs>

        {/* Concentric rings — blast radius scaffolding */}
        {[110, 200, 290].map((r, i) => (
          <motion.circle
            key={r}
            cx={CX}
            cy={CY}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={1}
            strokeDasharray="3 6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 + i * 0.1, duration: 0.6 }}
          />
        ))}

        {/* Pulsing blast wave (loops) */}
        {[0, 1, 2].map((i) => (
          <motion.circle
            key={`wave-${i}`}
            cx={CX}
            cy={CY}
            r={20}
            fill="none"
            stroke="#F0556C"
            strokeWidth={1.5}
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: [0.5, 0], scale: [0.6, 4] }}
            transition={{
              duration: 4,
              delay: i * 1.3,
              repeat: Infinity,
              ease: "easeOut",
            }}
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          />
        ))}

        {/* Edges */}
        <g>
          {EDGES.map((edge, idx) => {
            const a = nodeMap[edge.from];
            const b = nodeMap[edge.to];
            if (!a || !b) return null;
            const delay = 0.5 + (b.ring + (edge.hot ? 0 : 0.4)) * 0.15;
            return (
              <motion.line
                key={`${edge.from}-${edge.to}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={edge.hot ? "url(#edgeHot)" : "url(#edgeCool)"}
                strokeWidth={edge.hot ? 1.4 : 0.9}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{
                  pathLength: { delay, duration: 0.8, ease: [0.22, 1, 0.36, 1] },
                  opacity: { delay, duration: 0.4 },
                }}
                style={{ vectorEffect: "non-scaling-stroke" }}
              />
            );
          })}
        </g>

        {/* Subtle data-flow particles on hot edges */}
        <g>
          {EDGES.filter((e) => e.hot).map((edge, idx) => {
            const a = nodeMap[edge.from];
            const b = nodeMap[edge.to];
            if (!a || !b) return null;
            return (
              <motion.circle
                key={`p-${edge.from}-${edge.to}`}
                r={2}
                fill="#F2C94C"
                initial={{ cx: a.x, cy: a.y, opacity: 0 }}
                animate={{ cx: [a.x, b.x], cy: [a.y, b.y], opacity: [0, 1, 0] }}
                transition={{
                  duration: 1.6,
                  delay: 1.6 + idx * 0.2,
                  repeat: Infinity,
                  repeatDelay: 1.2,
                  ease: "easeInOut",
                }}
              />
            );
          })}
        </g>

        {/* Nodes */}
        <g>
          {NODES.map((n) => {
            const isCore = n.ring === 0;
            const fill = COLOR.ringFill[n.ring];
            const stroke = COLOR.ringStroke[n.ring];
            const delay = 0.3 + n.ring * 0.2;
            return (
              <g key={n.id}>
                {/* Glow halo on epicenter + ring 1 */}
                {n.ring <= 1 && (
                  <motion.circle
                    cx={n.x}
                    cy={n.y}
                    r={n.r * 3.6}
                    fill={isCore ? "url(#nodeGlowRisk)" : "url(#nodeGlowMint)"}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: isCore ? [0.6, 0.95, 0.6] : [0.3, 0.55, 0.3] }}
                    transition={{
                      duration: isCore ? 2.2 : 3,
                      delay,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                  />
                )}
                <motion.circle
                  cx={n.x}
                  cy={n.y}
                  r={n.r}
                  fill="#0A0F14"
                  stroke={stroke}
                  strokeWidth={isCore ? 2 : 1.2}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{
                    delay,
                    duration: 0.5,
                    type: "spring",
                    stiffness: 220,
                    damping: 20,
                  }}
                  style={{ transformOrigin: `${n.x}px ${n.y}px` }}
                />
                <motion.circle
                  cx={n.x}
                  cy={n.y}
                  r={Math.max(n.r * 0.45, 2)}
                  fill={fill}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: delay + 0.15, duration: 0.4 }}
                />
              </g>
            );
          })}
        </g>

        {/* Floating labels for narrative anchor points */}
        <motion.g
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.4, duration: 0.5 }}
        >
          <rect
            x={CX + 28}
            y={CY - 28}
            width={150}
            height={22}
            rx={6}
            fill="rgba(14,20,27,0.85)"
            stroke="rgba(240,85,108,0.5)"
            strokeWidth={1}
          />
          <text
            x={CX + 38}
            y={CY - 12}
            fill="#F0556C"
            fontFamily="ui-monospace, SF Mono, Menlo, monospace"
            fontSize={11}
            fontWeight={600}
          >
            auth/session.ts
          </text>
        </motion.g>

        <motion.g
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.7, duration: 0.5 }}
        >
          <rect
            x={CX - 220}
            y={CY + 80}
            width={140}
            height={22}
            rx={6}
            fill="rgba(14,20,27,0.85)"
            stroke="rgba(242,201,76,0.4)"
            strokeWidth={1}
          />
          <text
            x={CX - 210}
            y={CY + 96}
            fill="#F2C94C"
            fontFamily="ui-monospace, SF Mono, Menlo, monospace"
            fontSize={11}
            fontWeight={600}
          >
            blast: 12 modules
          </text>
        </motion.g>
      </svg>

      {/* Legend chip — overlay (not part of SVG, easier styling) */}
      <div className="pointer-events-none absolute bottom-3 left-3 flex gap-3 text-[10px] uppercase tracking-[0.18em] text-fog-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-state-error shadow-[0_0_8px_#F0556C]" />
          epicenter
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-state-warning" />
          direct
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-brand-cyan" />
          transitive
        </span>
      </div>
    </div>
  );
}
