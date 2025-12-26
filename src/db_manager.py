import sqlite3
import datetime
import logging
from typing import List, Dict, Optional

DB_FILE = "stock_analysis.db"

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
                
                # Migration: Add specific_model column if it doesn't exist
                cursor.execute("PRAGMA table_info(ai_advice)")
                columns = [info[1] for info in cursor.fetchall()]
                if 'specific_model' not in columns:
                    logging.info("Migrating DB: Adding specific_model column to ai_advice")
                    cursor.execute("ALTER TABLE ai_advice ADD COLUMN specific_model TEXT")

                if 'prompt' not in columns:
                    logging.info("Migrating DB: Adding prompt column to ai_advice")
                    cursor.execute("ALTER TABLE ai_advice ADD COLUMN prompt TEXT")
                
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Init Error: {e}")





    def save_rsi_result(self, date: str, code: str, name: str, rsi: float, close_price: float):
        """Save a single RSI analysis record."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO daily_rsi (date, code, name, rsi, close_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (date, code, name, rsi, close_price))
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

    def get_low_rsi_candidates(self, date: str, threshold: float = 30.0) -> List[Dict]:
        """
        Get list of stocks with RSI < threshold for the given date.
        Returns list of dicts: {code, name, rsi, close_price}
        """
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT code, name, rsi, close_price
                    FROM daily_rsi
                    WHERE date = ? AND rsi < ?
                    ORDER BY rsi ASC
                """, (date, threshold))
                
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Low RSI Fetch Error: {e}")
        return results
