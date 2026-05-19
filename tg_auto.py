import requests
import config

def send_telegram_message(link_url: str):
    url = f"https://api.telegram.org/bot{config.TG_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": config.TG_CHAT_ID,
        "text": "🔥 New Tweet Alert Panda's 🐼",
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

    response = requests.post(
        url,
        json=payload
    )
    print(f"Telegram Automation: {response.status_code}")
