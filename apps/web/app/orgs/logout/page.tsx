import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const metadata = { title: "Sign out · depOS" };

export default async function OrgsLogoutPage() {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    redirect("/auth/sign-in?next=/orgs/logout");
  }

  return (
    <main className="marketing-page">
      <p className="text-muted" style={{ marginBottom: "2rem" }}>
        <Link href="/orgs">← Organizations</Link>
      </p>
      <h1 className="font-display page-title">Sign out</h1>
      <p className="page-desc">
        You will leave the console and return to the depOS home. Sign in again
        anytime to open your organizations.
      </p>

      <div className="zone-interactive" style={{ marginTop: "2rem", maxWidth: "28rem" }}>
        <form action="/auth/sign-out?next=/" method="post">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
            <button type="submit" className="btn btn-primary">
              Sign out
            </button>
            <Link href="/orgs" className="btn btn-secondary" style={{ textDecoration: "none" }}>
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </main>
  );
}
