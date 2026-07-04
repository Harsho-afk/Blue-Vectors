from typing import Optional
from dataclasses import dataclass, field, asdict
import logging


# Data schemas
@dataclass
class Post:
    external_id: str
    text: str
    timestamp: float  # Unix epoch (UTC)
    metadata: dict = field(default_factory=dict)


@dataclass
class AccountProfile:
    platform: str  # "reddit" | "twitter"
    username: str
    display_name: str
    bio: str
    location: str
    profile_image_url: str
    created_utc: Optional[float]
    posts: list = field(default_factory=list)  # list[Post]
    subreddits: list = field(default_factory=list)  # Reddit only
    karma: Optional[int] = None  # Reddit only
    follower_count: Optional[int] = None  # Twitter only
    following_count: Optional[int] = None  # Twitter only
    extra: dict = field(default_factory=dict)  # platform-specific extras (e.g. is_private)

    def to_dict(self) -> dict:
        """Serialize to a plain dict — safe for JSON and PostgreSQL JSONB."""
        return asdict(self)


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("aria.collector")
