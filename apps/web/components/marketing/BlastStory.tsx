"use client";

import { motion } from "framer-motion";

/**
 * "What breaks if this changes?" — a focused visual story
 * with a single epicenter, expanding rings, and lit-up nodes.
 */
export function BlastStory() {
  return (
    <section className="relative overflow-hidden border-y border-white/[0.05] bg-ink-900 px-6 py-28 md:py-36">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 grid-backdrop opacity-40 mask-fade-y"
      />

      <div className="relative mx-auto grid max-w-6xl items-center gap-16 lg:grid-cols-2">
        <div className="order-2 lg:order-1">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-state-error">
            Blast radius
          </p>
          <h2 className="mt-3 font-display text-4xl tracking-tight text-fog-50 md:text-5xl">
            What breaks if{" "}
            <span className="relative inline-block">
              <span className="text-gradient-mint">this</span>
              <motion.span
                aria-hidden
                className="absolute -inset-x-2 bottom-0 h-px bg-brand-mint/60"
                initial={{ scaleX: 0 }}
                whileInView={{ scaleX: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.7, delay: 0.3 }}
                style={{ transformOrigin: "left" }}
              />
            </span>{" "}
            changes?
          </h2>
          <p className="mt-5 max-w-md text-fog-400">
            Pick any file. depOS expands the dependency wave outward, scoring
            risk per ring and revealing what your CI signals already know.
          </p>

          <ul className="mt-8 space-y-3 font-mono text-[12px] text-fog-300">
            <li className="flex items-center gap-3">
              <span className="h-2 w-2 rounded-full bg-state-error shadow-[0_0_8px_#F0556C]" />
              <span className="text-fog-100">epicenter</span>
              <span className="text-fog-500">— the file you touched</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="h-2 w-2 rounded-full bg-state-warning" />
              <span className="text-fog-100">ring 1</span>
              <span className="text-fog-500">— direct importers</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="h-2 w-2 rounded-full bg-brand-cyan" />
              <span className="text-fog-100">ring 2</span>
              <span className="text-fog-500">— transitive reach</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="h-2 w-2 rounded-full bg-fog-500" />
              <span className="text-fog-100">cold</span>
              <span className="text-fog-500">— unaffected by this change</span>
            </li>
          </ul>
        </div>

        {/* Animated story */}
        <div className="order-1 lg:order-2">
          <div className="relative mx-auto aspect-square w-full max-w-md">
            <BlastDiagram />
          </div>
        </div>
      </div>
    </section>
  );
}

function BlastDiagram() {
  // Polar coordinates for satellites
  const ring1 = polar(6, 70);
  const ring2 = polar(10, 130);
  const ring3 = polar(14, 195);

  return (
    <svg viewBox="-220 -220 440 440" className="h-full w-full">
      <defs>
        <radialGradient id="blast-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#F0556C" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#F0556C" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* outer rings */}
      {[80, 145, 205].map((r, i) => (
        <motion.circle
          key={r}
          cx={0}
          cy={0}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={1}
          strokeDasharray="2 6"
          initial={{ scale: 0.8, opacity: 0 }}
          whileInView={{ scale: 1, opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 + i * 0.1, duration: 0.6 }}
        />
      ))}

      {/* expanding blast waves */}
      {[0, 1].map((i) => (
        <motion.circle
          key={`wave-${i}`}
          cx={0}
          cy={0}
          r={20}
          fill="none"
          stroke="#F0556C"
          strokeWidth={1.4}
          initial={{ scale: 0.4, opacity: 0 }}
          animate={{ scale: [0.4, 4.5], opacity: [0.7, 0] }}
          transition={{
            duration: 4,
            delay: i * 1.6,
            repeat: Infinity,
            ease: "easeOut",
          }}
        />
      ))}

      {/* edges to ring 1 */}
      {ring1.map(([x, y], i) => (
        <motion.line
          key={`e1-${i}`}
          x1={0}
          y1={0}
          x2={x}
          y2={y}
          stroke="#F2C94C"
          strokeOpacity={0.6}
          strokeWidth={1.2}
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4 + i * 0.05, duration: 0.6 }}
        />
      ))}

      {/* edges ring 1 → ring 2 (paired) */}
      {ring2.map(([x, y], i) => {
        const [px, py] = ring1[i % ring1.length];
        return (
          <motion.line
            key={`e2-${i}`}
            x1={px}
            y1={py}
            x2={x}
            y2={y}
            stroke="rgba(92,225,255,0.4)"
            strokeWidth={0.9}
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.7 + i * 0.04, duration: 0.5 }}
          />
        );
      })}

      {/* ring 3 nodes (cold) */}
      {ring3.map(([x, y], i) => (
        <motion.circle
          key={`r3-${i}`}
          cx={x}
          cy={y}
          r={2.5}
          fill="#3F4B62"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 1 + i * 0.02 }}
        />
      ))}

      {/* ring 2 nodes */}
      {ring2.map(([x, y], i) => (
        <g key={`r2-${i}`}>
          <motion.circle
            cx={x}
            cy={y}
            r={4}
            fill="#5CE1FF"
            initial={{ scale: 0, opacity: 0 }}
            whileInView={{ scale: 1, opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.9 + i * 0.04, duration: 0.4 }}
            style={{ transformOrigin: `${x}px ${y}px` }}
          />
        </g>
      ))}

      {/* ring 1 nodes */}
      {ring1.map(([x, y], i) => (
        <g key={`r1-${i}`}>
          <motion.circle
            cx={x}
            cy={y}
            r={11}
            fill="rgba(242,201,76,0.18)"
            animate={{ opacity: [0.3, 0.6, 0.3] }}
            transition={{
              duration: 2.6,
              delay: i * 0.2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
          <motion.circle
            cx={x}
            cy={y}
            r={6}
            fill="#0A0F14"
            stroke="#F2C94C"
            strokeWidth={1.4}
            initial={{ scale: 0 }}
            whileInView={{ scale: 1 }}
            viewport={{ once: true }}
            transition={{
              delay: 0.5 + i * 0.06,
              type: "spring",
              stiffness: 220,
            }}
            style={{ transformOrigin: `${x}px ${y}px` }}
          />
          <circle cx={x} cy={y} r={2} fill="#F2C94C" />
        </g>
      ))}

      {/* epicenter */}
      <circle cx={0} cy={0} r={48} fill="url(#blast-glow)" />
      <circle
        cx={0}
        cy={0}
        r={20}
        fill="#0A0F14"
        stroke="#F0556C"
        strokeWidth={2}
      />
      <circle cx={0} cy={0} r={9} fill="#F0556C" />
    </svg>
  );
}

function polar(count: number, radius: number): Array<[number, number]> {
  return Array.from({ length: count }, (_, i) => {
    const a = (i / count) * Math.PI * 2 - Math.PI / 2;
    return [radius * Math.cos(a), radius * Math.sin(a)];
  });
}
