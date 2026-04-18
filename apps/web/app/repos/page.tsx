export default function ReposPage() {
  return (
    <main>
      <nav>
        <a href="/">Home</a>
        <a href="/repos">Repositories</a>
      </nav>
      <h1>Repositories</h1>
      <p style={{ color: "var(--muted)" }}>
        Configure allowlists via <code>PATCH /v1/repos/toggle</code> on the depOS API. This UI is a static shell;
        connect <code>DEPOS_API_URL</code> for live data.
      </p>
    </main>
  );
}
