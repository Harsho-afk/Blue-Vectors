import os
import asyncio
import aiohttp
from .models import PhoneProfile, log

# ---------------------------------------------------------------------------
# Phone number OSINT collector
#
# Sources:
#   1. phonenumbers — carrier, line type, country, region (offline, free)
#   2. Telegram     — display name, username, user ID, profile photo
#   3. WhatsApp     — display name, profile photo, about/status, registered check
#   4. Web search   — public mentions via SerpAPI / Google Custom Search
#
# ── SETUP ──────────────────────────────────────────────────────────────────
#
# 1. PHONENUMBERS (no API key, no rate limit)
#    pip install phonenumbers
#
# 2. TELEGRAM
#    Requires a Telegram account session (MTProto via Telethon).
#    a) pip install telethon
#    b) Go to https://my.telegram.org → API development tools
#       Create an app → copy api_id and api_hash
#    c) Run this once interactively to generate a session file:
#
#         from telethon.sync import TelegramClient
#         client = TelegramClient("aria_session", API_ID, API_HASH)
#         client.start()   # prompts for phone + OTP
#         print(client.session.save())
#
#    d) Copy the printed session string into .env:
#    .env:  TELEGRAM_API_ID=<api_id>
#           TELEGRAM_API_HASH=<api_hash>
#           TELEGRAM_SESSION=<session_string>
#
# 3. WHATSAPP
#    Requires whatsapp-web.js running as a local sidecar service.
#    It links to your WhatsApp account via QR code (same as WhatsApp Web).
#
#    a) npm install -g whatsapp-web.js express qrcode-terminal
#    b) Save this as wa_sidecar.js and run: node wa_sidecar.js
#
#       ──────────────────────────────────────────────────────────
#       const { Client, LocalAuth } = require('whatsapp-web.js');
#       const express = require('express');
#       const qrcode  = require('qrcode-terminal');
#
#       const app    = express();
#       const client = new Client({ authStrategy: new LocalAuth() });
#
#       client.on('qr', qr => qrcode.generate(qr, { small: true }));
#       client.on('ready', () => console.log('WhatsApp ready'));
#       client.initialize();
#
#       app.use(express.json());
#
#       app.get('/lookup/:phone', async (req, res) => {
#           const jid = req.params.phone + '@c.us';
#           try {
#               const registered = await client.isRegisteredUser(jid);
#               if (!registered) return res.json({ registered: false });
#               const contact = await client.getContactById(jid);
#               const profile_pic = await client.getProfilePicUrl(jid).catch(() => null);
#               const about = await contact.getAbout().catch(() => null);
#               res.json({
#                   registered: true,
#                   name: contact.pushname || contact.name || null,
#                   profile_pic,
#                   about,
#               });
#           } catch (e) {
#               res.status(500).json({ error: String(e) });
#           }
#       });
#
#       app.listen(3333, () => console.log('WA sidecar on :3333'));
#       ──────────────────────────────────────────────────────────
#
#    c) Scan the QR code with your phone (WhatsApp → Linked Devices → Link a Device)
#    .env:  WHATSAPP_SIDECAR_URL=http://localhost:3333   (default, change if remote)
#
# 4. WEB MENTIONS (free, no API key)
#    pip install duckduckgo-search
# ---------------------------------------------------------------------------


# ── phonenumbers (offline, free, no API key needed) ─────────────────────────

def _lookup_phonenumbers(phone: str) -> dict:
    try:
        import phonenumbers
        from phonenumbers import geocoder, carrier as pn_carrier, number_type, PhoneNumberType
    except ImportError:
        log.warning("Phone: phonenumbers not installed — pip install phonenumbers")
        return {}

    try:
        num = phonenumbers.parse(phone)
    except Exception as exc:
        log.warning("Phone: failed to parse number — %s", exc)
        return {"valid": False}

    if not phonenumbers.is_valid_number(num):
        return {"valid": False}

    ntype = number_type(num)
    type_map = {
        PhoneNumberType.MOBILE:          "mobile",
        PhoneNumberType.FIXED_LINE:      "landline",
        PhoneNumberType.FIXED_LINE_OR_MOBILE: "mobile",
        PhoneNumberType.VOIP:            "voip",
        PhoneNumberType.TOLL_FREE:       "toll_free",
        PhoneNumberType.PREMIUM_RATE:    "premium_rate",
        PhoneNumberType.SHARED_COST:     "shared_cost",
        PhoneNumberType.PERSONAL_NUMBER: "personal",
        PhoneNumberType.PAGER:           "pager",
        PhoneNumberType.UAN:             "uan",
    }

    region      = phonenumbers.region_code_for_number(num)
    carrier_str = pn_carrier.name_for_number(num, "en") or None
    location    = geocoder.description_for_number(num, "en") or None

    return {
        "valid":        True,
        "country_code": region,
        "country_name": location or region,
        "location":     location,
        "carrier":      carrier_str,
        "line_type":    type_map.get(ntype, "unknown"),
    }


# ── Telegram ────────────────────────────────────────────────────────────────

async def _lookup_telegram(phone: str) -> dict:
    api_id      = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash    = os.environ.get("TELEGRAM_API_HASH", "").strip()
    session_str = os.environ.get("TELEGRAM_SESSION", "").strip()

    if not all([api_id, api_hash, session_str]):
        log.warning("Phone: Telegram env vars not set — skipping.")
        return {}

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
        from telethon.tl.types import InputPhoneContact
        from telethon.errors import FloodWaitError
    except ImportError:
        log.warning("Phone: telethon not installed — pip install telethon")
        return {}

    result = {}
    client = TelegramClient(StringSession(session_str), int(api_id), api_hash)

    try:
        await client.connect()

        # Import the number as a temporary contact — only way to resolve
        # an arbitrary phone to a Telegram user without them being in your contacts.
        contact = InputPhoneContact(client_id=0, phone=phone, first_name="ARIA", last_name="Lookup")
        imported = await client(ImportContactsRequest([contact]))

        if not imported.users:
            log.info("Phone: %s not found on Telegram.", phone)
            await client(DeleteContactsRequest(id=[]))
            return {"telegram_registered": False}

        user = imported.users[0]

        # Download profile photo to a temp buffer and upload somewhere,
        # or just flag that one exists. We'll store the flag + user ID
        # so the frontend can fetch via the Telegram CDN if needed.
        photo_url = None
        try:
            import io, base64
            buf = io.BytesIO()
            await client.download_profile_photo(user, file=buf)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            if b64:
                photo_url = f"data:image/jpeg;base64,{b64}"
        except Exception:
            pass

        # Build display name — exclude our placeholder contact name
        parts = [user.first_name or "", user.last_name or ""]
        display_name = " ".join(p for p in parts if p).strip() or None

        result = {
            "telegram_display_name":     display_name,
            "telegram_username":         user.username,
            "telegram_user_id":          user.id,
            "telegram_profile_photo_url": photo_url,
        }

        # Clean up — remove the temporary contact
        await client(DeleteContactsRequest(id=[user]))

    except FloodWaitError as exc:
        log.warning("Phone: Telegram flood wait %ds — try again later.", exc.seconds)
    except Exception as exc:
        log.warning("Phone: Telegram lookup failed — %s", exc)
    finally:
        await client.disconnect()

    return result


# ── WhatsApp ─────────────────────────────────────────────────────────────────

async def _lookup_whatsapp(phone: str, session: aiohttp.ClientSession) -> dict:
    sidecar_url = os.environ.get("WHATSAPP_SIDECAR_URL", "http://localhost:3333").rstrip("/")

    # WhatsApp expects E.164 without the +, e.g. 919876543210
    number = phone.lstrip("+")
    url = f"{sidecar_url}/lookup/{number}"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
    except aiohttp.ClientConnectorError:
        log.warning(
            "Phone: WhatsApp sidecar not reachable at %s — is wa_sidecar.js running?",
            sidecar_url,
        )
        return {}
    except Exception as exc:
        log.warning("Phone: WhatsApp sidecar error — %s", exc)
        return {}

    if not data.get("registered"):
        return {"whatsapp_registered": False}

    return {
        "whatsapp_registered":        True,
        "whatsapp_display_name":      data.get("name"),
        "whatsapp_profile_photo_url": data.get("profile_pic"),
        "whatsapp_about":             data.get("about"),
    }


# ── Web mentions (DuckDuckGo — free, no API key) ─────────────────────────────

def _lookup_web_mentions(phone: str) -> list:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        log.warning("Phone: duckduckgo-search not installed — pip install duckduckgo-search")
        return []

    query = f'"{phone}"'
    try:
        results = list(DDGS().text(query, max_results=10))
    except Exception as exc:
        log.warning("Phone: DuckDuckGo search failed — %s", exc)
        return []

    return [
        {
            "url":     r.get("href"),
            "title":   r.get("title"),
            "snippet": r.get("body"),
        }
        for r in results
    ]


# ── Public entry-point ────────────────────────────────────────────────────────

class PhoneCollector:
    """
    Aggregates public OSINT for a phone number across:
      - NumVerify (carrier / line type / country)
      - Telegram  (display name, username, profile photo)
      - WhatsApp  (display name, about, profile photo)
      - Web       (public mentions via SerpAPI or Google CSE)

    Input:  E.164 format recommended, e.g. +919876543210
            Bare numbers like 09876543210 are accepted but country prefix
            must be included for Telegram/WhatsApp lookups to work correctly.
    """

    async def collect(self, phone: str) -> PhoneProfile:
        # Normalise: strip whitespace/dashes, ensure leading +
        phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("+"):
            phone = "+" + phone

        log.info("Phone: looking up %s", phone)

        profile = PhoneProfile(phone_number=phone)

        async with aiohttp.ClientSession() as session:
            # WhatsApp needs aiohttp. DDG and phonenumbers are sync — run in executor.
            # Telegram uses its own connection (Telethon), run separately.
            loop = asyncio.get_event_loop()
            whatsapp_task = asyncio.create_task(_lookup_whatsapp(phone, session))
            web_task      = loop.run_in_executor(None, _lookup_web_mentions, phone)
            telegram_result = await _lookup_telegram(phone)

            numverify_result = _lookup_phonenumbers(phone)
            whatsapp_result  = await whatsapp_task
            web_result       = await web_task

        # Carrier / telco
        profile.valid        = numverify_result.get("valid")
        profile.country_code = numverify_result.get("country_code")
        profile.country_name = numverify_result.get("country_name")
        profile.location     = numverify_result.get("location")
        profile.carrier      = numverify_result.get("carrier")
        profile.line_type    = numverify_result.get("line_type")

        # Telegram
        profile.telegram_display_name      = telegram_result.get("telegram_display_name")
        profile.telegram_username          = telegram_result.get("telegram_username")
        profile.telegram_user_id           = telegram_result.get("telegram_user_id")
        profile.telegram_profile_photo_url = telegram_result.get("telegram_profile_photo_url")

        # WhatsApp
        profile.whatsapp_registered        = whatsapp_result.get("whatsapp_registered")
        profile.whatsapp_display_name      = whatsapp_result.get("whatsapp_display_name")
        profile.whatsapp_profile_photo_url = whatsapp_result.get("whatsapp_profile_photo_url")
        profile.whatsapp_about             = whatsapp_result.get("whatsapp_about")

        # Web mentions
        profile.web_mentions = web_result

        log.info(
            "Phone: %s — valid=%s carrier=%s TG=%s WA=%s mentions=%d",
            phone,
            profile.valid,
            profile.carrier,
            "yes" if profile.telegram_user_id else "no",
            "yes" if profile.whatsapp_registered else "no",
            len(profile.web_mentions),
        )

        return profile


def collect_phone(phone: str) -> PhoneProfile:
    """Synchronous wrapper — use from base.py or CLI."""
    return asyncio.run(PhoneCollector().collect(phone))
