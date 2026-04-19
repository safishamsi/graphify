import { cn } from "@/lib/cn";

type AuthSkeletonProps = {
  /** Number of input rows to render. Defaults to 2. */
  fields?: number;
  /** Render the segmented method tabs above the fields. */
  withTabs?: boolean;
  /** Render the strength meter beneath the password row. */
  withStrength?: boolean;
};

/**
 * Drop-in Suspense fallback for auth pages. Mirrors the AuthCard outline so
 * the layout doesn't shift when the real form mounts.
 */
export function AuthSkeleton({
  fields = 2,
  withTabs,
  withStrength,
}: AuthSkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading sign-in form"
      aria-live="polite"
      className="glass-panel relative w-full max-w-md overflow-hidden rounded-2xl border border-edge-soft p-7 shadow-panel sm:p-8"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-12 top-0 h-px bg-gradient-hairline-mint opacity-40"
      />

      {/* Header */}
      <div className="space-y-2">
        <SkBar w="w-20" h="h-3" />
        <SkBar w="w-3/5" h="h-7" tone="bright" />
        <SkBar w="w-4/5" h="h-3" />
      </div>

      {/* Body */}
      <div className="mt-7 space-y-4">
        {withTabs ? <SkBar w="w-full" h="h-9" rounded="rounded-md" /> : null}
        {Array.from({ length: fields }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <SkBar w="w-16" h="h-2.5" />
            <SkBar w="w-full" h="h-10" rounded="rounded-md" />
          </div>
        ))}
        {withStrength ? (
          <div className="flex gap-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkBar key={i} w="flex-1" h="h-[3px]" />
            ))}
          </div>
        ) : null}
        <SkBar w="w-full" h="h-10" rounded="rounded-md" tone="bright" />
      </div>

      {/* Footer */}
      <div className="mt-7 border-t border-edge-subtle pt-5">
        <SkBar w="w-1/2" h="h-3" />
      </div>

      <span className="sr-only">Loading…</span>
    </div>
  );
}

function SkBar({
  w,
  h,
  rounded = "rounded",
  tone = "default",
}: {
  w: string;
  h: string;
  rounded?: string;
  tone?: "default" | "bright";
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden bg-bg-active/60 motion-safe:animate-shimmer",
        tone === "bright" && "bg-bg-elevated",
        w,
        h,
        rounded,
      )}
    >
      <span
        aria-hidden
        className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/[0.04] to-transparent motion-safe:animate-shimmer"
      />
    </div>
  );
}
