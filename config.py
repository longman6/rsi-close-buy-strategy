import os
from dotenv import load_dotenv

load_dotenv()

# KIS Credentials
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_CANO = os.getenv("KIS_CANO", "")
KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")
KIS_URL_BASE = os.getenv("KIS_URL_BASE", "https://openapi.koreainvestment.com:9443")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"

# Slack (Deprecated)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#general")

# Strategy Constants
RSI_WINDOW = int(os.getenv("RSI_WINDOW", 3))
SMA_WINDOW = int(os.getenv("SMA_WINDOW", 100))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", 5))
RSI_BUY_THRESHOLD = float(os.getenv("RSI_BUY_THRESHOLD", 35))
RSI_SELL_THRESHOLD = float(os.getenv("RSI_SELL_THRESHOLD", 70))

MAX_HOLDING_DAYS = int(os.getenv("MAX_HOLDING_DAYS", 38))
LOSS_COOLDOWN_DAYS = int(os.getenv("LOSS_COOLDOWN_DAYS", 40))

# Trading Config
# ALLOCATION_PCT = float(os.getenv("ALLOCATION_PCT", 0.20)) # Deprecated
BUY_AMOUNT_KRW = int(os.getenv("BUY_AMOUNT_KRW", 1000000)) # Default 1 Million KRW per stock

# Scheduler Settings (24h format HH:MM)
TIME_MORNING_ANALYSIS = os.getenv("TIME_MORNING_ANALYSIS", "08:30")
TIME_PRE_ORDER = os.getenv("TIME_PRE_ORDER", "08:57")
TIME_ORDER_CHECK = os.getenv("TIME_ORDER_CHECK", "09:05")
TIME_SELL_CHECK = os.getenv("TIME_SELL_CHECK", "15:20")
TIME_SELL_EXEC = os.getenv("TIME_SELL_EXEC", "15:26")

# Split Buy Order Settings
FIRST_ORDER_RATIO = float(os.getenv("FIRST_ORDER_RATIO", 0.5))  # Default 50%
SECOND_ORDER_TIME = os.getenv("SECOND_ORDER_TIME", "09:30")
