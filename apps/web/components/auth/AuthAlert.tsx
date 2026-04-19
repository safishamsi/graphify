"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "@/lib/auth/hooks";

type Tone = "error" | "success" | "info" | "warning";

type AuthAlertProps = {
  tone?: Tone;
  children: ReactNode;
  /** Optional title rendered above the body. */
  title?: ReactNode;
  /** Render an action slot inline (e.g. "Resend"). */
  action?: ReactNode;
};

const TONE_STYLES: Record<
  Tone,
  { wrap: string; icon: ReactNode; live: "polite" | "assertive" }
> = {
  error: {
    wrap: "border-state-error/40 bg-state-error/[0.06] text-state-error",
    icon: <XCircle className="h-4 w-4 flex-shrink-0" />,
    live: "assertive",
  },
  success: {
    wrap: "border-brand-mint/40 bg-brand-mint/[0.06] text-brand-mint",
    icon: <CheckCircle2 className="h-4 w-4 flex-shrink-0" />,
    live: "polite",
  },
  info: {
    wrap: "border-brand-cyan/40 bg-brand-cyan/[0.06] text-brand-cyan",
    icon: <Info className="h-4 w-4 flex-shrink-0" />,
    live: "polite",
  },
  warning: {
    wrap: "border-state-warning/40 bg-state-warning/[0.06] text-state-warning",
    icon: <AlertTriangle className="h-4 w-4 flex-shrink-0" />,
    live: "polite",
  },
};

export function AuthAlert({
  tone = "error",
  title,
  children,
  action,
}: AuthAlertProps) {
  const reduce = usePrefersReducedMotion();
  const t = TONE_STYLES[tone];
  return (
    <AnimatePresence initial={false}>
      <motion.div
        key="alert"
        role={tone === "error" ? "alert" : "status"}
        aria-live={t.live}
        initial={reduce ? false : { opacity: 0, y: -4, height: 0 }}
        animate={{ opacity: 1, y: 0, height: "auto" }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          "flex gap-2.5 overflow-hidden rounded-md border px-3 py-2.5 text-sm",
          t.wrap,
        )}
      >
        <span className="mt-0.5">{t.icon}</span>
        <div className="min-w-0 flex-1">
          {title ? <p className="font-medium">{title}</p> : null}
          <div
            className={cn(
              "text-text-secondary",
              title ? "mt-0.5 text-xs" : "text-sm",
            )}
          >
            {children}
          </div>
        </div>
        {action ? <div className="flex-shrink-0">{action}</div> : null}
      </motion.div>
    </AnimatePresence>
  );
}
