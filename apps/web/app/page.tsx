export default function Home() {
  return (
    <main>
      <nav>
        <a href="/">Home</a>
        <a href="/repos">Repositories</a>
        <a href="/ci">CI runs</a>
      </nav>
      <h1>depOS</h1>
      <p style={{ color: "var(--muted)", maxWidth: "52ch" }}>
        Dependency Map OS — blast radius across branches and allowlisted repos, diagnostics fused into graphs for
        LLMs, CI-first analysis.
      </p>
      <div className="grid">
        <div className="card">
          <h2>Blast radius</h2>
          <p>k-hop · cross-owner</p>
        </div>
        <div className="card">
          <h2>Errors on graph</h2>
          <p>SARIF → nodes</p>
        </div>
        <div className="card">
          <h2>API</h2>
          <p>/v1/ci/analyze</p>
        </div>
      </div>
    </main>
  );
}
