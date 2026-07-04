export default function PlatformBadge({ platform }) {
  const prefix = platform === "reddit" ? "r/"
                : platform === "github" || platform === "instagram" ? ""
                : "@";
  const label  = platform === "github" ? "GitHub"
               : platform === "instagram" ? "Instagram"
               : platform.toUpperCase();
  return (
    <span className={`platform-badge platform-badge--${platform}`}>
      {prefix}{label}
    </span>
  );
}
