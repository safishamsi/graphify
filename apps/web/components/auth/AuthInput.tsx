"use client";

import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { cn } from "@/lib/cn";

type AuthInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  leadingIcon?: ReactNode;
  trailing?: ReactNode;
  /** When true, the input renders without its own border so wrappers can supply one. */
  bare?: boolean;
};

export const AuthInput = forwardRef<HTMLInputElement, AuthInputProps>(
  function AuthInput(
    {
      id,
      label,
      hint,
      error,
      leadingIcon,
      trailing,
      className,
      bare,
      ...rest
    },
    ref,
  ) {
    const reactId = useId();
    const inputId = id ?? `${reactId}-input`;
    const errorId = `${inputId}-err`;
    const hintId = `${inputId}-hint`;
    const describedBy =
      [error ? errorId : null, hint && !error ? hintId : null]
        .filter(Boolean)
        .join(" ") || undefined;

    return (
      <div className="space-y-1.5">
        <label
          htmlFor={inputId}
          className="flex items-center justify-between text-xs font-medium text-text-secondary"
        >
          <span>{label}</span>
          {hint && !error ? (
            <span id={hintId} className="font-mono text-[10px] text-text-muted">
              {hint}
            </span>
          ) : null}
        </label>

        <div
          className={cn(
            "group relative flex items-center rounded-md border bg-bg-sunken transition-all duration-fast",
            "focus-within:border-edge-focus focus-within:shadow-glow-mint-sm",
            error
              ? "border-state-error/60 shadow-glow-danger"
              : "border-edge-soft hover:border-edge-hover",
            bare && "border-transparent bg-transparent shadow-none",
          )}
        >
          {leadingIcon ? (
            <span
              aria-hidden
              className={cn(
                "pl-3 pr-1 text-text-muted transition-colors group-focus-within:text-brand-mint",
                error && "text-state-error",
              )}
            >
              {leadingIcon}
            </span>
          ) : null}

          <input
            ref={ref}
            id={inputId}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={describedBy}
            className={cn(
              // 44px min-height on mobile to satisfy touch-target a11y.
              "min-h-[44px] w-full bg-transparent px-3 py-2.5 text-base text-text-primary placeholder:text-text-subtle focus:outline-none sm:min-h-0 sm:py-2 sm:text-sm",
              leadingIcon && "pl-1.5",
              trailing && "pr-1",
              className,
            )}
            {...rest}
          />

          {trailing ? <span className="pr-1.5">{trailing}</span> : null}
        </div>

        {error ? (
          <p
            id={errorId}
            role="alert"
            aria-live="polite"
            className="font-mono text-[11px] text-state-error"
          >
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
