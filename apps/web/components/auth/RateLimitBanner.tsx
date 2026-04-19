"use client";

import { motion } from "framer-motion";
import { Timer } from "lucide-react";

type RateLimitBannerProps = {
  secondsLeft: number;
  /** Override the default copy. */
  message?: string;
};

/**
 * Pinned, animated banner shown while a rate-limit cooldown is active.
 * Renders nothing when `secondsLeft <= 0`.
 */
export function RateLimitBanner({
  secondsLeft,
  message = "Too many attempts. You can try again in",
}: RateLimitBannerProps) {
  if (secondsLeft <= 0) return null;

  // Progress 0..1 of the original lock window. We don't know the full window,
  // so derive it from a soft 60s ceiling — purely cosmetic.
  const ratio = Math.min(1, secondsLeft / 60);

  return (
    <motion.div
      role="status"
      aria-live="polite"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-md border border-state-warning/35 bg-state-warning/[0.06] px-3 py-2.5 text-sm text-state-warning"
    >
      <div className="flex items-center gap-2.5">
        <Timer className="h-4 w-4 flex-shrink-0" />
        <p className="flex-1 text-xs text-text-secondary">
          {message}{" "}
          <span className="font-mono font-semibold text-state-warning">
            {secondsLeft}s
          </span>
          .
        </p>
      </div>
      <span
        aria-hidden
        className="absolute bottom-0 left-0 h-[2px] bg-state-warning/70 transition-[width] duration-base ease-out"
        style={{ width: `${ratio * 100}%` }}
      />
    </motion.div>
  );
}
