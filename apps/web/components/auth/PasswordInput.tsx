"use client";

import { forwardRef, useState, type InputHTMLAttributes } from "react";
import { Eye, EyeOff, Lock } from "lucide-react";
import { AuthInput } from "./AuthInput";
import { passwordStrength } from "@/lib/auth/validation";
import { cn } from "@/lib/cn";

type PasswordInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string | null;
  /** Show segmented strength meter beneath the field. */
  showStrength?: boolean;
};

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  function PasswordInput(
    { label = "Password", error, showStrength, value, onChange, ...rest },
    ref,
  ) {
    const [visible, setVisible] = useState(false);
    const stringValue = typeof value === "string" ? value : "";
    const strength = passwordStrength(stringValue);

    return (
      <div className="space-y-2">
        <AuthInput
          ref={ref}
          label={label}
          type={visible ? "text" : "password"}
          autoComplete="current-password"
          leadingIcon={<Lock className="h-3.5 w-3.5" />}
          error={error}
          value={value}
          onChange={onChange}
          trailing={
            <button
              type="button"
              onClick={() => setVisible((v) => !v)}
              tabIndex={-1}
              aria-label={visible ? "Hide password" : "Show password"}
              className="grid h-7 w-7 place-items-center rounded text-text-muted transition-colors hover:text-text-primary"
            >
              {visible ? (
                <EyeOff className="h-3.5 w-3.5" />
              ) : (
                <Eye className="h-3.5 w-3.5" />
              )}
            </button>
          }
          {...rest}
        />
        {showStrength ? (
          <div aria-live="polite">
            <div className="flex gap-1">
              {[1, 2, 3, 4].map((seg) => (
                <span
                  key={seg}
                  className={cn(
                    "h-[3px] flex-1 rounded-full transition-colors duration-fast",
                    strength.score >= seg
                      ? seg <= 1
                        ? "bg-state-error"
                        : seg <= 2
                          ? "bg-state-warning"
                          : seg <= 3
                            ? "bg-brand-cyan"
                            : "bg-brand-mint shadow-[0_0_8px_#3DF5B0]"
                      : "bg-edge-subtle",
                  )}
                />
              ))}
            </div>
            <p className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
              {strength.label === "empty"
                ? strength.hint
                : `${strength.label} · ${strength.hint}`}
            </p>
          </div>
        ) : null}
      </div>
    );
  },
);
