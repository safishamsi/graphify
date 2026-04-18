export default function OrgSlugLoading() {
  return (
    <div aria-busy="true" aria-label="Loading workspace">
      <div className="skeleton-block skeleton-title" />
      <div className="skeleton-block skeleton-line" />
      <div className="skeleton-block skeleton-line" style={{ maxWidth: "28rem" }} />
      <div className="skeleton-block skeleton-table" />
    </div>
  );
}
