import hashlib
import aiohttp
import base64
from .models import AccountProfile, log


async def lookup_gravatar(email: str) -> AccountProfile | None:
    """
    Fetch Gravatar profile picture and profile data for an email address.
    Returns an AccountProfile suitable for saving to the accounts table
    (so the correlation engine can compare it against other accounts).
    Returns None if no Gravatar exists for this email.
    """
    email_clean = email.strip().lower()
    md5_hash = hashlib.md5(email_clean.encode("utf-8")).hexdigest()

    avatar_url = f"https://www.gravatar.com/avatar/{md5_hash}?s=400&d=404"
    profile_url = f"https://www.gravatar.com/{md5_hash}.json"

    display_name = None
    bio = None
    profile_image_b64 = None

    async with aiohttp.ClientSession() as session:
        # 1. Fetch avatar image
        try:
            async with session.get(
                avatar_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
                    b64 = base64.b64encode(img_bytes).decode()
                    content_type = resp.headers.get("Content-Type", "image/jpeg")
                    profile_image_b64 = f"data:{content_type};base64,{b64}"
                    log.info("Gravatar: avatar found for %s", email_clean)
                elif resp.status == 404:
                    log.info("Gravatar: no avatar for %s", email_clean)
                else:
                    log.warning("Gravatar: avatar fetch returned HTTP %d", resp.status)
        except Exception as exc:
            log.warning("Gravatar: avatar fetch failed — %s", exc)

        # 2. Fetch profile JSON for display name / bio
        try:
            async with session.get(
                profile_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    entry = (data.get("entry") or [{}])[0]
                    display_name = entry.get("displayName") or entry.get("preferredUsername")
                    bio = entry.get("aboutMe")
                    log.info(
                        "Gravatar: profile found — name=%s bio=%s",
                        display_name,
                        bool(bio),
                    )
        except Exception as exc:
            log.warning("Gravatar: profile JSON failed — %s", exc)

    if not profile_image_b64 and not display_name:
        log.info("Gravatar: no useful data for %s — skipping", email_clean)
        return None

    return AccountProfile(
        platform="gravatar",
        username=email_clean,
        display_name=display_name or "",
        bio=bio or "",
        location="",
        profile_image_url=profile_image_b64 or "",
        created_utc=None,
    )
