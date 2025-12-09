import sys
import time
import pandas as pd
import logging
from datetime import datetime
import config
from src.kis_client import KISClient
from src.slack_bot import SlackBot
from src.strategy import Strategy

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("trade_log.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    logging.info("Starting RSI Power Zone Bot...")
    
    # 1. Initialize Components
    kis = KISClient()
    slack = SlackBot()

    # Disable Slack in Mock Mode (Dev Environment)
    # Disable Slack in Mock Mode (Dev Environment)
    if kis.is_mock:
        logging.info("[Main] Mock Investment Mode detected. Slack notifications DISABLED.")
        slack.enabled = False
        delay_time = 1.0 # Slow down for Mock (Rate Limit strict)
    else:
        delay_time = 0.1 # Fast for Real
    
    slack.send_message("🚀 RSI Power Zone Bot Started")
    
    strategy = Strategy()
    
    # 2. Get Account Balance
    balance = kis.get_balance()
    if not balance:
        msg = "❌ Failed to fetch account balance. Terminating."
        logging.error(msg)
        slack.send_message(msg)
        return

    cash_available = balance['cash_available']
    logging.info(f"Cash Available: {cash_available:,.0f} KRW, Total Asset: {balance['total_asset']:,.0f} KRW")
    
    # 3. Check Sell Signals (Existing Holdings)
    holdings = balance['holdings']
    logging.info(f"Checking {len(holdings)} holdings for sell signals...")
    
    for item in holdings:
        code = item['pdno'] # Product Number
        name = item['prdt_name']
        qty = int(item['hldg_qty'])
        if qty == 0: continue
        
        curr_price = float(item['prpr']) # Current Price
        buy_price = float(item['pchs_avg_pric'])
        
        # Get Data
        df = kis.get_daily_ohlcv(code)
        df = strategy.calculate_indicators(df)
        
        # Check Sell
        should_sell = strategy.check_sell_signal(code, df)
        if should_sell:
            msg = f"📉 Sell Signal: {name} ({code}) RSI > 70. Executing Sell."
            logging.info(msg)
            slack.send_message(msg)
            
            # Execute Sell
            success, result_msg = kis.send_order(code, qty, side="sell")
            if success:
                slack.send_message(f"✅ Sold {name}: {result_msg}")
            else:
                slack.send_message(f"❌ Sell Failed {name}: {result_msg}")
        else:
            if not df.empty:
                logging.info(f"Hold: {name} (RSI: {df.iloc[-1]['RSI']:.2f} if valid)")
            else:
                logging.warning(f"Hold: {name} (Data fetch failed or insufficient)")

    # 4. Strategy Analysis (Buy Signals)
    # Only if we have slots available
    # Actually, we should check current slots count accurately.
    # Re-fetch balance/holdings or just count remaining from loop?
    # KIS holdings update might be slightly delayed if we just sold, 
    # but 'send_order' is async essentially.
    
    # Let's count current positions (assuming sells go through, slots open up? 
    # No, settlement takes time (D+2), but Buying Power (deposit) updates differently.
    # We'll stick to: Start with logic "Target 5 stocks". 
    # If we have 3 stocks, we can buy 2 more.
    
    # Note: KIS 'cash_available' (dnca_tot_amt) is the deposit. 
    # We should trust it for purchasing power.
    
    current_holdings_count = len([h for h in holdings if int(h['hldg_qty']) > 0]) # Crude count
    # Note: We should ideally track 'pending sells' too, but for simplicity:
    
    target_positions = config.MAX_POSITIONS
    slots_open = target_positions - current_holdings_count
    
    if slots_open <= 0:
        msg = f"full Portfolio ({current_holdings_count}/{target_positions}). No new buys."
        logging.info(msg)
        slack.send_message(msg)
        return

    logging.info(f"Searching for Buy Candidates... (Slots Open: {slots_open})")
    
    # Get Universe
    universe = strategy.get_universe()
    if not universe:
        slack.send_message("❌ Failed to get Universe.")
        return
        
    logging.info(f"Universe Size: {len(universe)} (KOSDAQ Top)")
    
    candidates = []
    
    # Analyze Universe
    # IMPORTANT: API Rate Limit. KIS is ~20/sec? 
    # 150 requests might take ~10-20s. Add small sleep if needed.
    
    cnt = 0
    for code in universe:
        # Skip if already holding
        if any(h['pdno'] == code for h in holdings):
            continue
            
        # Optional: Check 'Managed' state via KIS if not trusted FDR?
        # Implicitly done by FDR 'Dept' check in strategy.py
        
        # Optimize: Fetch only last 250 days (approx 1 year) which is enough for SMA100
        # This significantly reduces API load compared to full history.
        start_date = (datetime.now() - pd.Timedelta(days=250)).strftime("%Y%m%d")
        df = kis.get_daily_ohlcv(code, start_date=start_date)
        if df.empty: continue
        
        df = strategy.calculate_indicators(df)
        signal = strategy.analyze_stock(code, df)
        
        if signal:
            # Add simple Name lookup if possible? 
            # We don't have name easily without another query.
            signal['name'] = code # Placeholder
            candidates.append(signal)
            logging.info(f"Found Candidate: {code} RSI={signal['rsi']:.2f}")
            
        cnt += 1
        # Rate limit throttling
        # Mock mode needs 1.5s to avoid 500 errors, Real mode can be 0.2s
        delay = 1.5 if kis.is_mock else 0.2
        time.sleep(delay)
        
        if cnt % 10 == 0:
            logging.info(f"Analyzed {cnt}/{len(universe)} stocks...")

    # Sort Candidates by RSI (Ascending - Lower is better)
    candidates.sort(key=lambda x: x['rsi'])
    
    # Pick Top N
    final_buys = candidates[:slots_open]
    
    if not final_buys:
        slack.send_message("ℹ️ No Buy Candidates found today.")
        return
        
    slack.send_message(f"🔍 Found {len(final_buys)} Buy Candidates. Executing...")
    
    # Snapshot cash for even distribution
    # If we have 3 candidates and 10M cash, allocate 3.33M each.
    initial_cash_for_allocation = cash_available
    
    for item in final_buys:
        code = item['code']
        rsi_val = item['rsi']
        
        # Calculate Order Qty
        # User Request: "Use remaining cash... additional buy by ratio"
        # Interpretation: Distribute ALL available cash equally among the selected candidates.
        
        num_candidates = len(final_buys)
        # Use initial snapshot to ensure equal distribution
        target_amt_per_stock = initial_cash_for_allocation / num_candidates
        
        # Buffer for fees (0.2% safe)
        invest_amt = target_amt_per_stock * 0.998
        
        # Get Current Price (Yesterday Close)
        ref_price = item['close'] 
        
        # [Margin Issue] Market Order usually requires Cash for Upper Limit (+30%).
        # Solution: Use Limit Order at +15% of Close. 
        # This acts like Market Order (executes at Open price) but requires less margin.
        raw_limit_price = int(ref_price * 1.15)
        limit_price = kis.get_valid_price(raw_limit_price)
        
        # Calculate Qty based on Limit Price (to be safe on margin)
        qty = int(invest_amt / limit_price)
        
        if qty < 1:
            logging.info(f"Qty too small for {code} (InvestAmt: {invest_amt:,.0f}, LimitPrice: {limit_price})")
            continue
            
        # Check cash again
        est_cost = qty * limit_price # Max possible cost
        if est_cost > cash_available:
             # Reduce qty if needed (margin buffer)
             qty = int(cash_available / limit_price)
             if qty < 1: continue

        # Execute Buy (Limit Order at +15%)
        msg = f"🚀 Buying {code} (RSI: {rsi_val:.2f}) Qty: {qty} @ Limit {limit_price} (+15%)"
        logging.info(msg)
        slack.send_message(msg)
        
        # Price > 0 implies Limit Order in kis_client ("00")
        success, result_msg = kis.send_order(code, qty, side="buy", price=limit_price)
        if success:
             slack.send_message(f"✅ Buy Order Placed: {code}")
             # Deduct estimate cost (Use Limit Price for safety in local tracking)
             cash_available -= (qty * limit_price * 1.00015)
        else:
             slack.send_message(f"❌ Buy Failed {code}: {result_msg}")
             
        time.sleep(delay_time) # Rate limit throttling for orders

    # =========================================================
    # Phase 2: Wait for Market Open & Re-allocate Remaining Cash
    # =========================================================


    
    logging.info("\n[Phase 2] Waiting for Market Open to use remaining cash...")
    
    # Wait until 09:00:10 (Give 10s buffer for execution)
    # If Mock Mode, skip waiting for immediate debugging
    if kis.is_mock:
         logging.info("[Debug] Mock Mode: Skipping wait for market open.")
    else:
        target_time_str = datetime.now().strftime("%Y-%m-%d") + " 09:00:10"
        target_time = datetime.strptime(target_time_str, "%Y-%m-%d %H:%M:%S")
        
        while True:
            now = datetime.now()
            if now >= target_time:
                break
            
            remaining = (target_time - now).total_seconds()
            if remaining > 60:
                logging.info(f"Waiting... {int(remaining)}s left")
                time.sleep(60)
            else:
                logging.info(f"Waiting... {int(remaining)}s left")
                time.sleep(remaining if remaining > 0 else 0)
                break
            
    logging.info("🔔 Market Open! checking remaining cash...")
    slack.send_message("🔔 Market Open! Re-calculating for remaining cash...")
    
    # Re-fetch Balance (Actual execution result)
    time.sleep(2) # Extra buffer
    balance = kis.get_balance()
    if not balance:
        logging.error("Failed to fetch balance for Phase 2.")
        return
        
    cash_available = balance['cash_available']
    logging.info(f"Remaining Cash: {cash_available:,.0f} KRW")
    
    # Re-allocate to the SAME candidates if we have enough cash
    # Candidates: final_buys
    
    if cash_available < 10000: # Min threshold
        logging.info("Cash too small to re-allocate.")
        return
        
    num_candidates = len(final_buys)
    if num_candidates == 0: return

    target_amt_per_stock = cash_available / num_candidates
    invest_amt = target_amt_per_stock * 0.99
    
    logging.info(f"Re-allocating {invest_amt:,.0f} KRW per stock to {num_candidates} stocks...")
    
    for item in final_buys:
        code = item['code']
        # Recalculate Qty with Current Price
        # Phase 2: User requested "Choi-U-Seon" (Best Priority) or "Choi-Yu-Ri" (Best Advantageous).
        # Context: "Market Order causes Margin Issue". 
        # Solution: Use "Choi-Yu-Ri" (03) which executes at Best Ask (Immediate Buy)
        # but treats margin as Limit Order (usually).
        # Note: True "Choi-U-Seon" (06) sits at Bid and doesn't execute immediately.
        # We assume 03 (Choi-Yu-Ri) is what is needed for filling the remainder.
        
        curr_data = kis.get_current_price(code)
        if curr_data:
            current_price = float(curr_data['stck_prpr'])
            # Use current price to estimate Qty
            est_price = current_price
        else:
            # Fallback
            est_price = float(item['close'])
            
        qty = int(invest_amt / est_price)
        
        if qty < 1: continue
        
        msg = f"💰 Additional Buy {code} Qty: {qty} (Best Limit/03)"
        logging.info(msg)
        slack.send_message(msg)
        
        # Order Type 03 = Choi-Yu-Ri (Best Advantageous Quote - Market like execution)
        success, result_msg = kis.send_order(code, qty, side="buy", price=0, order_type="03")
        if success:
              slack.send_message(f"✅ Additional Buy Done: {code}")
        else:
              slack.send_message(f"❌ Additional Buy Failed: {result_msg}")
        
        time.sleep(1.0) # Rate limit throttling for orders

    logging.info("Daily Routine Completed.")

if __name__ == "__main__":
    main()
