import { Suspense } from "react";
import { LoginForm } from "./LoginForm";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="auth-card text-muted">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
