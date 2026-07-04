export default function PlatformBadge({ platform }) {
  const prefix = platform === "reddit" ? "r/" : platform === "github" ? "" : "@";
  const label  = platform === "github" ? "GitHub" : platform.toUpperCase();
  return (
    <span className={`platform-badge platform-badge--${platform}`}>
      {prefix}{label}
    </span>
  );
}
