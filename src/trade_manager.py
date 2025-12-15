import json
import os
import logging
import pytz
from datetime import datetime
import config

HISTORY_FILE = "trade_history.json"

class TradeManager:
    def __init__(self):
        self.history = self._load_history()

    def _load_history(self):
        if not os.path.exists(HISTORY_FILE):
            return {"holdings": {}, "last_trade": {}}
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"[TradeManager] Failed to load history: {e}")
            return {"holdings": {}, "last_trade": {}}

    def _save_history(self):
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"[TradeManager] Failed to save history: {e}")

    def update_buy(self, code, date_str):
        """Called upon successful buy."""
        # Clean date string just in case
        date_str = date_str.replace("-", "")
        self.history["holdings"][code] = {"buy_date": date_str}
        self._save_history()

    def update_sell(self, code, date_str, pnl_pct):
        """Called upon successful sell."""
        date_str = date_str.replace("-", "")
        
        # Record Last Trade
        self.history["last_trade"][code] = {
            "sell_date": date_str,
            "pnl_pct": float(pnl_pct)
        }
        
        # Remove from holdings
        if code in self.history["holdings"]:
            del self.history["holdings"][code]
            
        self._save_history()

    def get_holding_days(self, code, current_date_str=None):
        """Calculate how many days held."""
        # If unknown, treat as 0 days held (Do NOT Force Sell)
        if code not in self.history["holdings"]:
            return 0
            
        buy_date_str = self.history["holdings"][code].get("buy_date")
        if not buy_date_str:
             return 0
        
        # If current_date not passed, use today KST
        if not current_date_str:
            tz_kst = pytz.timezone('Asia/Seoul')
            current_date_str = datetime.now(pytz.utc).astimezone(tz_kst).strftime("%Y%m%d")
            
        try:
            d1 = datetime.strptime(buy_date_str, "%Y%m%d")
            d2 = datetime.strptime(current_date_str, "%Y%m%d")
            delta = (d2 - d1).days
            return delta
        except Exception as e:
            logging.error(f"[TradeManager] Date Calc Error ({code}): {e}")
            return 0

    def check_forced_sell(self, code):
        """
        Check if stock exceeded MAX_HOLDING_DAYS.
        Returns True if forced sell is needed.
        """
        days_held = self.get_holding_days(code)
        if days_held > config.MAX_HOLDING_DAYS:
            logging.info(f"[TradeManager] {code} Held {days_held} days > Max {config.MAX_HOLDING_DAYS}. Force Sell.")
            return True
        return False

    def can_buy(self, code):
        """
        Check if stock can be bought (Loss Cooldown).
        """
        if code not in self.history["last_trade"]:
            return True
        
        last_trade = self.history["last_trade"][code]
        pnl = last_trade["pnl_pct"]
        sell_date_str = last_trade["sell_date"]
        
        # If last trade was profitable (>= 0), no cooldown
        if pnl >= 0:
            return True
            
        # If Loss, check Cooldown
        tz_kst = pytz.timezone('Asia/Seoul')
        today_str = datetime.now(pytz.utc).astimezone(tz_kst).strftime("%Y%m%d")
        
        try:
            d1 = datetime.strptime(sell_date_str, "%Y%m%d")
            d2 = datetime.strptime(today_str, "%Y%m%d")
            days_passed = (d2 - d1).days
            
            if days_passed < config.LOSS_COOLDOWN_DAYS:
                logging.info(f"[TradeManager] {code} Cooldown Active: Loss {pnl}% ({days_passed}/{config.LOSS_COOLDOWN_DAYS} days)")
                return False
        except:
            return True # Fallback
            
        return True
