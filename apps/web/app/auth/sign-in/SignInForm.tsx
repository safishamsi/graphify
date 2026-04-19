"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Mail, MailCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthInput } from "@/components/auth/AuthInput";
import { PasswordInput } from "@/components/auth/PasswordInput";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { MethodTabs } from "@/components/auth/MethodTabs";
import { RateLimitBanner } from "@/components/auth/RateLimitBanner";
import { sendMagicLink, signInWithPassword } from "@/lib/auth/actions";
import { useAuthSubmit } from "@/lib/auth/useAuthSubmit";
import { usePrefersReducedMotion } from "@/lib/auth/hooks";
import { validateEmail, validatePassword } from "@/lib/auth/validation";
import { nextQueryString, safeNext } from "@/lib/auth/redirects";

type Method = "password" | "magic";

const METHODS = [
  { value: "password" as const, label: "Password" },
  { value: "magic" as const, label: "Magic link" },
] as const;

export function SignInForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const presetError = params.get("error");
  const reduce = usePrefersReducedMotion();

  const [method, setMethod] = useState<Method>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});
  const [magicSent, setMagicSent] = useState(false);

  const submit = useAuthSubmit();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // Surface a `?error=` from a failed callback as a one-shot form error.
  useEffect(() => {
    if (!presetError) return;
    submit.run(async () => ({
      ok: false as const,
      error: { kind: "expired" as const, message: presetError },
    }));
    // Only on first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Focus first invalid field after a failed submit.
  useEffect(() => {
    if (submit.fieldErrors.email) emailRef.current?.focus();
    else if (submit.fieldErrors.password) passwordRef.current?.focus();
  }, [submit.fieldErrors]);

  // Auto-focus email on first paint (only when not coming back to a state).
  useEffect(() => {
    if (!magicSent) emailRef.current?.focus();
  }, [magicSent]);

  const emailErr =
    submit.fieldErrors.email ??
    (touched.email ? validateEmail(email) : null);
  const passwordErr =
    submit.fieldErrors.password ??
    (method === "password" && touched.password ? validatePassword(password) : null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched({ email: true, password: true });

    const e1 = validateEmail(email);
    if (e1) {
      emailRef.current?.focus();
      return;
    }

    if (method === "password") {
      const e2 = validatePassword(password);
      if (e2) {
        passwordRef.current?.focus();
        return;
      }
      const res = await submit.run(() => signInWithPassword({ email, password }));
      if (!res.ok) return;
      router.push(next);
      router.refresh();
      return;
    }

    const res = await submit.run(() => sendMagicLink(email, next));
    if (res.ok) setMagicSent(true);
  }

  if (magicSent) {
    return (
      <AuthCard
        eyebrow="Check your inbox"
        title="Magic link sent"
        description={
          <>
            We sent a one-time sign-in link to{" "}
            <span className="text-text-primary">{email}</span>. Open it on this
            device to finish signing in.
          </>
        }
        footer={
          <button
            type="button"
            onClick={() => {
              setMagicSent(false);
              submit.reset();
            }}
            className="rounded text-text-secondary underline-offset-4 hover:text-text-primary hover:underline focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            Use a different email
          </button>
        }
      >
        <div className="grid place-items-center py-2">
          <div className="relative">
            <span className="absolute inset-0 motion-safe:animate-pulse-glow rounded-full bg-brand-mint/20 blur-xl" />
            <div className="relative grid h-16 w-16 place-items-center rounded-full bg-bg-elevated ring-1 ring-brand-mint/40">
              <MailCheck className="h-7 w-7 text-brand-mint" aria-hidden />
            </div>
          </div>
        </div>
        <p className="mt-4 text-center text-xs text-text-muted">
          Didn&apos;t get it? Check spam, or{" "}
          <button
            type="button"
            disabled={submit.isRateLimited}
            onClick={() => void submit.run(() => sendMagicLink(email, next))}
            className="rounded text-brand-mint hover:text-brand-mintHover disabled:opacity-60 focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            send another
          </button>
          .
        </p>
        {submit.isRateLimited ? (
          <div className="mt-3">
            <RateLimitBanner secondsLeft={submit.cooldownSeconds} />
          </div>
        ) : null}
      </AuthCard>
    );
  }

  return (
    <AuthCard
      eyebrow="Welcome back"
      title="Sign in to depOS"
      description="Enter your console credentials or get a one-time link by email."
      footer={
        <p className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <span>
            New to depOS?{" "}
            <Link
              href={`/auth/sign-up${nextQueryString(next)}`}
              className="rounded text-brand-mint hover:text-brand-mintHover focus-visible:shadow-ring-mint focus-visible:outline-none"
            >
              Create an account
            </Link>
          </span>
          <Link
            href="/auth/forgot-password"
            className="rounded text-text-muted hover:text-text-secondary focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            Forgot password?
          </Link>
        </p>
      }
    >
      <form onSubmit={(e) => void onSubmit(e)} noValidate className="space-y-5">
        <MethodTabs value={method} onChange={setMethod} options={METHODS} />

        <div className="space-y-4">
          <AuthInput
            ref={emailRef}
            label="Email"
            type="email"
            name="email"
            inputMode="email"
            autoComplete="email"
            placeholder="you@company.dev"
            value={email}
            leadingIcon={<Mail className="h-3.5 w-3.5" aria-hidden />}
            onBlur={() => setTouched((t) => ({ ...t, email: true }))}
            onChange={(e) => {
              setEmail(e.target.value);
              if (submit.fieldErrors.email) submit.clearFieldError("email");
            }}
            error={emailErr}
            required
          />

          <AnimatePresence mode="wait" initial={false}>
            {method === "password" ? (
              <motion.div
                key="pw"
                initial={reduce ? false : { opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
                transition={{ duration: 0.18 }}
              >
                <PasswordInput
                  ref={passwordRef}
                  autoComplete="current-password"
                  placeholder="Your password"
                  value={password}
                  onBlur={() => setTouched((t) => ({ ...t, password: true }))}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (submit.fieldErrors.password) submit.clearFieldError("password");
                  }}
                  error={passwordErr}
                  required
                />
              </motion.div>
            ) : (
              <motion.p
                key="magic-hint"
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-start gap-2 rounded-md border border-edge-subtle bg-bg-sunken px-3 py-2.5 text-xs text-text-muted"
              >
                <Sparkles className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-brand-cyan" aria-hidden />
                We&apos;ll email you a single-use link. No password needed.
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        {submit.formError ? (
          <AuthAlert tone={submit.formError.kind === "network" ? "warning" : "error"}>
            {submit.formError.message}
          </AuthAlert>
        ) : null}

        {submit.isRateLimited ? (
          <RateLimitBanner secondsLeft={submit.cooldownSeconds} />
        ) : null}

        <AuthButton
          type="submit"
          loading={submit.submitting}
          loadingLabel={method === "password" ? "Signing in…" : "Sending link…"}
          disabled={submit.isRateLimited}
        >
          {method === "password" ? "Sign in" : "Send magic link"}
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </AuthButton>
      </form>
    </AuthCard>
  );
}
