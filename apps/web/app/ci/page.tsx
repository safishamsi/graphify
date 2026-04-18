export default function CIPage() {
  return (
    <main>
      <nav>
        <a href="/">Home</a>
        <a href="/ci">CI runs</a>
      </nav>
      <h1>CI &amp; blast radius</h1>
      <p style={{ color: "var(--muted)" }}>
        Run the GitHub Action <code>depos-ci.yml</code> to post analysis. Post-CI correlation:{" "}
        <code>POST /v1/ci/postci</code>.
      </p>
    </main>
  );
}
