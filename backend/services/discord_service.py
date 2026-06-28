import json
import os
from urllib.request import Request, urlopen


def send_discord_log(title, message):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    if not webhook_url:
        return False

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": 15950948,
        }]
    }
    request = Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=5):
            return True
    except Exception as error:
        print("Discord webhook failed:", error)
        return False
