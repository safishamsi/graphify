"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

type GlowOrbsProps = {
  className?: string;
};

/**
 * Three slowly-drifting blurred color orbs that sit behind a section.
 * Provides depth + atmosphere without being a focal element.
 */
export function GlowOrbs({ className }: GlowOrbsProps) {
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-0 overflow-hidden",
        className,
      )}
    >
      <motion.div
        className="absolute -top-40 -left-32 h-[36rem] w-[36rem] rounded-full bg-brand-mint/20 blur-[120px]"
        animate={{ x: [0, 40, 0], y: [0, 30, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute top-1/3 -right-40 h-[40rem] w-[40rem] rounded-full bg-brand-violet/20 blur-[140px]"
        animate={{ x: [0, -30, 0], y: [0, -20, 0] }}
        transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-0 left-1/3 h-[28rem] w-[28rem] rounded-full bg-brand-cyan/15 blur-[120px]"
        animate={{ x: [0, 20, 0], y: [0, 15, 0] }}
        transition={{ duration: 26, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
