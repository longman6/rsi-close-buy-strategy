import re
import json
import os
import datetime

LOG_FILE = "logs/trade_log.txt"
HISTORY_FILE = "data/trade_history.json"

def parse_log():
    if not os.path.exists(LOG_FILE):
        print(f"Log file {LOG_FILE} not found.")
        return

    # Structure of history:
    # {
    #   "holdings": { "code": { "buy_date": "YYYYMMDD" } },
    #   "last_trade": { "code": { "sell_date": "YYYYMMDD", "pnl_pct": 0.0 } }
    # }
    
    history = {
        "holdings": {},
        "last_trade": {}
    }

    # Tracking temp storage
    # Store last seen P/L for codes to attach to Sell events
    last_seen_pnl = {} 

    pnl_pattern = re.compile(r"📊 .*?\((\d+)\): .*? P/L: .*? \(([-\d.]+)%\)")
    buy_pattern = re.compile(r"Order Success: BUY (\d+)")
    sell_pattern = re.compile(r"Order Success: SELL (\d+)")
    
    # We also need date from log line
    # Log format: 2025-12-09 02:22:18,062 ...
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                # Extract Date
                parts = line.split(' ')
                if len(parts) < 2: continue
                date_str = parts[0] # YYYY-MM-DD
                time_str = parts[1].split(',')[0] # HH:MM:SS
                
                # Normalize date format to YYYYMMDD
                clean_date = date_str.replace("-", "")
                
                # Check P/L (Monitor)
                # 📊 큐리언트(115180): ... P/L: ... (-5.38%)
                pnl_match = pnl_pattern.search(line)
                if pnl_match:
                    code = pnl_match.group(1)
                    pnl = float(pnl_match.group(2))
                    last_seen_pnl[code] = pnl
                    continue
                
                # Check Buy
                buy_match = buy_pattern.search(line)
                if buy_match:
                    code = buy_match.group(1)
                    # If not already recorded as holding or if we want latest
                    history["holdings"][code] = {"buy_date": clean_date}
                    continue
                
                # Check Sell
                sell_match = sell_pattern.search(line)
                if sell_match:
                    code = sell_match.group(1)
                    
                    # Get P/L
                    pnl = last_seen_pnl.get(code, 0.0)
                    
                    # Update last trade
                    history["last_trade"][code] = {
                        "sell_date": clean_date,
                        "pnl_pct": pnl
                    }
                    
                    # Remove from holdings if present
                    if code in history["holdings"]:
                        del history["holdings"][code]
                    continue
                    
            except Exception as e:
                # print(f"Error parsing line: {line.strip()} -> {e}")
                pass

    # Save to JSON
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)
    
    print(f"✅ Generated {HISTORY_FILE} from {LOG_FILE}")
    print(f"   Holdings: {len(history['holdings'])}")
    print(f"   Past Trades: {len(history['last_trade'])}")

if __name__ == "__main__":
    parse_log()
