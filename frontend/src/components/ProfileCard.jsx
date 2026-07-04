import PlatformBadge from "./PlatformBadge";
import StatPill from "./StatPill";
import { C } from "../styles/tokens";

export default function ProfileCard({ profile }) {
  const created = profile.created_utc
    ? new Date(profile.created_utc * 1000).toISOString().slice(0, 10)
    : null;

  const handle = (profile.platform === "twitter" ? "@" : "u/") + profile.username;

  return (
    <div className="profile-card">
      <div className="profile-card__header">
        {profile.profile_image_url ? (
          <img
            src={profile.profile_image_url}
            alt=""
            className="profile-card__avatar"
          />
        ) : (
          <div className="profile-card__avatar-fallback">
            {(profile.display_name || profile.username || "?")[0].toUpperCase()}
          </div>
        )}

        <div className="profile-card__meta">
          <div className="profile-card__name-row">
            <span className="profile-card__name">
              {profile.display_name || profile.username}
            </span>
            <PlatformBadge platform={profile.platform} />
          </div>
          <span className="profile-card__handle">{handle}</span>
          {profile.bio && (
            <p className="profile-card__bio">{profile.bio}</p>
          )}
          {profile.location && (
            <p className="profile-card__location">◈ {profile.location}</p>
          )}
        </div>
      </div>

      <div className="stat-pills">
        {profile.karma          != null && <StatPill label="karma"     value={profile.karma.toLocaleString()} />}
        {profile.follower_count != null && <StatPill label="followers" value={profile.follower_count.toLocaleString()} color={C.blue} />}
        {profile.following_count!= null && <StatPill label="following" value={profile.following_count.toLocaleString()} color={C.muted2} />}
        <StatPill label="posts" value={profile.posts?.length ?? 0} />
        {profile.subreddits?.length > 0 && (
          <StatPill label="subreddits" value={profile.subreddits.length} color={C.reddit} />
        )}
        {created && <StatPill label="joined" value={created} color={C.muted2} />}
      </div>

      {profile.subreddits?.length > 0 && (
        <div className="subreddit-tags">
          <p className="subreddit-tags__label">ACTIVE SUBREDDITS</p>
          <div className="subreddit-tags__list">
            {profile.subreddits.slice(0, 20).map(s => (
              <span key={s} className="subreddit-tag">r/{s}</span>
            ))}
            {profile.subreddits.length > 20 && (
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: C.muted }}>
                +{profile.subreddits.length - 20} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
