import sqlite3
import datetime
import logging
from typing import List, Dict, Optional

DB_FILE = "advice_history.db"

class DBManager:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self._initialize_db()

    def _initialize_db(self):
        """Initialize the database table if not exists."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS advice_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,          -- YYYY-MM-DD
                        code TEXT,          -- Stock Code
                        name TEXT,          -- Stock Name
                        rsi REAL,           -- RSI Value
                        recommendation TEXT,-- 'YES' or 'NO'
                        reasoning TEXT,     -- Detailed Reasoning
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logging.error(f"[DB] Init Error: {e}")

    def save_advice(self, date: str, code: str, name: str, rsi: float, recommendation: str, reasoning: str):
        """Save a single advice record."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO advice_results (date, code, name, rsi, recommendation, reasoning)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (date, code, name, rsi, recommendation, reasoning))
                conn.commit()
                logging.info(f"[DB] Saved advice for {name} ({code}): {recommendation}")
        except Exception as e:
            logging.error(f"[DB] Save Error: {e}")

    def get_advice_by_date(self, date: str) -> List[Dict]:
        """Fetch all advice records for a specific date."""
        results = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM advice_results 
                    WHERE date = ? 
                    ORDER BY id DESC
                """, (date,))
                rows = cursor.fetchall()
                for row in rows:
                    results.append(dict(row))
        except Exception as e:
            logging.error(f"[DB] Fetch Error: {e}")
        return results

    def get_all_dates(self) -> List[str]:
        """Get unique dates available in DB."""
        dates = []
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT date FROM advice_results ORDER BY date DESC")
                dates = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"[DB] Date Fetch Error: {e}")
        return dates
