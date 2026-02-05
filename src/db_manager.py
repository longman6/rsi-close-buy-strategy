import sqlite3
import datetime
import logging
import os
import config
from typing import List, Dict, Optional

MARKET_DB_FILE = "data/stock_analysis.db"
# User DB path from config, default if not set
USER_DB_FILE = getattr(config, 'USER_DB_PATH', "data/user_data.db")

class DBManager:
    def __init__(self, market_db=MARKET_DB_FILE, user_db=USER_DB_FILE):
        self.market_db = market_db
        self.user_db = user_db
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.user_db), exist_ok=True)
        
        self._initialize_db()

    def _initialize_db(self):
        """Initialize both database tables if not exist."""
        try:
            # --- 1. Market Data DB ---
            with sqlite3.connect(self.market_db) as conn:
                cursor = conn.cursor()
                
                # daily_rsi
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_rsi (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,          -- YYYY-MM-DD
                        code TEXT,          -- Stock Code
                        name TEXT,          -- Stock Name
                        rsi REAL,           -- RSI Value
                        close_price REAL,   -- Close Price
                        sma REAL,           -- SMA Value
                        is_above_sma INTEGER, -- 1 or 0
                        is_low_rsi INTEGER,   -- 1 or 0
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # ai_advice
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_advice (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,          -- YYYY-MM-DD
                        code TEXT,          -- Stock Code
                        model TEXT,         -- AI Model Name
                        recommendation TEXT,-- 'YES', 'NO'
                        reasoning TEXT,     -- Specific reasoning
                        specific_model TEXT,
                        prompt TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                
            # --- 2. User Data DB ---
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()

                # trade_history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trade_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,          -- YYYY-MM-DD
                        code TEXT,          -- Stock Code
                        name TEXT,          -- Stock Name
                        action TEXT,        -- 'BUY' or 'SELL'
                        price REAL,         -- Execution Price
                        quantity INTEGER,   -- Executed Quantity
                        amount REAL,        -- Total Amount
                        pnl_amt REAL,       -- Profit/Loss Amount (for SELL)
                        pnl_pct REAL,       -- Profit/Loss Percentage (for SELL)
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # users
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # trading_journal
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trading_journal (
                        date TEXT PRIMARY KEY,   -- YYYY-MM-DD
                        total_balance REAL,      -- Total Assets (Equity)
                        daily_profit_loss REAL,  -- Daily P/L Amount
                        daily_return_pct REAL,   -- Daily Return %
                        holdings_snapshot TEXT,  -- JSON or Formatted String of Holdings
                        notes TEXT,              -- User's Manual Note
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

            # --- Migrations (Check Logic) ---
            # Market DB Migrations
            with sqlite3.connect(self.market_db) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(daily_rsi)")
                cols = [info[1] for info in cursor.fetchall()]
                if 'sma' not in cols:
                    logging.info("Migrating Market DB: Adding sma to daily_rsi")
                    cursor.execute("ALTER TABLE daily_rsi ADD COLUMN sma REAL")
                if 'is_above_sma' not in cols:
                    logging.info("Migrating Market DB: Adding is_above_sma to daily_rsi")
                    cursor.execute("ALTER TABLE daily_rsi ADD COLUMN is_above_sma INTEGER")
                if 'is_low_rsi' not in cols:
                    logging.info("Migrating Market DB: Adding is_low_rsi to daily_rsi")
                    cursor.execute("ALTER TABLE daily_rsi ADD COLUMN is_low_rsi INTEGER")

                cursor.execute("PRAGMA table_info(ai_advice)")
                cols = [info[1] for info in cursor.fetchall()]
                if 'specific_model' not in cols:
                     cursor.execute("ALTER TABLE ai_advice ADD COLUMN specific_model TEXT")
                if 'prompt' not in cols:
                     cursor.execute("ALTER TABLE ai_advice ADD COLUMN prompt TEXT")
                conn.commit()
                
        except Exception as e:
            logging.error(f"[DB] Init Error: {e}")

    # --- Market DB Methods ---
    def save_rsi_result(self, date: str, code: str, name: str, rsi: float, close_price: float, sma: float = None, is_above_sma: bool = False, is_low_rsi: bool = False):
        try:
            with sqlite3.connect(self.market_db) as conn:
                cursor = conn.cursor()
                # 기존 데이터 삭제 (덮어쓰기)
                cursor.execute("DELETE FROM daily_rsi WHERE date = ? AND code = ?", (date, code))
                
                is_above_int = 1 if is_above_sma else 0
                is_low_int = 1 if is_low_rsi else 0
                cursor.execute("""
                    INSERT INTO daily_rsi (date, code, name, rsi, close_price, sma, is_above_sma, is_low_rsi)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (date, code, name, rsi, close_price, sma, is_above_int, is_low_int))
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Save RSI Error: {e}")

    def get_rsi_by_date(self, date: str) -> List[Dict]:
        results = []
        try:
            with sqlite3.connect(self.market_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM daily_rsi WHERE date = ? ORDER BY rsi ASC", (date,))
                for row in cursor.fetchall():
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch RSI Error: {e}")
        return results

    def save_ai_advice(self, date: str, code: str, model: str, recommendation: str, reasoning: str, specific_model: str = None, prompt: str = None):
        try:
            with sqlite3.connect(self.market_db) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ai_advice (date, code, model, recommendation, reasoning, specific_model, prompt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (date, code, model, recommendation, reasoning, specific_model, prompt))
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Save AI Advice Error: {e}")

    def get_ai_advice(self, date: str, code: str = None) -> List[Dict]:
        results = []
        try:
            with sqlite3.connect(self.market_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if code:
                    cursor.execute("SELECT * FROM ai_advice WHERE date = ? AND code = ?", (date, code))
                else:
                    cursor.execute("SELECT * FROM ai_advice WHERE date = ?", (date,))
                for row in cursor.fetchall():
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch AI Advice Error: {e}")
        return results

    def get_all_dates(self) -> List[str]:
        dates = set()
        try:
            with sqlite3.connect(self.market_db) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT date FROM daily_rsi")
                dates.update([row[0] for row in cursor.fetchall()])
        except Exception as e:
            logging.error(f"[DB] Date Fetch Error: {e}")
        return sorted(list(dates), reverse=True)

    def get_consensus_candidates(self, date: str, min_votes: int = 4) -> set:
        candidates = set()
        try:
            with sqlite3.connect(self.market_db) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT code, COUNT(DISTINCT model) as vote_count
                    FROM ai_advice
                    WHERE date = ? AND recommendation = 'YES'
                    GROUP BY code
                    HAVING vote_count >= ?
                """, (date, min_votes))
                candidates = {row[0] for row in cursor.fetchall()}
                if candidates:
                    logging.info(f"[DB] Consensus ({min_votes}+ votes) found for: {candidates}")
        except Exception as e:
            logging.error(f"[DB] Consensus Fetch Error: {e}")
        return candidates

    def get_low_rsi_candidates(self, date: str, threshold: float = 30.0, min_sma_check: bool = False) -> List[Dict]:
        results = []
        try:
            with sqlite3.connect(self.market_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                query = "SELECT code, name, rsi, close_price, sma, is_above_sma FROM daily_rsi WHERE date = ? AND rsi < ?"
                params = [date, threshold]
                if min_sma_check:
                    query += " AND is_above_sma = 1"
                query += " ORDER BY rsi ASC"
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Low RSI Fetch Error: {e}")
        return results

    # --- User Data DB Methods ---
    def save_trade_record(self, date: str, code: str, name: str, action: str, price: float, quantity: int, pnl_amt: float = 0.0, pnl_pct: float = 0.0):
        try:
            # 중복 체크: 동일 날짜, 종목, 작업이 이미 있는지 확인
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM trade_history 
                    WHERE date = ? AND code = ? AND action = ?
                """, (date, code, action))
                if cursor.fetchone():
                    logging.info(f"[DB] Trade record already exists for {name} ({code}) {action} on {date}. Skipping.")
                    return

                amount = float(price * quantity)
                cursor.execute("""
                    INSERT INTO trade_history (date, code, name, action, price, quantity, amount, pnl_amt, pnl_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (date, code, name, action, price, quantity, amount, pnl_amt, pnl_pct))
                conn.commit()
                logging.info(f"[DB] Saved {action} record for {name} ({code})")
        except Exception as e:
            logging.error(f"[DB] Save Trade Record Error: {e}")

    def get_trade_history(self) -> List[Dict]:
        results = []
        try:
            with sqlite3.connect(self.user_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trade_history ORDER BY date DESC, id DESC")
                for row in cursor.fetchall():
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch Trade History Error: {e}")
        return results

    def has_trade_history_for_date(self, date: str) -> bool:
        """해당 날짜에 거래 기록이 한 건이라도 있는지 확인"""
        try:
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM trade_history WHERE date = ? LIMIT 1", (date,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"[DB] Check Trade History Error: {e}")
            return False

    def create_user(self, username, password_hash):
        try:
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"[DB] Create User Error: {e}")
            return False

    def get_user(self, username):
        try:
            with sqlite3.connect(self.user_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
                row = cursor.fetchone()
                if row: return dict(row)
        except Exception as e:
            logging.error(f"[DB] Get User Error: {e}")
        return None

    def update_password(self, username, new_password_hash):
        try:
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_password_hash, username))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"[DB] Update Password Error: {e}")
            return False

    def save_journal_entry(self, date: str, total_balance: float, daily_profit_loss: float, daily_return_pct: float, holdings_snapshot: str):
        try:
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT notes FROM trading_journal WHERE date = ?", (date,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        UPDATE trading_journal 
                        SET total_balance=?, daily_profit_loss=?, daily_return_pct=?, holdings_snapshot=?
                        WHERE date=?
                    """, (total_balance, daily_profit_loss, daily_return_pct, holdings_snapshot, date))
                else:
                    cursor.execute("""
                        INSERT INTO trading_journal (date, total_balance, daily_profit_loss, daily_return_pct, holdings_snapshot)
                        VALUES (?, ?, ?, ?, ?)
                    """, (date, total_balance, daily_profit_loss, daily_return_pct, holdings_snapshot))
                conn.commit()
                logging.info(f"[DB] Saved Journal Entry for {date}")
        except Exception as e:
            logging.error(f"[DB] Save Journal Error: {e}")

    def update_journal_note(self, date: str, note: str):
        try:
            with sqlite3.connect(self.user_db) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM trading_journal WHERE date = ?", (date,))
                if cursor.fetchone():
                    cursor.execute("UPDATE trading_journal SET notes = ? WHERE date = ?", (note, date))
                else:
                    cursor.execute("INSERT INTO trading_journal (date, notes) VALUES (?, ?)", (date, note))
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Update Note Error: {e}")

    def get_journal_entry(self, date: str) -> Optional[Dict]:
        try:
            with sqlite3.connect(self.user_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trading_journal WHERE date = ?", (date,))
                row = cursor.fetchone()
                if row: return dict(row)
        except Exception as e:
            logging.error(f"[DB] Get Journal Error: {e}")
        return None

    def get_all_journal_entries(self) -> List[Dict]:
        results = []
        try:
            with sqlite3.connect(self.user_db) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trading_journal ORDER BY date DESC")
                for row in cursor.fetchall():
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Get All Journals Error: {e}")
        return results
