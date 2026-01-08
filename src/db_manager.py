import sqlite3
import datetime
import logging
from typing import List, Dict, Optional

DB_FILE = "data/stock_analysis.db"

class DBManager:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self._initialize_db()

    def _initialize_db(self):
        """Initialize the database table if not exists."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()

                
                # New Simple RSI Table (Pure Data)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_rsi (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,          -- YYYY-MM-DD
                        code TEXT,          -- Stock Code
                        name TEXT,          -- Stock Name
                        rsi REAL,           -- RSI Value
                        close_price REAL,   -- Close Price
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Multi-LLM Advice Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_advice (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,          -- YYYY-MM-DD
                        code TEXT,          -- Stock Code
                        model TEXT,         -- AI Model Name (Gemini, Claude, etc)
                        recommendation TEXT,-- 'YES', 'NO'
                        reasoning TEXT,     -- Specific reasoning
                        specific_model TEXT, -- Specific Model ID (e.g. gemini-1.5-flash)
                        prompt TEXT,        -- The prompt used for analysis
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Trade History Table
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
                
                # Users Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Trading Journal Table
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
                
                # Migration: Add specific_model column if it doesn't exist
                cursor.execute("PRAGMA table_info(ai_advice)")
                columns = [info[1] for info in cursor.fetchall()]
                if 'specific_model' not in columns:
                    logging.info("Migrating DB: Adding specific_model column to ai_advice")
                    cursor.execute("ALTER TABLE ai_advice ADD COLUMN specific_model TEXT")

                if 'prompt' not in columns:
                    logging.info("Migrating DB: Adding prompt column to ai_advice")
                    cursor.execute("ALTER TABLE ai_advice ADD COLUMN prompt TEXT")
                
                # Migration: Add SMA columns to daily_rsi
                cursor.execute("PRAGMA table_info(daily_rsi)")
                rsi_columns = [info[1] for info in cursor.fetchall()]
                if 'sma' not in rsi_columns:
                    logging.info("Migrating DB: Adding sma column to daily_rsi")
                    cursor.execute("ALTER TABLE daily_rsi ADD COLUMN sma REAL")
                
                if 'is_above_sma' not in rsi_columns:
                    logging.info("Migrating DB: Adding is_above_sma column to daily_rsi")
                    cursor.execute("ALTER TABLE daily_rsi ADD COLUMN is_above_sma INTEGER")

                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Init Error: {e}")





    def save_rsi_result(self, date: str, code: str, name: str, rsi: float, close_price: float, sma: float = None, is_above_sma: bool = False):
        """Save a single RSI analysis record."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                is_above_int = 1 if is_above_sma else 0
                cursor.execute("""
                    INSERT INTO daily_rsi (date, code, name, rsi, close_price, sma, is_above_sma)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (date, code, name, rsi, close_price, sma, is_above_int))
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Save RSI Error: {e}")

    def get_rsi_by_date(self, date: str) -> List[Dict]:
        """Fetch all RSI records for a specific date."""
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM daily_rsi 
                    WHERE date = ? 
                    ORDER BY rsi ASC
                """, (date,))
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch RSI Error: {e}")
        return results

    def save_ai_advice(self, date: str, code: str, model: str, recommendation: str, reasoning: str, specific_model: str = None, prompt: str = None):
        """Save advice from a specific AI model."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ai_advice (date, code, model, recommendation, reasoning, specific_model, prompt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (date, code, model, recommendation, reasoning, specific_model, prompt))
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Save AI Advice Error: {e}")

    def save_trade_record(self, date: str, code: str, name: str, action: str, price: float, quantity: int, pnl_amt: float = 0.0, pnl_pct: float = 0.0):
        """Save a trade execution record (BUY/SELL)."""
        try:
            amount = float(price * quantity)
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trade_history (date, code, name, action, price, quantity, amount, pnl_amt, pnl_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (date, code, name, action, price, quantity, amount, pnl_amt, pnl_pct))
                conn.commit()
                logging.info(f"[DB] Saved {action} record for {name} ({code})")
        except Exception as e:
            logging.error(f"[DB] Save Trade Record Error: {e}")

    def get_ai_advice(self, date: str, code: str = None) -> List[Dict]:
        """Fetch AI advice for a date, optionally filtered by code."""
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if code:
                    cursor.execute("""
                        SELECT * FROM ai_advice 
                        WHERE date = ? AND code = ?
                    """, (date, code))
                else:
                    cursor.execute("""
                        SELECT * FROM ai_advice 
                        WHERE date = ? 
                    """, (date,))
                
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch AI Advice Error: {e}")
        return results

    def get_all_dates(self) -> List[str]:
        """Get unique dates available in DB (Merging both advice and rsi tables)."""
        dates = set()
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # From RSI
                cursor.execute("SELECT DISTINCT date FROM daily_rsi")
                dates.update([row[0] for row in cursor.fetchall()])
                
        except Exception as e:
            logging.error(f"[DB] Date Fetch Error: {e}")
        return sorted(list(dates), reverse=True)

    def get_consensus_candidates(self, date: str, min_votes: int = 4) -> set:
        """
        Get set of stock codes that have at least `min_votes` 'YES' recommendations 
        from DIFFERENT models for the given date.
        """
        candidates = set()
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # Group by code and count distinct models that said YES
                # assuming 'recommendation' is stored as 'YES'
                cursor.execute("""
                    SELECT code, COUNT(DISTINCT model) as vote_count
                    FROM ai_advice
                    WHERE date = ? AND recommendation = 'YES'
                    GROUP BY code
                    HAVING vote_count >= ?
                """, (date, min_votes))
                
                rows = cursor.fetchall()
                candidates = {row[0] for row in rows}
                
                if candidates:
                    logging.info(f"[DB] Consensus ({min_votes}+ votes) found for: {candidates}")
                    
        except Exception as e:
            logging.error(f"[DB] Consensus Fetch Error: {e}")
        return candidates

    def get_low_rsi_candidates(self, date: str, threshold: float = 30.0, min_sma_check: bool = False) -> List[Dict]:
        """
        Get list of stocks with RSI < threshold for the given date.
        Returns list of dicts: {code, name, rsi, close_price, sma, is_above_sma}
        """
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = """
                    SELECT code, name, rsi, close_price, sma, is_above_sma
                    FROM daily_rsi
                    WHERE date = ? AND rsi < ?
                """
                params = [date, threshold]
                
                if min_sma_check:
                    query += " AND is_above_sma = 1"
                    
                query += " ORDER BY rsi ASC"
                
                cursor.execute(query, params)
                
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Low RSI Fetch Error: {e}")
        return results

    def get_trade_history(self) -> List[Dict]:
        """Fetch all trade execution records sorted by date descending."""
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM trade_history 
                    ORDER BY date DESC, id DESC
                """)
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch Trade History Error: {e}")
        return results

    # --- User Management ---
    def create_user(self, username, password_hash):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"[DB] Create User Error: {e}")
            return False

    def get_user(self, username):
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logging.error(f"[DB] Get User Error: {e}")
        return None

    def update_password(self, username, new_password_hash):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_password_hash, username))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"[DB] Update Password Error: {e}")
            return False

    # --- Trading Journal ---
    def save_journal_entry(self, date: str, total_balance: float, daily_profit_loss: float, daily_return_pct: float, holdings_snapshot: str):
        """Save or Update daily journal entry (excluding notes if exists, or keep it)."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # Check if exists to preserve notes
                cursor.execute("SELECT notes FROM trading_journal WHERE date = ?", (date,))
                row = cursor.fetchone()
                
                if row:
                    # Update fields except notes
                    cursor.execute("""
                        UPDATE trading_journal 
                        SET total_balance=?, daily_profit_loss=?, daily_return_pct=?, holdings_snapshot=?
                        WHERE date=?
                    """, (total_balance, daily_profit_loss, daily_return_pct, holdings_snapshot, date))
                else:
                    # Insert new
                    cursor.execute("""
                        INSERT INTO trading_journal (date, total_balance, daily_profit_loss, daily_return_pct, holdings_snapshot)
                        VALUES (?, ?, ?, ?, ?)
                    """, (date, total_balance, daily_profit_loss, daily_return_pct, holdings_snapshot))
                conn.commit()
                logging.info(f"[DB] Saved Journal Entry for {date}")
        except Exception as e:
            logging.error(f"[DB] Save Journal Error: {e}")

    def update_journal_note(self, date: str, note: str):
        """Update the note for a specific date."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # Use UPSERT logic or just Update? Better only Update if row exists?
                # Actually user might write note before snapshot.
                cursor.execute("SELECT 1 FROM trading_journal WHERE date = ?", (date,))
                if cursor.fetchone():
                    cursor.execute("UPDATE trading_journal SET notes = ? WHERE date = ?", (note, date))
                else:
                    # Create empty entry with note
                    cursor.execute("INSERT INTO trading_journal (date, notes) VALUES (?, ?)", (date, note))
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Update Note Error: {e}")

    def get_journal_entry(self, date: str) -> Optional[Dict]:
        """Get journal entry for a specific date."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trading_journal WHERE date = ?", (date,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logging.error(f"[DB] Get Journal Error: {e}")
        return None

    def get_all_journal_entries(self) -> List[Dict]:
        """Get all journal entries sorted by date desc."""
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trading_journal ORDER BY date DESC")
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Get All Journals Error: {e}")
        return results
