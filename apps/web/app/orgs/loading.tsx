export default function OrgsIndexLoading() {
  return (
    <main className="marketing-page" aria-busy="true" aria-label="Loading organizations">
      <div className="skeleton-block skeleton-line" style={{ maxWidth: "8rem", marginBottom: "2rem" }} />
      <div className="skeleton-block skeleton-title" style={{ width: "min(18rem, 70%)" }} />
      <div className="skeleton-block skeleton-line" style={{ marginTop: "1rem" }} />
      <div className="skeleton-block skeleton-line" style={{ maxWidth: "32rem" }} />
      <div className="skeleton-block skeleton-table" style={{ marginTop: "2.5rem", height: "10rem" }} />
    </main>
  );
}
