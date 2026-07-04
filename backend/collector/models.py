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


@dataclass
class PhoneProfile:
    """Aggregated OSINT result for a phone number lookup."""
    phone_number: str  # E.164 format, e.g. +919876543210

    # Carrier / telco layer (NumVerify)
    valid: Optional[bool] = None
    country_code: Optional[str] = None       # e.g. "IN"
    country_name: Optional[str] = None       # e.g. "India"
    location: Optional[str] = None           # region/city from prefix
    carrier: Optional[str] = None            # e.g. "Jio"
    line_type: Optional[str] = None          # "mobile" | "landline" | "voip"

    # Telegram
    telegram_display_name: Optional[str] = None
    telegram_username: Optional[str] = None  # without @
    telegram_user_id: Optional[int] = None
    telegram_profile_photo_url: Optional[str] = None

    # WhatsApp
    whatsapp_display_name: Optional[str] = None
    whatsapp_profile_photo_url: Optional[str] = None
    whatsapp_about: Optional[str] = None     # status/about text
    whatsapp_registered: Optional[bool] = None

    # Web mentions
    web_mentions: list = field(default_factory=list)  # list of {url, title, snippet}

    def to_dict(self) -> dict:
        return asdict(self)
