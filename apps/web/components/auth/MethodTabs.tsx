"use client";

import { motion } from "framer-motion";
import { useRef, type KeyboardEvent } from "react";
import { cn } from "@/lib/cn";
import { usePrefersReducedMotion } from "@/lib/auth/hooks";

type Tab<T extends string> = { value: T; label: string };

type MethodTabsProps<T extends string> = {
  value: T;
  onChange: (next: T) => void;
  options: ReadonlyArray<Tab<T>>;
  ariaLabel?: string;
};

/**
 * Segmented control for switching between auth methods (e.g. Password / Magic link).
 * Uses a shared layoutId pill that slides under the active option.
 *
 * Implements the WAI-ARIA tablist pattern: arrow keys move focus + selection,
 * Home/End jump to ends.
 */
export function MethodTabs<T extends string>({
  value,
  onChange,
  options,
  ariaLabel = "Sign-in method",
}: MethodTabsProps<T>) {
  const reduce = usePrefersReducedMotion();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function focusAt(index: number) {
    const wrapped = (index + options.length) % options.length;
    refs.current[wrapped]?.focus();
    onChange(options[wrapped].value);
  }

  function onKey(index: number, e: KeyboardEvent<HTMLButtonElement>) {
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
        focusAt(index + 1);
        e.preventDefault();
        break;
      case "ArrowLeft":
      case "ArrowUp":
        focusAt(index - 1);
        e.preventDefault();
        break;
      case "Home":
        focusAt(0);
        e.preventDefault();
        break;
      case "End":
        focusAt(options.length - 1);
        e.preventDefault();
        break;
    }
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="relative grid grid-flow-col auto-cols-fr rounded-md border border-edge-soft bg-bg-sunken p-1"
    >
      {options.map((opt, i) => {
        const isActive = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            type="button"
            tabIndex={isActive ? 0 : -1}
            aria-selected={isActive}
            onClick={() => onChange(opt.value)}
            onKeyDown={(e) => onKey(i, e)}
            className={cn(
              "relative z-10 min-h-[36px] rounded px-3 py-1.5 text-xs font-medium transition-colors duration-fast",
              "focus-visible:outline-none focus-visible:shadow-ring-mint",
              isActive ? "text-text-primary" : "text-text-muted hover:text-text-secondary",
            )}
          >
            {isActive ? (
              <motion.span
                layoutId={reduce ? undefined : "auth-method-pill"}
                className="absolute inset-0 -z-10 rounded bg-bg-active shadow-hairline-top"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            ) : null}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
