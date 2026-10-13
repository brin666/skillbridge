export function LoadingSkeleton() {
  return (
    <div className="skeleton-stack" aria-busy="true">
      <div className="skeleton skeleton-overview" />
      <div className="skeleton skeleton-panel" />
      <div className="skeleton skeleton-panel" />
    </div>
  )
}
