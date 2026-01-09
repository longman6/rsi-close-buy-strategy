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
import src.auth as auth
import extra_streamlit_components as stx

# Cookie Manager
cookie_manager = stx.CookieManager()

# Initialize Default User (Run once)
auth.init_default_user()

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
    return TradeManager(db=DBManager())

# --- Authentication Logic ---
def login_page():
    st.title("🔒 Login Required")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            db = DBManager()
            user = db.get_user(username)
            if user and auth.verify_password(password, user['password_hash']):
                token = auth.create_token(username)
                
                # Set Session
                st.session_state['token'] = token
                st.session_state['username'] = username
                
                # Set Cookie (72h) -> expires_at is datetime
                expires = datetime.now() + timedelta(hours=72)
                cookie_manager.set("auth_token", token, expires_at=expires)
                
                st.success("Login Successful!")
                time.sleep(1) # Wait for cookie to set
                st.rerun()
            else:
                st.error("Invalid Username or Password")

def logout():
    if 'token' in st.session_state:
        del st.session_state['token']
    if 'username' in st.session_state:
        del st.session_state['username']
    
    # Delete Cookie
    # Delete Cookie
    cookie_manager.delete("auth_token")
    
    # Prevent immediate re-login from stale cookie
    st.session_state['just_logged_out'] = True
    st.rerun()

def render_change_password_page():
    st.title("🔐 Change Password")
    username = st.session_state.get('username')
    
    if not username:
        st.error("Not logged in.")
        return

    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        submit = st.form_submit_button("Update Password")
        
        if submit:
            if new_password != confirm_password:
                st.error("New passwords do not match.")
                return
            
            if len(new_password) < 4:
                st.error("Password must be at least 4 characters.")
                return

            db = DBManager()
            user = db.get_user(username)
            
            if user and auth.verify_password(current_password, user['password_hash']):
                new_hash = auth.hash_password(new_password)
                if db.update_password(username, new_hash):
                    st.success("Password updated successfully!")
                else:
                    st.error("Failed to update password in DB.")
            else:
                st.error("Incorrect current password.")

def main_dashboard():
    # Sidebar Logout Button
    with st.sidebar:
        st.write(f"Logged in as: **{st.session_state.get('username', 'User')}**")
        if st.button("Logout"):
            logout()
        st.markdown("---")

    st.sidebar.title("🤖 RSI Power Bot")
    page = st.sidebar.radio("Navigation", [
        "📊 Dashboard (KIS)", 
        "🧠 AI Advice", 
        "📉 Full RSI List (KOSDAQ 150)",
        "📈 Trade History",
        "📒 Trading Journal",
        "💳 LLM Billing & Usage",
        "🔐 Change Password"
    ])
    
    if page == "📊 Dashboard (KIS)":
        render_dashboard()
    elif page == "🧠 AI Advice":
        render_ai_advice_page()
    elif page == "📒 Trading Journal":
        render_journal_page()
    elif page == "📈 Trade History":
        render_trade_history_page()
    elif page == "📉 Full RSI List (KOSDAQ 150)":
        render_full_rsi_page()
    elif page == "🔐 Change Password":
        render_change_password_page()
    elif page == "💳 LLM Billing & Usage":
        render_credit_page()

def render_credit_page():
    st.title("💳 LLM Billing & Usage")
    st.markdown("### Active Models & Billing Links")
    st.info("Most LLM providers do not allow checking credit balance via API for security reasons. Please use the links below to check your usage.")
    
    # Load AI Config
    from src.ai_manager import AIManager
    try:
        # We instantiate AIManager just to get config, ignoring init cost for now or cache it
        # Actually initializing AIManager connects to clients which is fine but maybe heavy?
        # Let's just read the json directly or trust AIManager is light enough.
        # AIManager init does environment checks.
        ai_manager = AIManager()
        config = ai_manager.config
    except Exception as e:
        st.error(f"Failed to load AI Config: {e}")
        return

    # Providers Data
    providers = [
        {
            "id": "openai", 
            "name": "OpenAI (ChatGPT)", 
            "link": "https://platform.openai.com/settings/organization/billing/overview", 
            "desc": "Check API Usage"
        },
        {
            "id": "claude", 
            "name": "Anthropic (Claude)", 
            "link": "https://console.anthropic.com/settings/plans", 
            "desc": "Check Credits"
        },
        {
            "id": "gemini", 
            "name": "Google (Gemini)", 
            "link": "https://aistudio.google.com/usage?timeRange=last-28-days&tab=billing&project=gen-lang-client-0904665104", 
            "desc": "Check Quota/Plan"
        },
        {
            "id": "grok", 
            "name": "xAI (Grok)", 
            "link": "https://console.x.ai/", 
            "desc": "Check Billing"
        }
    ]

    # Create 2 columns
    col1, col2 = st.columns(2)
    
    for i, p in enumerate(providers):
        p_cfg = config.get(p["id"], {})
        is_enabled = p_cfg.get("enabled", False)
        model = p_cfg.get("model", "N/A")
        
        status_icon = "✅" if is_enabled else "❌"
        status_text = "Active" if is_enabled else "Disabled"
        
        with (col1 if i % 2 == 0 else col2):
            with st.container(border=True):
                st.subheader(f"{p['name']}")
                st.write(f"**Status:** {status_icon} {status_text}")
                st.write(f"**Model:** `{model}`")
                
                if is_enabled:
                    st.link_button(f"🔗 {p['desc']}", p['link'])
                else:
                    st.caption("Enable in llm_config.json to use.")

def main():
    # 1. Check Session State
    token = st.session_state.get('token')
    
    # 2. If no session, Check Cookie
    if not token:
        # If we just logged out, skip cookie check and clear the flag
        if st.session_state.get('just_logged_out'):
             del st.session_state['just_logged_out']
        else:
            token = cookie_manager.get("auth_token")
            if token:
                 # Verify found cookie
                 username = auth.verify_token(token)
                 if username:
                     st.session_state['token'] = token
                     st.session_state['username'] = username
                     st.rerun() # Rerun to update state
    
    # 3. Final Verification
    if token:
        username = auth.verify_token(token)
        if username:
            main_dashboard()
        else:
            # Invalid Token (Expired or Fake)
            if 'token' in st.session_state:
                del st.session_state['token']
            cookie_manager.delete("auth_token")
            login_page()
    else:
        login_page()

def render_dashboard():
    st.title("📊 Real-time Dashboard")
    
    kis = get_kis_client()
    strategy = get_strategy()
    trade_manager = get_trade_manager() # Not heavily used here if using API for history, but kept for util

    # 1. Account Summary & Holdings
    st.subheader("💼 Portfolio Status")
    
    if st.button("🔄 Refresh Data"):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Fetching KIS Data..."):
        balance = kis.get_balance()
    
    if not balance:
        st.error("Failed to fetch balance. Check API/Network.")
        return

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Asset", f"{balance['total_asset']:,.0f} KRW")
    col2.metric("Max Orderable", f"{balance.get('max_buy_amt', 0):,.0f} KRW")
    col3.metric("Cash Available", f"{balance['cash_available']:,.0f} KRW")
    
    holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    holdings_count = len(holdings)
    col4.metric("Positions", f"{holdings_count} / {config.MAX_POSITIONS}")

    st.divider()
    
    # Holdings Table
    total_pnl = balance.get('total_pnl', 0)
    total_rate = balance.get('total_return_rate', 0)
    
    # Fallback: Calculate manually if API returns 0 but we have holdings
    if total_pnl == 0 and balance.get('holdings'):
        calc_pnl = 0
        total_purchase = 0
        for h in balance['holdings']:
             qty = int(h['hldg_qty'])
             if qty > 0:
                 p_pnl = float(h['evlu_pfls_amt'])
                 p_avg = float(h['pchs_avg_pric'])
                 calc_pnl += p_pnl
                 total_purchase += (p_avg * qty)
        
        if total_purchase > 0:
            total_pnl = calc_pnl
            total_rate = (total_pnl / total_purchase) * 100

    pnl_color = "red" if total_pnl >= 0 else "blue"
    st.markdown(f"### 📈 Current Holdings | P/L: :{pnl_color}[{total_pnl:,.0f} KRW ({total_rate:.2f}%)]")
    
    if holdings:
        # Header Row
        h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1, 1, 1, 1.5, 1.5, 1])
        h1.markdown("**Name/Code**")
        h2.markdown("**Price**")
        h3.markdown("**Qty**")
        h4.markdown("**RSI/SMA**")
        h5.markdown("**P/L**")
        h6.markdown("**Day Chg**")
        h7.markdown("**Action**")
        st.divider()

        # Fetch RSI for each (cached if possible, but real-time needed)
        progress_bar = st.progress(0)
        
        for i, h in enumerate(holdings):
            code = h['pdno']
            name = h['prdt_name']
            curr = float(h['prpr'])
            avg = float(h['pchs_avg_pric'])
            qty = int(h['hldg_qty'])
            pnl_pct = float(h['evlu_pfls_rt']) 
            pnl_amt = float(h['evlu_pfls_amt']) 
            
            # RSI/SMA Calculation & Day Change
            df = kis.get_daily_ohlcv(code)
            rsi = 0.0
            sma = 0.0
            is_above_sma = False
            day_change_pct = 0.0

            if not df.empty:
                df = strategy.calculate_indicators(df)
                latest = df.iloc[-1]
                if 'RSI' in df.columns:
                    rsi = latest['RSI']
                if 'SMA' in df.columns:
                    sma = latest['SMA']
                    if 'Close' in df.columns and latest['Close'] > sma:
                        is_above_sma = True

                # Calculate day change
                if len(df) >= 2:
                    yesterday_close = df['Close'].iloc[-2]
                    today_price = curr
                    if yesterday_close > 0:
                        day_change_pct = ((today_price - yesterday_close) / yesterday_close) * 100

            # UI Rendering
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1, 1, 1, 1.5, 1.5, 1])
            
            # 1. Name
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            c1.markdown(f"[{name}]({url})\n`{code}`")
            
            # 2. Price
            c2.write(f"{curr:,.0f}\n({avg:,.0f})")
            
            # 3. Qty
            c3.write(f"{qty:,}")
            
            # 4. RSI/SMA
            sma_icon = "✅" if is_above_sma else "❌"
            c4.write(f"RSI: {rsi:.1f}\nSMA: {int(sma):,} {sma_icon}")
            
            # 5. P/L
            pnl_c = "red" if pnl_pct >= 0 else "blue"
            c5.markdown(f":{pnl_c}[{pnl_pct:.2f}%]\n:{pnl_c}[{pnl_amt:,.0f}]")
            
            # 6. Day Change
            day_c = "red" if day_change_pct > 0 else "blue" if day_change_pct < 0 else "grey"
            c6.markdown(f":{day_c}[{day_change_pct:+.2f}%]")
            
            # 7. Action Button
            sell_key = f"sell_state_{code}"
            
            # Check if we are in confirmation mode for this stock
            if st.session_state.get(sell_key):
                # Confirmation Mode
                ac1, ac2 = c7.columns(2)
                if ac1.button("확인", key=f"confirm_{code}", type="primary", use_container_width=True):
                    # Execute Market Sell
                    with st.spinner(f"Selling {name}..."):
                        success, msg = kis.send_order(code, qty, side="sell", price=0) # Market Sell
                        if success:
                            st.success(f"Sold {name}!")
                            
                            # Log Trade (Same logic)
                            try:
                                now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
                                date_str = now_kst.strftime("%Y%m%d")
                                trade_manager.update_sell(
                                    code=code, 
                                    name=name, 
                                    date_str=date_str, 
                                    price=curr, 
                                    qty=qty, 
                                    pnl_pct=pnl_pct
                                )
                                st.toast("Trade history saved.")
                            except Exception as e:
                                st.error(f"Failed to save trade history: {e}")
                                
                            del st.session_state[sell_key] # Reset state
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Failed: {msg}")
                            del st.session_state[sell_key] # Reset on fail
                            
                if ac2.button("취소", key=f"cancel_{code}", use_container_width=True):
                    del st.session_state[sell_key]
                    st.rerun()
            else:
                # Default Mode
                if c7.button("매도", key=f"init_sell_{code}", type="secondary", use_container_width=True):
                    st.session_state[sell_key] = True
                    st.rerun()

            st.divider()
            progress_bar.progress((i + 1) / len(holdings))
            
        progress_bar.empty()
        
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

def render_ai_advice_page():
    st.title("🧠 AI Advice")
    st.markdown("Detailed AI Analysis for Low RSI Stocks.")

    db = DBManager()
    available_dates = db.get_all_dates()
    
    if not available_dates:
        st.warning("No data found.")
        return

    selected_date = st.sidebar.selectbox("Select Date", available_dates, index=0, key="ai_date")
    st.header(f"📅 AI Analysis for {selected_date}")

    # Fetch Base RSI Results
    rsi_results = db.get_rsi_by_date(selected_date)
    # Fetch AI Detailed Advice
    ai_advice_list = db.get_ai_advice(selected_date)
    
    if not rsi_results:
        st.info("No analysis records for this date.")
        return
    
    df_rsi = pd.DataFrame(rsi_results)
    
    if df_rsi.empty:
        st.info("No data.")
        return

    # Check if there is advice for this date
    if not ai_advice_list:
        st.info(f"No AI advice generated for {selected_date}.")
        return

    # Group Advice by Code AND Collect Models
    advice_map = {} # code -> list of dicts
    all_models = set()
    
    for row in ai_advice_list:
        c = row['code']
        m = row['model']
        all_models.add(m)
        if c not in advice_map: advice_map[c] = []
        advice_map[c].append(row)

    # Filter RSI stocks to only those that have AI advice
    analyzed_codes = set(advice_map.keys())
    analyzed_df = df_rsi[df_rsi['code'].isin(analyzed_codes)].copy()
    
    if analyzed_df.empty:
         st.warning("Mismatch: Advice exists but RSI records missing for those codes.")
         return

    # --- Model Selection ---
    # Sort models alphabetically
    sorted_models = sorted(list(all_models))
    # Add "All (Consensus)" option
    filter_options = ["All (Consensus)"] + sorted_models
    
    selected_model = st.selectbox("Select AI Model", filter_options)
    
    st.divider()
    
    st.subheader(f"🔍 Analysis Results ({len(analyzed_df)})")
    
    for _, row in analyzed_df.iterrows():
        code = row['code']
        name = row['name']
        rsi = row['rsi']
        
        opinions = advice_map.get(code, [])
        
        # Filter opinions based on selection
        if selected_model != "All (Consensus)":
            opinions = [op for op in opinions if op['model'] == selected_model]
            if not opinions:
                continue # Skip stocks if the selected model didn't analyze them (unlikely if they are in analyzed_df from same date, but possible)
        
        # Calculate Summary/Display
        if selected_model == "All (Consensus)":
            yes_count = sum(1 for op in opinions if op['recommendation'] == 'YES')
            total = len(opinions)
            summary = f"{yes_count}/{total} YES"
            if total > 0 and yes_count == total: summary = "ALL YES"
            if sum(1 for op in opinions if op['recommendation'] == 'NO') == total: summary = "ALL NO"
        else:
            # Single Model View
            op = opinions[0] # Should be only one per model per date per code
            summary = op['recommendation']
        
        # Color for Summary
        color = "grey"
        if "YES" in summary: color = "green"
        if "ALL NO" in summary or summary == "NO": color = "red"
        
        # Expander Title
        price_fmt = f"{int(row['close_price']):,}" if pd.notna(row['close_price']) else "N/A"
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        
        # SMA Formatting
        sma_val = row.get('sma')
        is_above = row.get('is_above_sma')
        sma_str = ""
        if pd.notna(sma_val):
             icon = "✅" if is_above else "❌"
             sma_str = f" | SMA: {int(float(sma_val)):,} {icon}"

        title = f":{color}[{summary}] **{name}** ({code}) | RSI: {rsi:.2f}{sma_str} | Close: {price_fmt} KRW"
        
        with st.expander(title):
            st.markdown(f"### 🔗 [{name} ({code})]({url})")
            if not opinions:
                st.caption("No advice details.")
            else:
                if selected_model != "All (Consensus)":
                    # Single View
                    op = opinions[0]
                    rec = op['recommendation']
                    reason = op['reasoning']
                    prompt = op.get('prompt', 'No prompt recorded.')
                    
                    if rec == "YES":
                        st.success(f"**{op['model']} Recommendation: {rec}**\n\n{reason}")
                    elif rec == "NO":
                        st.error(f"**{op['model']} Recommendation: {rec}**\n\n{reason}")
                    else:
                        st.warning(f"**{op['model']} Recommendation: {rec}**\n\n{reason}")
                        
                    with st.expander("📝 View Analysis Prompt Used"):
                        st.code(prompt, language='text')

                else:
                    # Tabs View (Consensus)
                    model_names = [op['model'] for op in opinions]
                    tabs = st.tabs(model_names)
                    for i, tab in enumerate(tabs):
                        op = opinions[i]
                        with tab:
                            rec = op['recommendation']
                            reason = op['reasoning']
                            prompt = op.get('prompt', 'No prompt recorded.')
                            
                            if rec == "YES":
                                st.success(f"**Recommendation: {rec}**\n\n{reason}")
                            elif rec == "NO":
                                st.error(f"**Recommendation: {rec}**\n\n{reason}")
                            else:
                                st.warning(f"**Recommendation: {rec}**\n\n{reason}")
                            
                            with st.expander("📝 View Analysis Prompt Used"):
                                st.code(prompt, language='text')


def render_full_rsi_page():
    st.title("📉 Full RSI List (KOSDAQ 150)")
    st.markdown("Full RSI(3) screening results for all 150 stocks.")

    db = DBManager()
    available_dates = db.get_all_dates()
    
    if not available_dates:
        st.warning("No data found.")
        return

    selected_date = st.sidebar.selectbox("Select Date", available_dates, index=0, key="rsi_date")
    st.header(f"📅 Daily RSI Scan for {selected_date}")
    
    rsi_results = db.get_rsi_by_date(selected_date)
    ai_advice_list = db.get_ai_advice(selected_date)
    
    if not rsi_results:
        st.info("No RSI analysis records for this date.")
        return
    
    df = pd.DataFrame(rsi_results)
    
    if not df.empty:
        # Build Consensus for Table
        advice_map = {} # code -> summary
        if ai_advice_list:
             # Group first
             grouped = {}
             for row in ai_advice_list:
                 c = row['code']
                 if c not in grouped: grouped[c] = []
                 grouped[c].append(row)
             
             for code, ops in grouped.items():
                 yes = sum(1 for x in ops if x['recommendation'] == 'YES')
                 total = len(ops)
                 # Simple display
                 if total == 0:
                     advice_map[code] = "N/A"
                 elif yes == total:
                     advice_map[code] = "ALL YES"
                 elif yes == 0:
                     advice_map[code] = "ALL NO"
                 else:
                     advice_map[code] = f"{yes}/{total} YES"

        # Apply to DF
        df['AI Rec'] = df['code'].map(lambda x: advice_map.get(x, "")) # Empty if no advice
        
        # Sort: RSI Ascending
        df = df.sort_values(by='rsi', ascending=True)

        # Summary Metrics
        total_stocks = len(df)
        candidates = len(df[df['rsi'] < config.RSI_BUY_THRESHOLD])
        
        c1, c2 = st.columns(2)
        c1.metric("Total Analyzed", total_stocks)
        c2.metric(f"Low RSI (<{config.RSI_BUY_THRESHOLD})", candidates)
        
        st.divider()
        
        # Main Table format
        df['rsi_fmt'] = df['rsi'].map(lambda x: f"{x:.2f}" if pd.notna(x) else "NaN")
        
        def safe_fmt_close(x):
            try:
                if pd.isna(x) or x == "": return ""
                if isinstance(x, bytes): return "Err"
                return f"{int(float(x)):,}"
            except: return "Err"

        df['close_fmt'] = df['close_price'].map(safe_fmt_close)
        df['sma_fmt'] = df.apply(lambda row: f"{safe_fmt_close(row.get('sma', 0))} {'(✅)' if row.get('is_above_sma') else '(❌)'}", axis=1)
        df['low_rsi_fmt'] = df.apply(lambda row: "✅" if row.get('is_low_rsi') else "", axis=1)

        # Display Columns
        # Display Columns
        df_display = df[['code', 'name', 'rsi_fmt', 'low_rsi_fmt', 'close_fmt', 'sma_fmt', 'AI Rec']].copy()
        df_display.columns = ['Code', 'Name', f'RSI({config.RSI_WINDOW})', 'Low RSI', 'Close', f'SMA({config.SMA_WINDOW})', 'Consensus']
        
        # Naver Link
        df_display['Name'] = df_display.apply(
            lambda row: f"<a href='https://finance.naver.com/item/main.naver?code={row['Code']}' target='_blank'>{row['Name']}</a>", 
            axis=1
        )
        
        # Colorize Consensus
        df_display['Consensus'] = df_display['Consensus'].apply(
            lambda x: f"<span style='font-weight:bold; color:{'green' if 'YES' in x else 'red' if 'ALL NO' in x else 'gray'}'>{x}</span>" if x else ""
        )
        
        st.write(df_display.to_html(escape=False), unsafe_allow_html=True)
        st.caption(f"Total: {len(df)} stocks. Sorted by RSI Ascending.")
        
    else:
        st.info("No data available.")

    if st.sidebar.button("Refresh Data"):
        st.rerun()

def render_trade_history_page():
    st.title("📈 Trade History")
    st.markdown("Detailed log of all BUY/SELL executions stored in the database.")

    db = DBManager()
    history = db.get_trade_history()

    if not history:
        st.info("No trade records found in the database.")
        return

    df = pd.DataFrame(history)
    
    # 1. Summary Metrics
    st.subheader("📊 Performance Summary")
    
    # Calculate realized P/L from SELL records
    sell_df = df[df['action'] == 'SELL'].copy()
    
    total_trades = len(sell_df)
    total_pnl_pct = sell_df['pnl_pct'].sum() if total_trades > 0 else 0.0
    avg_pnl_pct = sell_df['pnl_pct'].mean() if total_trades > 0 else 0.0
    win_rate = (len(sell_df[sell_df['pnl_pct'] > 0]) / total_trades * 100) if total_trades > 0 else 0.0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Closed Trades", f"{total_trades}")
    c2.metric("Total P/L (%)", f"{total_pnl_pct:.2f}%")
    c3.metric("Avg P/L (%)", f"{avg_pnl_pct:.2f}%")
    c4.metric("Win Rate", f"{win_rate:.1f}%")
    
    st.divider()

    # 2. Cumulative Profit Chart
    st.subheader("📈 Cumulative Profit Over Time")
    if total_trades > 0:
        # Sort by date ascending for chart
        chart_df = sell_df.sort_values('date')
        chart_df['cumulative_pnl'] = chart_df['pnl_pct'].cumsum()
        
        # Streamlit line_chart expects index to be the x-axis
        chart_df = chart_df.set_index('date')
        st.line_chart(chart_df['cumulative_pnl'])
    else:
        st.info("Not enough sell data for a performance chart.")

    st.divider()

    # 3. Detailed Trade Log
    st.subheader("📜 Execution Log")
    
    # Format for display
    df_display = df.copy()
    
    # Naver Link for Name
    df_display['Name'] = df_display.apply(
        lambda row: f"<a href='https://finance.naver.com/item/main.naver?code={row['code']}' target='_blank'>{row['name']}</a>", 
        axis=1
    )
    
    # Format Price and Amount
    df_display['Price'] = df_display['price'].map(lambda x: f"{int(x):,}")
    df_display['Amount'] = df_display['amount'].map(lambda x: f"{int(x):,}")
    
    # Action Badge
    df_display['Action'] = df_display['action'].apply(
        lambda x: f"<span style='font-weight:bold; color:{'blue' if x == 'BUY' else 'red'}'>{x}</span>"
    )
    
    # Calculate P/L Amount (Approximate from Sell Total and PnL %)
    def calc_pnl_amt(row):
        if row['action'] == 'SELL' and row['amount'] > 0 and row['pnl_pct'] != 0:
            # Formula: Profit = Sell_Amt - Buy_Amt
            # Sell_Amt = Buy_Amt * (1 + r/100) => Buy_Amt = Sell_Amt / (1 + r/100)
            # Profit = Sell_Amt * (r/100) / (1 + r/100)
            # Or simply: amount * pnl / (100 + pnl)
            
            # Handle extreme case where pnl is -100% (denominator 0)?
            if row['pnl_pct'] == -100: return -row['amount'] # Lost everything (technically Sell amt would be 0 though)
            
            pnl_amt = row['amount'] * row['pnl_pct'] / (100 + row['pnl_pct'])
            return pnl_amt
        return 0

    df_display['pnl_amt'] = df_display.apply(calc_pnl_amt, axis=1)

    # P/L (Amount) Display
    df_display['P/L (₩)'] = df_display.apply(
        lambda row: f"<span style='color:{'red' if row['pnl_amt'] > 0 else 'blue'}'>{int(row['pnl_amt']):,}</span>" if row['action'] == 'SELL' else "",
        axis=1
    )

    # P/L (%) for display
    df_display['P/L (%)'] = df_display.apply(
        lambda row: f"<span style='color:{'red' if row['pnl_pct'] > 0 else 'blue'}'>{row['pnl_pct']:.2f}%</span>" if row['action'] == 'SELL' else "",
        axis=1
    )
    
    # Select and order columns
    df_display = df_display[['date', 'Action', 'Name', 'code', 'Price', 'quantity', 'Amount', 'P/L (%)', 'P/L (₩)']]
    df_display.columns = ['Date', 'Action', 'Name', 'Code', 'Price', 'Qty', 'Amount', 'P/L (%)', 'P/L (₩)']
    
    st.write(df_display.to_html(escape=False), unsafe_allow_html=True)

def render_journal_page():
    st.title("📒 Trading Journal")
    st.markdown("Daily analysis logs and trade execution snapshots.")

    db = DBManager()
    
    # 1. Fetch All Journal Entries
    entries = db.get_all_journal_entries()
    
    if not entries:
        st.info("No journal entries yet. They are created daily at market close.")
        return
        
    # Convert to DF for easy handling
    df = pd.DataFrame(entries)
    df.sort_values(by="date", ascending=False, inplace=True)
    
    # Select Date
    selected_date = st.selectbox("Select Date", df['date'].unique(), index=0)
    
    # Get Entry for selected date
    entry = df[df['date'] == selected_date].iloc[0]
    
    # --- UI Layout ---
    col1, col2, col3 = st.columns(3)
    
    col1.metric("Date", entry['date'])
    col2.metric("Total Equity", f"{float(entry['total_balance']):,.0f} KRW")
    
    # P/L Color
    pnl = float(entry['daily_profit_loss']) if entry['daily_profit_loss'] else 0.0
    ret = float(entry['daily_return_pct']) if entry['daily_return_pct'] else 0.0
    
    col3.metric("Daily P/L", f"{pnl:,.0f} KRW", f"{ret:.2f}%")
    
    st.divider()
    
    c_left, c_right = st.columns([1, 1])
    
    with c_left:
        st.subheader("📸 Holdings Snapshot")
        snapshot_text = entry.get('holdings_snapshot', "No snapshot.")
        st.text_area("End of Day Status", value=snapshot_text, height=400, disabled=True)
        
    with c_right:
        st.subheader("📝 Daily Notes")
        
        current_note = entry.get('notes') if entry.get('notes') else ""
        
        with st.form(key=f"note_form_{selected_date}"):
            new_note = st.text_area("Write your thoughts...", value=current_note, height=300)
            submit = st.form_submit_button("Save Note")
            
            if submit:
                db.update_journal_note(selected_date, new_note)
                st.success("Note saved!")
                time.sleep(1)
                st.rerun()

    st.divider()
    
    # Equity Curve
    st.subheader("📈 Equity Curve")
    chart_df = df.sort_values('date')
    st.line_chart(chart_df, x="date", y="total_balance")


if __name__ == "__main__":
    main()
