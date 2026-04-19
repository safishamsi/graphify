"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";
import { cn } from "@/lib/cn";

type OtpInputProps = {
  value: string;
  onChange: (next: string) => void;
  /** Auto-submit when all 6 digits are entered. */
  onComplete?: (code: string) => void;
  length?: number;
  disabled?: boolean;
  error?: boolean;
  autoFocus?: boolean;
  /** Used to wire up `aria-describedby` from a parent (e.g. error message). */
  describedBy?: string;
  /** Used as the visible label via aria-label / sr-only header. */
  label?: string;
};

/**
 * Premium 6-cell OTP input. Supports paste, backspace navigation,
 * arrow keys, and auto-advance. Emits a single string value to parents.
 */
export function OtpInput({
  value,
  onChange,
  onComplete,
  length = 6,
  disabled,
  error,
  autoFocus,
  describedBy,
  label = "One-time passcode",
}: OtpInputProps) {
  const groupId = useId();
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const cells = useMemo(
    () => Array.from({ length }, (_, i) => value[i] ?? ""),
    [value, length],
  );

  useEffect(() => {
    if (autoFocus) refs.current[0]?.focus();
  }, [autoFocus]);

  useEffect(() => {
    if (value.length === length) onComplete?.(value);
    // intentionally only react to value crossing the threshold
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.length === length]);

  function setCell(index: number, char: string) {
    const digit = char.replace(/\D/g, "").slice(-1);
    const arr = cells.slice();
    arr[index] = digit;
    const next = arr.join("").slice(0, length);
    onChange(next);
    if (digit && index < length - 1) refs.current[index + 1]?.focus();
  }

  function onKey(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace") {
      if (cells[index]) {
        setCell(index, "");
      } else if (index > 0) {
        const arr = cells.slice();
        arr[index - 1] = "";
        onChange(arr.join(""));
        refs.current[index - 1]?.focus();
      }
      e.preventDefault();
    } else if (e.key === "ArrowLeft" && index > 0) {
      refs.current[index - 1]?.focus();
      e.preventDefault();
    } else if (e.key === "ArrowRight" && index < length - 1) {
      refs.current[index + 1]?.focus();
      e.preventDefault();
    } else if (e.key === "Home") {
      refs.current[0]?.focus();
      e.preventDefault();
    } else if (e.key === "End") {
      refs.current[length - 1]?.focus();
      e.preventDefault();
    }
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
    if (!text) return;
    e.preventDefault();
    onChange(text);
    refs.current[Math.min(text.length, length - 1)]?.focus();
  }

  return (
    <div
      role="group"
      aria-label={label}
      aria-describedby={describedBy}
      className="flex justify-between gap-1.5 sm:gap-2"
    >
      {cells.map((char, i) => (
        <input
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          aria-label={`Digit ${i + 1} of ${length}`}
          id={`${groupId}-${i}`}
          maxLength={1}
          disabled={disabled}
          value={char}
          onChange={(e) => setCell(i, e.target.value)}
          onKeyDown={(e) => onKey(i, e)}
          onPaste={onPaste}
          aria-invalid={error || undefined}
          className={cn(
            // Mobile-first sizing — keeps cells inside even on a 320px viewport.
            "h-12 min-w-0 flex-1 rounded-md border bg-bg-sunken text-center font-mono text-lg text-text-primary transition-all duration-fast sm:h-12 sm:flex-none sm:w-11",
            "focus:border-edge-focus focus:shadow-glow-mint-sm focus:outline-none",
            error
              ? "border-state-error/60 shadow-glow-danger"
              : "border-edge-soft hover:border-edge-hover",
            disabled && "cursor-not-allowed opacity-60",
          )}
        />
      ))}
    </div>
  );
}
