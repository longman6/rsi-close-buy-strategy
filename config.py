import os
from dotenv import load_dotenv

load_dotenv()

# KIS Credentials
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_CANO = os.getenv("KIS_CANO", "")
KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")
KIS_URL_BASE = os.getenv("KIS_URL_BASE", "https://openapi.koreainvestment.com:9443")

# Slack
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#general")

# Strategy Constants
RSI_WINDOW = int(os.getenv("RSI_WINDOW", 3))
SMA_WINDOW = int(os.getenv("SMA_WINDOW", 100))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", 5))

# Trading Config
ALLOCATION_PCT = float(os.getenv("ALLOCATION_PCT", 0.20)) # 20% by default
