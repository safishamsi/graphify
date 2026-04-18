import Link from "next/link";

export default function SignupLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-shell">
      <header className="auth-header">
        <Link href="/" className="font-display auth-brand">
          depOS
        </Link>
      </header>
      <div className="auth-body">{children}</div>
    </div>
  );
}
