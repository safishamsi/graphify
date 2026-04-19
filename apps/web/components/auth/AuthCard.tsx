"use client";

import { motion } from "framer-motion";
import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "@/lib/auth/hooks";

type AuthCardProps = {
  children: ReactNode;
  className?: string;
  /** Optional eyebrow rendered above the title (e.g. "Step 2 of 3"). */
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
};

export function AuthCard({
  children,
  className,
  eyebrow,
  title,
  description,
  footer,
}: AuthCardProps) {
  const reduce = usePrefersReducedMotion();
  const id = useId();
  const titleId = `${id}-title`;
  const descId = description ? `${id}-desc` : undefined;

  return (
    <motion.section
      role="region"
      aria-labelledby={titleId}
      aria-describedby={descId}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "glass-panel relative w-full max-w-md overflow-hidden rounded-2xl border border-edge-soft p-6 shadow-panel sm:p-8",
        className,
      )}
    >
      {/* top hairline glow */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-12 top-0 h-px bg-gradient-hairline-mint opacity-70"
      />
      {/* corner glow */}
      <span
        aria-hidden
        className="pointer-events-none absolute -top-20 -left-20 h-40 w-40 rounded-full bg-brand-mint/10 blur-3xl"
      />

      <header className="relative">
        {eyebrow ? (
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-mint">
            {eyebrow}
          </p>
        ) : null}
        <h1
          id={titleId}
          className="mt-2 font-display text-2xl tracking-tight text-text-primary sm:text-[2rem]"
        >
          {title}
        </h1>
        {description ? (
          <p id={descId} className="mt-2 text-sm text-text-muted">
            {description}
          </p>
        ) : null}
      </header>

      <div className="relative mt-6">{children}</div>

      {footer ? (
        <footer className="relative mt-7 border-t border-edge-subtle pt-5 text-sm text-text-muted">
          {footer}
        </footer>
      ) : null}
    </motion.section>
  );
}
