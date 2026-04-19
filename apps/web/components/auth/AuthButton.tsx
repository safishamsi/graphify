"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";

type AuthButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  loading?: boolean;
  /** When provided, replaces the children while `loading` is true. */
  loadingLabel?: ReactNode;
  fullWidth?: boolean;
};

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-brand-mint text-text-onAccent shadow-glow-mint-sm hover:bg-brand-mintHover hover:shadow-glow-mint active:bg-brand-mintActive",
  secondary:
    "border border-edge-soft bg-bg-hover text-text-primary hover:border-edge-hover hover:bg-bg-active",
  ghost:
    "text-text-secondary hover:text-text-primary hover:bg-bg-hover",
};

export const AuthButton = forwardRef<HTMLButtonElement, AuthButtonProps>(
  function AuthButton(
    {
      variant = "primary",
      loading,
      loadingLabel,
      fullWidth = true,
      disabled,
      className,
      children,
      ...rest
    },
    ref,
  ) {
    const isDisabled = disabled || loading;
    return (
      <button
        ref={ref}
        type={rest.type ?? "button"}
        disabled={isDisabled}
        aria-busy={loading || undefined}
        className={cn(
          // 44px min touch target on mobile, condensed on desktop.
          "group relative inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-4 py-3 text-sm font-semibold transition-all duration-fast sm:min-h-0 sm:py-2.5",
          "focus-visible:outline-none focus-visible:shadow-ring-mint",
          "disabled:cursor-not-allowed disabled:opacity-60",
          fullWidth && "w-full",
          VARIANT[variant],
          className,
        )}
        {...rest}
      >
        {loading ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>{loadingLabel ?? children}</span>
          </>
        ) : (
          children
        )}
      </button>
    );
  },
);
