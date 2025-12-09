import requests
import json
import config

class SlackBot:
    def __init__(self):
        self.webhook_url = config.SLACK_WEBHOOK_URL
        self.enabled = True
        
    def send_message(self, text):
        """
        Sends a message to Slack via Webhook.
        """
        if not self.enabled:
            return

        if not self.webhook_url:
            print("[Slack] No Webhook URL configured. Message not sent.")
            return

        payload = {"text": text}
        try:
            response = requests.post(
                self.webhook_url, 
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code != 200:
                print(f"[Slack] Failed to send message: {response.text}")
        except Exception as e:
            print(f"[Slack] Error sending message: {e}")

if __name__ == "__main__":
    # Test
    bot = SlackBot()
    bot.send_message("RSI Bot Initialized [Test]")
