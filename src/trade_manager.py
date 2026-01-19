import json
import os
import logging
import pytz
from datetime import datetime
import pandas as pd
import config

HISTORY_FILE = "data/trade_history.json"

class TradeManager:
    def __init__(self, db=None):
        self.history = self._load_history()
        self.db = db

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

    def update_buy(self, code, name, date_str, price, qty):
        """Called upon successful buy."""
        # Clean date string just in case
        date_str = date_str.replace("-", "")
        self.history["holdings"][code] = {"buy_date": date_str}
        self._save_history()
        
        # Save to DB if available
        if self.db:
            # Convert YYYYMMDD back to YYYY-MM-DD for DB consistency if needed
            db_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            self.db.save_trade_record(db_date, code, name, "BUY", float(price), int(qty))

    def update_sell(self, code, name, date_str, price, qty, pnl_pct):
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

        # Save to DB if available
        if self.db:
            db_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            # Calculate pnl_amt if we want it in DB (optional since we have avg price in balance, but here we just pass it)
            # Actually, main.py calculates pnl_pct. Let's assume we might want pnl_amt later.
            # Simplified: just save pct for now as passed.
            self.db.save_trade_record(db_date, code, name, "SELL", float(price), int(qty), pnl_pct=float(pnl_pct))

    def get_holding_days(self, code, current_date_str=None, df=None):
        """
        보유 일수 계산.
        - df(OHLCV 데이터)가 제공되면: 영업일(Trading Days) 기준
        - df가 없으면: 캘린더 일수(Calendar Days) 기준 (Fallback)
        """
        # If unknown, treat as 0 days held (Do NOT Force Sell)
        if code not in self.history["holdings"]:
            return 0
            
        buy_date_str = self.history["holdings"][code].get("buy_date")
        if not buy_date_str:
             return 0
        
        # 1. Trading Days Calculation (Preferred)
        if df is not None and not df.empty:
            try:
                # Expecting df.index to be DatetimeIndex
                # buy_date_str is 'YYYYMMDD'
                buy_dt = pd.to_datetime(buy_date_str)
                
                # Count bars strictly AFTER buy date
                # Support both DatetimeIndex and 'Date' column
                if isinstance(df.index, pd.DatetimeIndex):
                    trading_days = df[df.index > buy_dt]
                elif 'Date' in df.columns:
                    # Ensure Date column is datetime
                    if not pd.api.types.is_datetime64_any_dtype(df['Date']):
                        df['Date'] = pd.to_datetime(df['Date'])
                    trading_days = df[df['Date'] > buy_dt]
                else:
                    # Fallback or invalid DF structure
                    logging.warning(f"[TradeManager] DF has no Date index or column for {code}")
                    return 0 # Fallback to 0 or calendar days? Let's fallback to calendar days logic below if this returns 0? 
                    # Actually structure implies we return len. 
                    # If we return 0 here, it might be misleading. 
                    # Raise exception to trigger fallback in except block?
                    raise ValueError("No Date information in DataFrame")
                    
                return len(trading_days)
            except Exception as e:
                logging.error(f"[TradeManager] DF Date Calc Error ({code}): {e}")
                # Fallback to calendar days
        
        # 2. Calendar Days Calculation (Fallback)
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

    def check_forced_sell(self, code, df=None):
        """
        Check if stock exceeded MAX_HOLDING_DAYS.
        Returns True if forced sell is needed.
        """
        days_held = self.get_holding_days(code, df=df)
        if days_held > config.MAX_HOLDING_DAYS:
            logging.info(f"[TradeManager] {code} Held {days_held} days (Trading Days) > Max {config.MAX_HOLDING_DAYS}. Force Sell.")
            return True
        return False

    def can_buy(self, code):
        """
        매수 가능 여부 확인 (손실 후 쿨다운 체크).
        - 기준: 캘린더 일수 (Calendar Days)
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
