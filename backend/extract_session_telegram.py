from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
import os

load_dotenv()

with TelegramClient(
    StringSession(),
    os.environ.get("TELEGRAM_API_ID"),
    os.environ.get("TELEGRAM_API_HASH"),
) as client:
    print(client.session.save())
