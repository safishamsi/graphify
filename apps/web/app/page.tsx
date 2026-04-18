import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="marketing-page">
      <div className="marketing-hero">
        <p className="marketing-kicker hero-stagger-1">Dependency Map OS</p>
        <h1 className="font-display hero-stagger-2" style={{ margin: "0 0 0.75rem" }}>
          Graph-native blast radius for real repos.
        </h1>
        <p className="hero-stagger-3" style={{ margin: 0, maxWidth: "40ch", color: "var(--fg-muted)", fontSize: "1.05rem" }}>
          Upload commit graphs to Storage, fuse SARIF diagnostics, run CI correlation, and ship LLM-ready exports — with
          org isolation you can stand behind.
        </p>
        <div className="marketing-cta-row hero-stagger-3">
          <Button variant="primary" asChild>
            <Link href="/login">Open console</Link>
          </Button>
          <Button variant="secondary" asChild>
            <Link href="/signup">Create account</Link>
          </Button>
        </div>
      </div>

      <section className="marketing-section">
        <h2>What you get in the console</h2>
        <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--fg-muted)", lineHeight: 1.7 }}>
          <li>Per-org graph snapshots (signed upload → verify → analyze).</li>
          <li>Blast radius and error indices for changed files.</li>
          <li>Post-CI overlap scoring with persisted signals.</li>
          <li>Federation and drift across ready snapshots.</li>
          <li>Intelligence runs surfaced for the whole org.</li>
        </ul>
      </section>

      <section className="marketing-section">
        <h2>Flow</h2>
        <ol style={{ margin: 0, paddingLeft: "1.25rem", color: "var(--fg-muted)", lineHeight: 1.7 }}>
          <li>Authenticate with Supabase.</li>
          <li>Create or join an organization.</li>
          <li>Prepare a snapshot, PUT graph JSON to Storage, complete, then analyze.</li>
        </ol>
      </section>

      <section className="marketing-section">
        <h2>Docs</h2>
        <p style={{ margin: 0, color: "var(--fg-muted)" }}>
          Architecture, product scope, and CI examples live in the repository <code className="font-mono">docs/</code>{" "}
          tree and root <code className="font-mono">README.md</code> (local Supabase + depOS API + this web app).
        </p>
      </section>
    </main>
  );
}
