import { cn } from "@/lib/cn";

type Variant = "grid" | "dots";

type GridBackdropProps = {
  variant?: Variant;
  className?: string;
  /** Mask the edges so the pattern fades away nicely. */
  fade?: boolean;
};

/**
 * Shared, decorative backdrop for marketing sections.
 * Renders behind content via absolute positioning — parents must be `relative`.
 */
export function GridBackdrop({
  variant = "grid",
  className,
  fade = true,
}: GridBackdropProps) {
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-0",
        variant === "grid" ? "grid-backdrop" : "dot-backdrop",
        fade && "mask-fade-y",
        className,
      )}
    />
  );
}
