import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz

# Custom Modules
from src.kis_client import KISClient
from src.strategy import Strategy
from src.trade_manager import TradeManager
from src.db_manager import DBManager
import config

# Page Config
st.set_page_config(
    page_title="RSI Power Zone Dashboard",
    page_icon="🤖",
    layout="wide"
)

def get_kst_now():
    return datetime.now(pytz.timezone('Asia/Seoul'))

@st.cache_resource
def get_kis_client():
    return KISClient()

@st.cache_resource
def get_strategy():
    return Strategy()

@st.cache_resource
def get_trade_manager():
    return TradeManager()

def main():
    st.sidebar.title("🤖 RSI Power Bot")
    page = st.sidebar.radio("Navigation", ["📊 Dashboard (KIS)", "🧠 Gemini Advisor"])
    
    if page == "📊 Dashboard (KIS)":
        render_dashboard()
    else:
        render_advisor()

def render_dashboard():
    st.title("📊 Real-time Dashboard")
    
    kis = get_kis_client()
    strategy = get_strategy()
    trade_manager = get_trade_manager() # Not heavily used here if using API for history, but kept for util

    # 1. Account Summary & Holdings
    st.subheader("💼 Portfolio Status")
    
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Fetching KIS Data..."):
        balance = kis.get_balance()
    
    if not balance:
        st.error("Failed to fetch balance. Check API/Network.")
        return

    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Asset", f"{balance['total_asset']:,.0f} KRW")
    col2.metric("Cash Available", f"{balance['cash_available']:,.0f} KRW")
    
    holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    holdings_count = len(holdings)
    col3.metric("Positions", f"{holdings_count} / {config.MAX_POSITIONS}")

    st.divider()
    
    # Holdings Table
    st.markdown("### 📈 Current Holdings")
    
    if holdings:
        holdings_data = []
        
        # Fetch RSI for each (cached if possible, but real-time needed)
        # We need to fetch OHLCV for RSI. This might be slow for many stocks.
        progress_bar = st.progress(0)
        
        for i, h in enumerate(holdings):
            code = h['pdno']
            name = h['prdt_name']
            curr = float(h['prpr'])
            avg = float(h['pchs_avg_pric'])
            qty = int(h['hldg_qty'])
            pnl_pct = float(h['evlu_pfls_rt']) # KIS gives this
            pnl_amt = float(h['evlu_pfls_amt']) 
            
            # RSI Calculation
            df = kis.get_daily_ohlcv(code)
            rsi = 0.0
            if not df.empty:
                df = strategy.calculate_indicators(df)
                if 'RSI' in df.columns:
                    rsi = df['RSI'].iloc[-1]
            
            # Naver Link
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            link_html = f"<a href='{url}' target='_blank'>{name}</a>"
            
            holdings_data.append({
                "Name": link_html,
                "Code": code,
                "Price": f"{curr:,.0f}",
                "Avg Price": f"{avg:,.0f}",
                "Qty": qty,
                "RSI": f"{rsi:.2f}",
                "P/L (%)": f"{pnl_pct:.2f}%",
                "P/L (₩)": f"{pnl_amt:,.0f}"
            })
            progress_bar.progress((i + 1) / len(holdings))
            
        progress_bar.empty()
        
        df_h = pd.DataFrame(holdings_data)
        st.write(df_h.to_html(escape=False), unsafe_allow_html=True)
        
    else:
        st.info("No active positions.")

    st.divider()

    # 2. Trade History (Realized Profit)
    st.subheader("💰 Realized Profit History")
    
    period = st.radio("Select Period", ["1 Week", "1 Month", "6 Months"], horizontal=True)
    
    now = get_kst_now()
    end_date = now.strftime("%Y%m%d")
    
    if period == "1 Week":
        start_date = (now - timedelta(weeks=1)).strftime("%Y%m%d")
    elif period == "1 Month":
        start_date = (now - timedelta(days=30)).strftime("%Y%m%d")
    else:
        start_date = (now - timedelta(days=180)).strftime("%Y%m%d")
        
    with st.spinner(f"Fetching History ({start_date} ~ {end_date})..."):
        history = kis.get_period_trades(start_date, end_date)
        
    if history:
        # history fields from inquire-daily-ccld:
        # ord_dt, prdt_name, sll_buy_dvsn_cd (01:Sell, 02:Buy), tot_ccld_amt, tot_ccld_qty, avg_prvs
        hist_data = []
        for item in history:
            # Filter only SELL (01)
            if item.get('sll_buy_dvsn_cd') == '01':
                name = item['prdt_name']
                code = item.get('pdno', '') # Might be empty in some outputs
                
                # If code is missing, try to find it? 
                # For now just link Name if possible or just display Name
                
                # Naver Link
                if code:
                    url = f"https://finance.naver.com/item/main.naver?code={code}"
                    name_display = f"<a href='{url}' target='_blank'>{name}</a>"
                else:
                    name_display = name

                qty = int(item.get('tot_ccld_qty', 0))
                price = float(item.get('avg_prvs', 0))
                amt = float(item.get('tot_ccld_amt', 0))
                
                hist_data.append({
                    "Date": item.get('ord_dt'),
                    "Name": name_display,
                    "Type": "SELL",
                    "Qty": qty,
                    "Price": f"{price:,.0f}",
                    "Amount": f"{amt:,.0f}",
                    "Note": "P/L N/A (Checking Local)" # Info place holder
                })
        
        if hist_data:
            df_hist = pd.DataFrame(hist_data)
            st.write(df_hist.to_html(escape=False), unsafe_allow_html=True)
            st.caption("* KIS API 'Daily Conclusion' does not provide realized profit directly. Showing execution amounts.")
        else:
            st.info("No Sell records found for this period in KIS History.")
            
    else:
        # Fallback to TradeManager (Local History) if KIS returns nothing (Mock Mode)
        st.warning("⚠️ KIS Period Profit API is unavailable (likely due to Mock Investment Mode). Showing Local Trade History.")
        
        tm_history = trade_manager.history.get("last_trade", {})
        if tm_history:
            local_data = []
            
            # Filter by date range
            start_int = int(start_date)
            end_int = int(end_date)
            
            for code, data in tm_history.items():
                sell_date = int(data['sell_date'])
                if start_int <= sell_date <= end_int:
                    # We need Name, which is not in trade_history.json usually
                    # Fetch from KIS current price or exclusion list cache? 
                    # Try fetch name
                    name = code
                    try:
                       curr = kis.get_current_price(code)
                       if curr: name = curr.get('hts_kor_isnm', code)
                    except: pass
                    
                    url = f"https://finance.naver.com/item/main.naver?code={code}"
                    name_display = f"<a href='{url}' target='_blank'>{name}</a>"

                    local_data.append({
                        "Date": data['sell_date'],
                        "Name": name_display,
                        "Code": code,
                        "Est. Return (%)": f"{data['pnl_pct']:.2f}%"
                    })
            
            if local_data:
                 df_local = pd.DataFrame(local_data)
                 st.write(df_local.to_html(escape=False), unsafe_allow_html=True)
            else:
                 st.info("No local trade history found for this period.")
        else:
             st.info("No local history records.")

def render_advisor():
    st.title("🧠 Gemini Buy Advisor")
    st.markdown("Automated analysis of Low-RSI KOSDAQ stocks using Gemini & real-time news.")

    # Sidebar: Date Selection
    db = DBManager()
    available_dates = db.get_all_dates()
    
    if not available_dates:
        st.warning("No data found in database yet. Run the daily job first.")
        return

    selected_date = st.sidebar.selectbox("Select Date", available_dates, index=0)
    
    st.header(f"📅 Analysis for {selected_date}")
    
    # Fetch Data
    results = db.get_advice_by_date(selected_date)
    
    if not results:
        st.info("No advice records for this date.")
        return
    
    # Convert to DataFrame for summary stats
    df = pd.DataFrame(results)
    
    # Metrics
    total = len(df)
    yes_count = len(df[df['recommendation'] == 'YES'])
    no_count = len(df[df['recommendation'] == 'NO'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Candidates", total)
    col2.metric("Recommended (YES)", yes_count)
    col3.metric("Rejected (NO)", no_count)
    
    st.divider()
    
    # Detailed List with Expanders
    # Group by Recommendation
    yes_df = df[df['recommendation'] == 'YES']
    no_df = df[df['recommendation'] == 'NO']
    
    st.subheader("✅ Recommended to BUY")
    if yes_df.empty:
        st.write("No 'YES' recommendations.")
    else:
        for _, row in yes_df.iterrows():
            with st.expander(f"**{row['name']}** ({row['code']}) | RSI: {row['rsi']:.2f}"):
                url = f"https://finance.naver.com/item/main.naver?code={row['code']}"
                st.markdown(f"### <a href='{url}' target='_blank'>{row['name']}</a>", unsafe_allow_html=True)
                st.write(f"**Decision:** {row['recommendation']}")
                st.info(row['reasoning'])
    
    st.subheader("❌ Recommended to HOLD/SKIP")
    if no_df.empty:
        st.write("No 'NO' recommendations.")
    else:
        for _, row in no_df.iterrows():
            with st.expander(f"**{row['name']}** ({row['code']}) | RSI: {row['rsi']:.2f}"):
                url = f"https://finance.naver.com/item/main.naver?code={row['code']}"
                st.markdown(f"### <a href='{url}' target='_blank'>{row['name']}</a>", unsafe_allow_html=True)
                st.write(f"**Decision:** {row['recommendation']}")
                st.caption(row['reasoning'])

    if st.sidebar.button("Refresh Data"):
        st.rerun()

if __name__ == "__main__":
    main()
