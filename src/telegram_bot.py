
import requests
import config
from datetime import datetime

class TelegramBot:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = config.ENABLE_NOTIFICATIONS
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send_message(self, text):
        """
        Sends a message to Telegram.
        """
        if not self.enabled:
            return

        if not self.token or not self.chat_id:
            print("[Telegram] Config missing. Message skipped.")
            return

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML" # Optional: Use HTML for simple formatting
        }
        
        try:
            # Timeout set to 5 seconds to avoid hanging main loop
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code != 200:
                print(f"[Telegram] Failed to send: {response.text}")
        except Exception as e:
            print(f"[Telegram] Error: {e}")

if __name__ == "__main__":
    # Test
    bot = TelegramBot()
    bot.send_message("🤖 RSI Bot: Telegram Migration Test")
