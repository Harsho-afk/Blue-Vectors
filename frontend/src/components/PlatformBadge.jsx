export default function PlatformBadge({ platform }) {
  return (
    <span className={`platform-badge platform-badge--${platform}`}>
      {platform === "reddit" ? "r/" : "@"}{platform.toUpperCase()}
    </span>
  );
}
