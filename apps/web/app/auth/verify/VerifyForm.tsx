"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { OtpInput } from "@/components/auth/OtpInput";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { RateLimitBanner } from "@/components/auth/RateLimitBanner";
import { sendMagicLink, verifyEmailOtp } from "@/lib/auth/actions";
import { useAuthSubmit } from "@/lib/auth/useAuthSubmit";
import { useResendCooldown } from "@/lib/auth/hooks";
import { safeNext } from "@/lib/auth/redirects";

export function VerifyForm() {
  const router = useRouter();
  const params = useSearchParams();
  const email = params.get("email") ?? "";
  const next = safeNext(params.get("next"));

  const [code, setCode] = useState("");
  const submit = useAuthSubmit();
  const resend = useAuthSubmit();
  const cooldown = useResendCooldown(30);

  if (!email) {
    return (
      <AuthCard
        eyebrow="Missing email"
        title="No verification context"
        description="Start a new sign-in to receive a code."
        footer={
          <Link
            href="/auth/sign-in"
            className="rounded text-text-secondary hover:text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            Go to sign in
          </Link>
        }
      >
        <p className="text-sm text-text-muted">
          This page expects an email parameter to verify against. Try sending
          yourself a fresh link or one-time code first.
        </p>
      </AuthCard>
    );
  }

  async function attemptVerify(value: string) {
    const res = await submit.run(() => verifyEmailOtp(email, value));
    if (!res.ok) return;
    router.push(next);
    router.refresh();
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (code.length !== 6) {
      void submit.run(async () => ({
        ok: false as const,
        error: {
          kind: "validation" as const,
          field: "code" as const,
          message: "Enter the 6-digit code from your email.",
        },
      }));
      return;
    }
    void attemptVerify(code);
  }

  async function onResend() {
    if (!cooldown.canResend) return;
    const res = await resend.run(() => sendMagicLink(email, next));
    if (res.ok) cooldown.trigger();
  }

  const hasError = Boolean(submit.formError) || Boolean(submit.fieldErrors.code);

  return (
    <AuthCard
      eyebrow="Verify"
      title="Enter your code"
      description={
        <>
          We sent a 6-digit code to{" "}
          <span className="text-text-primary">{email}</span>. It expires in 10
          minutes.
        </>
      }
      footer={
        <p className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Link
            href="/auth/sign-in"
            className="rounded text-text-secondary hover:text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            ← Back to sign in
          </Link>
          <button
            type="button"
            disabled={!cooldown.canResend || resend.submitting || resend.isRateLimited}
            onClick={() => void onResend()}
            className="rounded text-text-muted hover:text-text-secondary disabled:opacity-60 focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            {resend.submitting
              ? "sending…"
              : cooldown.canResend
                ? "resend code"
                : `resend in ${cooldown.secondsLeft}s`}
          </button>
        </p>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5">
        <div className="grid place-items-center py-1">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-bg-elevated ring-1 ring-brand-cyan/40">
            <KeyRound className="h-5 w-5 text-brand-cyan" aria-hidden />
          </div>
        </div>

        <OtpInput
          value={code}
          onChange={(v) => {
            setCode(v);
            if (submit.fieldErrors.code) submit.clearFieldError("code");
            if (submit.formError) submit.clearFormError();
          }}
          onComplete={(c) => void attemptVerify(c)}
          disabled={submit.submitting || submit.isRateLimited}
          error={hasError}
          autoFocus
          label="Email verification code"
        />

        {submit.fieldErrors.code ? (
          <p role="alert" aria-live="assertive" className="font-mono text-[11px] text-state-error">
            {submit.fieldErrors.code}
          </p>
        ) : null}

        {submit.formError ? (
          <AuthAlert tone={submit.formError.kind === "network" ? "warning" : "error"}>
            {submit.formError.message}
          </AuthAlert>
        ) : null}

        {submit.isRateLimited ? (
          <RateLimitBanner secondsLeft={submit.cooldownSeconds} />
        ) : null}

        {resend.formError ? (
          <AuthAlert tone="warning">{resend.formError.message}</AuthAlert>
        ) : null}

        <AuthButton
          type="submit"
          loading={submit.submitting}
          loadingLabel="Verifying…"
          disabled={submit.isRateLimited}
        >
          Verify and continue
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </AuthButton>
      </form>
    </AuthCard>
  );
}
