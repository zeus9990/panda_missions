import httpx
import re
from config import TG_BOT_TOKEN, TG_CHAT_ID

async def send_telegram_message(message):
    urls = re.findall(r'(https?://\S+)',message)
    if not urls:
        return
    msg_url = urls[0]
    link_url = msg_url.replace("https://x.com/","https://twitter.com/")

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    text = f"🔥 New Tweet Alert Panda's 🐼\n\n{link_url}"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "link_preview_options": {
            "is_disabled": False,
            "prefer_large_media": True,
            "show_above_text": False
        },
        "reply_markup": {
            "inline_keyboard": [
                [
                    {
                        "text": "View Tweet 𝕏 ",
                        "url": link_url
                    }
                ]
            ]
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
    print(f"Telegram Automation: {response.status_code}")