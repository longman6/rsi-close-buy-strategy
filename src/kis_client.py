import requests
import json
import time
import os
import logging
import pandas as pd
import pytz
from datetime import datetime, timedelta
import config

# Configure logging
# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class KISClient:
    def __init__(self):
        self.app_key = config.KIS_APP_KEY
        self.app_secret = config.KIS_APP_SECRET
        self.account_no = config.KIS_CANO
        self.base_url = config.KIS_URL_BASE
        
        # ... (rest of init)
        
    def get_valid_price(self, price):
        """
        Adjust price to valid tick size for KOSDAQ/KOSPI.
        Simplified logic for KOSDAQ (mostly matches):
        - < 2,000 : 1
        - 2,000 ~ 5,000 : 5
        - 5,000 ~ 20,000 : 10
        - 20,000 ~ 50,000 : 50
        - 50,000 ~ : 100
        - 200,000 ~ : 500 (KOSPI only? KOSDAQ caps at 100 usually? Let's assume standard brackets)
        
        Actually, let's use common brackets:
        PRC < 2000: 1
        2000 <= PRC < 5000: 5
        5000 <= PRC < 20000: 10
        20000 <= PRC < 50000: 50
        50000 <= PRC < 200000: 100
        200000 <= PRC < 500000: 500
        500000 <= PRC: 1000
        """
        price = int(price)
        if price < 2000: tick = 1
        elif price < 5000: tick = 5
        elif price < 20000: tick = 10
        elif price < 50000: tick = 50
        elif price < 200000: tick = 100
        elif price < 500000: tick = 500
        else: tick = 1000
        
        return price - (price % tick)
        
    def __init__(self):
        self.app_key = config.KIS_APP_KEY
        self.app_secret = config.KIS_APP_SECRET
        self.account_no = config.KIS_CANO
        self.base_url = config.KIS_URL_BASE
        
        self.access_token = None
        self.token_expired_at = 0
        
        # Check if Mock Trading (Virtual)
        self.is_mock = "openapivts" in self.base_url
        if self.is_mock:
            logging.info(f"[KIS] Running in Mock Investment Mode (openapivts detected)")
        
        if not self.app_key or not self.app_secret:
            logging.warning("[KIS] Warning: API credentials not found in config.")

    def _get_headers(self, tr_id, data=None):
        """Construct headers for API requests."""
        if self.access_token is None or time.time() > self.token_expired_at:
            self.get_access_token()
            
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        return headers

    def _save_token(self):
        """Save token to file."""
        data = {
            'access_token': self.access_token,
            'token_expired_at': self.token_expired_at
        }
        try:
            with open('token.json', 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logging.error(f"[KIS] Failed to save token: {e}")

    def _load_token(self):
        """Load token from file."""
        try:
            with open('token.json', 'r') as f:
                data = json.load(f)
                if time.time() < data['token_expired_at']:
                    self.access_token = data['access_token']
                    self.token_expired_at = data['token_expired_at']
                    logging.info(f"[KIS] Loaded cached Access Token (Expires in {int(self.token_expired_at - time.time())}s)")
                    return True
        except:
            pass
        return False

    def _send_request(self, method, path, tr_id, params=None, body=None):
        """
        Refactored Request Handler with Auto Token Refresh and Rate Limit Handling
        """
        url = f"{self.base_url}{path}"
        
        # Max retries for rate limits or server errors
        max_retries = 5
        
        for attempt in range(max_retries):
            headers = self._get_headers(tr_id)
            res = None
            try:
                if method == "GET":
                    res = requests.get(url, headers=headers, params=params, timeout=10)
                else:
                    res = requests.post(url, headers=headers, data=json.dumps(body) if body else None, timeout=10)
                
                # Check JSON for specific error codes
                is_expired = False
                is_ratelimit = False
                msg = ""
                try:
                    data = res.json()
                    msg_cd = data.get('msg_cd', '')
                    msg = data.get('msg1', '')
                    if msg_cd == 'EGW00123':
                        is_expired = True
                    elif msg_cd == 'EGW00201' or "초과" in msg:
                        is_ratelimit = True
                except:
                    pass
                
                # 1. Handle Token Expiry
                if is_expired:
                    logging.warning("[KIS] Token Expired (EGW00123). Refreshing and retrying...")
                    self.access_token = None
                    if os.path.exists('token.json'):
                        os.remove('token.json')
                    self.get_access_token()
                    continue
                
                # 2. Handle Rate Limit
                if is_ratelimit or res.status_code == 500:
                    wait_time = 1.0 if self.is_mock else 0.5
                    logging.warning(f"[KIS] Rate Limit or Server Error ({res.status_code}). Waiting {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                
                return res
            
            except Exception as e:
                logging.error(f"[KIS] Request Exception: {e}")
                time.sleep(1)
                continue
                
        return res

    def get_access_token(self):
        """Get or refresh OAuth access token."""
        # Try loading from file first
        if self._load_token():
            return

        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            data = res.json()
            if 'access_token' in data:
                self.access_token = data['access_token']
                # Token usually valid for 24h
                self.token_expired_at = time.time() + data.get('expires_in', 86400) - 60
                logging.info("[KIS] Access Token refreshed.")
                self._save_token()
            else:
                logging.error(f"[KIS] Token Error: {data}")
                raise Exception("Failed to get Access Token")
        except Exception as e:
            logging.error(f"[KIS] Auth Exception: {e}")
            raise

    def get_current_price(self, code):
        """
        Fetch current price details.
        Also used to check 'Admin Issue' status from output fields if available,
        though fetching 'master' info is more reliable for status.
        Here we use standard price query.
        TR_ID: FHKST01010100 (Stock Current Price)
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", # J: Stock, W: Warrants...
            "FID_INPUT_ISCD": code # Stock Code
        }
        
        
        for attempt in range(5):
            res = self._send_request("GET", path, "FHKST01010100", params=params)
            
            if res:
                if res.status_code == 200:
                    data = res.json()
                    if data['rt_cd'] == '0':
                        return data['output']
                    else:
                        # Check for Rate Limit (EGW00201 or similar msg)
                        msg = data.get('msg1', '')
                        code_err = data.get('msg_cd', '')
                        if "초과" in msg or code_err == "EGW00201":
                            logging.warning(f"[KIS] Rate Limit (GetPrice) -> Sleeping 0.5s... ({attempt+1}/5)")
                            time.sleep(0.5)
                            continue
                        
                        logging.warning(f"[KIS] GetPrice Error {code}: {msg}")
                        return None
                elif res.status_code == 500: # Sometimes Mock throws 500 on rate limit
                     logging.warning(f"[KIS] Server Error 500 (GetPrice) -> Sleeping 1s... ({attempt+1}/5)")
                     time.sleep(1)
                     continue

            time.sleep(0.1) # Default short wait between retries if net error
            
        logging.error(f"[KIS] Failed to get price for {code} after retries.")
        return None

    def get_daily_ohlcv(self, code, start_date=None, end_date=None, period_code="D"):
        """
        Fetch daily OHLCV for chart/strategy.
        TR_ID: FHKST01010400 (Daily Price)
        """
        # Switching to CHART API for longer history (needed for SMA 100)
        # TR_ID: FHKST03010100
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        url = f"{self.base_url}{path}"
        headers = self._get_headers("FHKST03010100")
        
        # Calculate start/end dates
        target_start_date = start_date if start_date else "20230101"
        current_end_date = end_date if end_date else datetime.now().strftime("%Y%m%d")
        
        all_dfs = []
        
        while True:
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": target_start_date, 
                "FID_INPUT_DATE_2": current_end_date,
                "FID_PERIOD_DIV_CODE": period_code, 
                "FID_ORG_ADJ_PRC": "1" # Adjusted Price
            }
            
            # Rate limit buffer inside loop (essential)
            # Mock server needs longer delay to avoid 500 errors
            delay = 0.5 if self.is_mock else 0.1
            time.sleep(delay) 
            
            res = self._send_request("GET", path, "FHKST03010100", params=params)
            if res.status_code == 200:
                data = res.json()
                if data['rt_cd'] == '0' and data['output2']:
                    chunk_df = pd.DataFrame(data['output2'])
                    
                    # Clean up columns for this chunk
                    chunk_df = chunk_df.rename(columns={
                        'stck_bsop_date': 'Date',
                        'stck_oprc': 'Open',
                        'stck_hgpr': 'High',
                        'stck_lwpr': 'Low',
                        'stck_clpr': 'Close',
                        'acml_vol': 'Volume'
                    })
                    chunk_df = chunk_df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
                    
                    # Store chunk
                    all_dfs.append(chunk_df)
                    
                    # Update end_date for next iteration
                    # output2 is usually sorted desc by date, so first item is latest, last item is oldest in this chunk
                    # But reliable way is to check min date in this chunk
                    dates = chunk_df['Date'].tolist()
                    if not dates: break
                    
                    min_date_str = min(dates) # "YYYYMMDD"
                    
                    # Check if we reached target start
                    if min_date_str <= target_start_date:
                        break
                        
                    # Calculate new end_date = min_date - 1 day
                    min_date_dt = datetime.strptime(min_date_str, "%Y%m%d")
                    new_end_dt = min_date_dt - timedelta(days=1)
                    current_end_date = new_end_dt.strftime("%Y%m%d")
                    
                    # Safety break if we are stuck
                    if new_end_dt < datetime.strptime(target_start_date, "%Y%m%d"):
                        break
                else:
                    # No more data or error
                    break
            else:
                logging.error(f"[KIS] Network Error in OHLCV loop: {res.status_code}")
                break
                
        if all_dfs:
            df = pd.concat(all_dfs)
            # Drop duplicates just in case overlap
            df = df.drop_duplicates(subset=['Date'])
            
            # Convert types
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            df[cols] = df[cols].apply(pd.to_numeric)
            df['Date'] = pd.to_datetime(df['Date'])
            
            # Filter solely within range (API might return a bit outside boundary depending on logic)
            # Actually, let's trust the logic but just sort.
            df = df.sort_values('Date') # Ascending
            
            return df
        return pd.DataFrame()

    def get_ohlcv_cached(self, code, start_date=None, end_date=None):
        """
        Fetch OHLCV using local cache + Gap Filling + Real-time Update.
        1. Load data/ohlcv/{code}.pkl
        2. If gap exists between cache and today, fetch missing days via API.
        3. Append/Update today's real-time price.
        4. (Optional) Save updated history to cache if gap was large? (Skipping save to avoid partial corruption, in-memory only)
        """
        cache_dir = "data/ohlcv"
        cache_path = os.path.join(cache_dir, f"{code}.pkl")
        
        df = pd.DataFrame()
        
        # 1. Load Cache
        if os.path.exists(cache_path):
            try:
                df = pd.read_pickle(cache_path)
            except Exception:
                pass

        today = datetime.now()
        today_str = today.strftime("%Y%m%d")
        
        # 2. Check Cache & Fill Gap
        if df.empty:
            # Full Fetch
            df = self.get_daily_ohlcv(code, start_date=start_date, end_date=end_date)
            # If we fetched everything, we might as well save it if it's substantial history?
            # For now, keep inconsistent-save policy from before to be safe.
        else:
            # Has cache. Check last date.
            last_dt = df.iloc[-1]['Date']
            last_date_str = last_dt.strftime("%Y%m%d")
            
            # If last date is earlier than today, we might have a gap.
            # Even if it is yesterday, we might want to ensure we have up to today.
            if last_date_str < today_str:
                # Calculate start_fetch_date = last_date + 1 day
                next_day = last_dt + timedelta(days=1)
                fetch_start = next_day.strftime("%Y%m%d")
                
                if fetch_start <= today_str:
                    # Fetch from fetch_start to today
                    # logging.info(f"[KIS] Filling gap for {code}: {fetch_start} ~ {today_str}")
                    gap_df = self.get_daily_ohlcv(code, start_date=fetch_start, end_date=today_str)
                    
                    if not gap_df.empty:
                        # Append
                        df = pd.concat([df, gap_df]).drop_duplicates(subset=['Date'], keep='last')
                        df = df.sort_values('Date').reset_index(drop=True)

        # 3. Force Update Today's Candle with Real-Time Current Price
        # (Chart API might be delayed or have different values than current price API)
        curr = self.get_current_price(code)
        if curr:
            curr_price = float(curr['stck_prpr'])
            try:
                # Check if today exists in df
                current_dt_normalized = pd.to_datetime(today_str)
                
                if not df.empty and df.iloc[-1]['Date'] == current_dt_normalized:
                    # Update existing today row
                    df.at[df.index[-1], 'Close'] = curr_price
                    df.at[df.index[-1], 'High'] = max(df.iloc[-1]['High'], float(curr['stck_hgpr']))
                    df.at[df.index[-1], 'Low'] = min(df.iloc[-1]['Low'], float(curr['stck_lwpr']))
                    df.at[df.index[-1], 'Volume'] = int(curr['acml_vol'])
                    # Open should be stable
                else:
                    # Append new today row
                    new_row = {
                        'Date': current_dt_normalized,
                        'Open': float(curr['stck_oprc']),
                        'High': float(curr['stck_hgpr']),
                        'Low': float(curr['stck_lwpr']),
                        'Close': curr_price,
                        'Volume': int(curr['acml_vol'])
                    }
                    if new_row['Close'] > 0: # Valid data check
                         new_df = pd.DataFrame([new_row])
                         df = pd.concat([df, new_df], ignore_index=True)
            except Exception as e:
                 logging.warning(f"[KIS] Failed to merge real-time price: {e}")

        # Filter by start_date if needed
        if start_date and not df.empty:
            df = df[df['Date'] >= pd.to_datetime(start_date)]
            
        return df

    def refresh_ohlcv_cache(self, universe_list):
        """
        Force-refresh OHLCV cache for the entire universe.
        Deletes existing .pkl files and fetches fresh data.
        """
        logging.info(f"🔄 Starting Full OHLCV Cache Refresh for {len(universe_list)} stocks...")
        count = 0
        cache_dir = "data/ohlcv"
        
        for item in universe_list:
            code = item['code']
            name = item['name']
            cache_path = os.path.join(cache_dir, f"{code}.pkl")
            
            # 1. Delete existing cache
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except Exception as e:
                    logging.warning(f"Failed to delete cache for {code}: {e}")
            
            # 2. Fetch Fresh Data & Save
            # get_daily_ohlcv returns DF but doesn't save (helper). 
            # We must save it explicitly here to rebuild the cache files.
            
            try:
                # Fetch full history (~2 years default)
                # Calculate start_date = 2 years ago
                start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
                df = self.get_daily_ohlcv(code, start_date=start_date)
                
                if not df.empty:
                    if not os.path.exists(cache_dir):
                        os.makedirs(cache_dir)
                    df.to_pickle(cache_path)
                    count += 1
            except Exception as e:
                logging.error(f"Failed to refresh {name} ({code}): {e}")
                
            # Rate Limit (Mock: 0.5s, Real: 0.1s)
            time.sleep(0.3)
            
            if (count + 1) % 10 == 0:
                logging.info(f"   Refreshed {count+1}/{len(universe_list)}...")
                
        logging.info(f"✅ Full OHLCV Refresh Complete. Updated {count} files.")

    def get_balance(self):
        """
        Check account balance and holdings.
        TR_ID: TTTC8434R (Real) / VTTC8434R (Mock)
        """
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        url = f"{self.base_url}{path}"
        
        tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
        headers = self._get_headers(tr_id)
        
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "01",  # 01: 대출일별, 02: 종목별 (공식 예제: "01")
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        res = self._send_request("GET", path, tr_id, params=params)
        if res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                # output1: Holdings list, output2: Account Summary
                holdings = data['output1']
                summary = data['output2'][0]
                
                cash_info = self.get_buyable_cash()
                
                return {
                    'cash_available': cash_info['cash'], # Real Orderable Cash
                    'max_buy_amt': cash_info['max_buy'], # Max Buyable (Margin included)
                    'total_asset': float(summary.get('tot_evlu_amt', 0)),
                    'total_pnl': float(summary.get('evlu_pfls_smt_tl', 0)),
                    'total_return_rate': float(summary.get('evlu_pfls_rt', 0)),
                    'holdings': holdings 
                }
            else:
                logging.error(f"[KIS] Balance Error: {data['msg1']} (Code: {data['msg_cd']})")
        else:
            logging.error(f"[KIS] Network/Server Error: {res.status_code} - {res.text}")
        return None

    def get_buyable_cash(self):
        """
        Fetch Real-Time Orderable Cash via inquire-psbl-order.
        TR_ID: TTTC8908R (Real) / VTTC8908R (Mock)
        Returns dict with 'cash' and 'max_buy'
        """
        path = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        
        tr_id = "VTTC8908R" if self.is_mock else "TTTC8908R"
        
        # We need a dummy code to check buying power (KIS requirement)
        # Using Samsung Electronics (005930) or any valid code
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "PDNO": "005930", 
            "ORD_UNPR": "0",
            "ORD_DVSN": "01",
            "CMA_EVLU_AMT_ICLD_YN": "Y",
            "OVRS_ICLD_YN": "N"
        }
        
        res = self._send_request("GET", path, tr_id, params=params)
        if res and res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                return {
                    "cash": float(data['output']['ord_psbl_cash']),
                    "max_buy": float(data['output']['max_buy_amt'])
                }
            else:
                 logging.warning(f"[KIS] Buyable Cash Error: {data['msg1']}")
        return {"cash": 0.0, "max_buy": 0.0}

    def is_trading_day(self, date_str):
        """
        Check if the given date (YYYYMMDD) is a trading day.
        TR_ID: CTCA0903R (Check Holiday)
        """
        # [Override] Mock Investment -> Always Trading Day
        if self.is_mock:
            logging.info(f"[KIS] Mock Mode: Forcing Trading Day = True for {date_str}")
            return True

        # [Optimization] Local Weekend Check
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            # 0=Mon, 4=Fri, 5=Sat, 6=Sun
            if dt.weekday() >= 5:
                # logging.info(f"[KIS] {date_str} is Weekend (Local Check). Skipping API.")
                return False
        except ValueError:
            logging.error(f"[KIS] Invalid Date Format for Holiday Check: {date_str}")
            # Fallback to API check if parsing fails, though likely to fail there too
            pass

        path = "/uapi/domestic-stock/v1/quotations/chk-holiday"
        tr_id = "CTCA0903R"
        
        params = {
            "BASS_DT": date_str,
            "CTX_AREA_NK": "",
            "CTX_AREA_FK": ""
        }
        
        retry_count = 0
        while retry_count < 5:
            res = self._send_request("GET", path, tr_id, params=params)
            if res and res.status_code == 200:
                data = res.json()
                if data['rt_cd'] == '0':
                    outputs = data.get('output', [])
                    for item in outputs:
                        if item['bass_dt'] == date_str:
                            return item['opnd_yn'] == 'Y'
                    return True 
                else:
                    if "초당 거래건수를 초과하였습니다" in data.get('msg1', ''):
                        # TPS Limit -> Wait and Retry (Don't count strictly against limit or allow many retries)
                        logging.warning(f"[KIS] Holiday Check TPS Limit -> Retrying...")
                        time.sleep(1)
                        # retry_count unchanged? No, avoid infinite loop risk. 
                        # But TPS can be frequent. Let's not increment count for TPS.
                        continue
                        
                    logging.warning(f"[KIS] Holiday Check Error: {data['msg1']}")
                    return True # Default open on non-TPS error
            else:
                 retry_count += 1
                 status = res.status_code if res else "None"
                 # Mock Server Workaround: 500 Error
                 if self.is_mock and status == 500:
                     logging.warning("[KIS-MOCK] Holiday Check 500 Error. Mock Server Unstable. Assuming Open.")
                     return True
                 
                 logging.warning(f"[KIS] Holiday Check Network Error ({status}). Retrying...")
                 time.sleep(1)
        
        logging.error("[KIS] Holiday Check Failed after retries. Defaulting to True.")
        return True

    def send_order(self, code, qty, side="buy", price=0, order_type="00"):
        """
        Send Buy/Sell Order.
        side: 'buy' or 'sell'
        price: 0 for Market Order (usually), or specific price.
        order_type: '00'(Limit), '01'(Market), '03'(Choi-Yu-Ri/BestCall), '06'(Choi-U-Seon)
        """
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        url = f"{self.base_url}{path}"
        
        if self.is_mock:
            tr_id = "VTTC0802U" if side == "buy" else "VTTC0801U"
        else:
            tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
            
        headers = self._get_headers(tr_id)
        
        # Order Division
        # If order_type is provided as default "00", check if price is 0 (Market)
        if order_type == "00" and price == 0:
            ord_div = "01"
        else:
            ord_div = order_type
        
        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "PDNO": code, # Product Number (Code)
            "ORD_DVSN": ord_div,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price) # 0 for Market
        }
        
        while True:
            res = self._send_request("POST", path, tr_id, body=body)
            if res is None:
                logging.error("[KIS] Order Request Failed (No Response)")
                return False, "No Response"

            try:
                data = res.json()
            except Exception as e:
                logging.error(f"[KIS] Order Response JSON Error: {e}")
                return False, "JSON Error"

            if data['rt_cd'] == '0':
                logging.info(f"[KIS] Order Success: {side.upper()} {code} {qty}ea @ {price if price >0 else 'Market'}")
                return True, data['msg1']
            else:
                # Check for TPS Limit Error
                if "초당 거래건수를 초과하였습니다" in data.get('msg1', ''):
                    logging.warning(f"[KIS] Order Rate Limit Exceeded: {data['msg1']} -> Sleeping 5s and retrying...")
                    time.sleep(5)
                    continue
                else:
                    logging.error(f"[KIS] Order Failed: {data['msg1']}")
                    return False, data['msg1']

    def check_manage_status(self, code):
        """
        Check if the stock is a Managed Item (Administrative Issue).
        Uses 'psearch/price' or master inquiry.
        Actually, simplest way via API is examining 'is_dangerous' or similar from price query if available.
        
        Alternate: Search Info (CTPF4002R - Search Stock Info)
        This endpoint returns Detailed State.
        """
        # Note: Implementing a robust check might require looking up the specific 'market warning' code.
        # For now, we will assume if 'get_current_price' returns 'is_admin_issue' equivalent.
        # Let's check 'output' of 'get_current_price' more closely in docs.
        # It has 'mrkt_warn_cls_code' (Market Warning Class).
        # And commonly 'adm_isu_yn' (Admin Issue Yes/No) is NOT clearly in all lightweight queries.
        
        # We will use FinanceDataReader in the main strategy to filter initially if possible.
        # But if we must use KIS:
        # Use 'Inquire Subject Item Info' (JTTT2001R) - but this is for specific account holdings? No.
        
        # Let's rely on get_daily_ohlcv or similar not returning error? No.
        
        # Strategy: We will use the 'Market Warning Code' from Inquire Price (FHKST01010100)
        # return dict contains:
        # 'mrkt_warn_cls_code': '00'(Normal), '01'(Caution), '02'(Warning), '03'(Danger)
        # This is a good proxy. 'Admin' might be separate.
        
        # For safety, we will implement this check in Strategy using FinanceDataReader if KIS is ambiguous.
        pass

    def check_dangerous_stock(self, code):
        """
        Check if the stock is in a dangerous state (Suspended, Admin Issue, Market Warning).
        Returns: (is_dangerous: bool, reason: str)
        """
        # Reuse get_current_price which fetches FHKST01010100
        # We need the RAW data, but get_current_price returns 'output' dict.
        
        data = None
        for _ in range(3): # Retry up to 3 times
            data = self.get_current_price(code)
            if data:
                break
            time.sleep(0.5)
            
        if not data:
            return True, "No Data" # Can't verify, so risky

        # 1. Issue Status Class Code (iscd_stat_cls_code)
        # 55: Normal (KOSPI 200), 57: Normal
        # 58: Trading Suspended (confirmed with Fadu)
        # 51: Admin Issue, 52: Inv Caution, 53: Warning, 54: Danger
        iscd_code = data.get('iscd_stat_cls_code', '')
        if iscd_code in ['51', '52', '53', '54', '58', '59']:
             return True, f"Bad Status Code ({iscd_code})"

        # 2. Market Warning (mrkt_warn_cls_code)
        # 00: Normal, 01: Caution, 02: Warning, 03: Danger
        warn_code = data.get('mrkt_warn_cls_code', '00')
        if warn_code != '00':
             return True, f"Market Warning ({warn_code})"
             
        # 3. Management Issue (mang_issu_cls_code)
        # N: Normal. Not 'N' -> Issue (assuming 'Y' or code)
        mang_code = data.get('mang_issu_cls_code', 'N')
        if mang_code != 'N':
             return True, f"Management Issue ({mang_code})"
             
        # 4. Investment Caution (invt_caful_yn)
        if data.get('invt_caful_yn', 'N') == 'Y':
             return True, "Investment Caution"

        return False, "Safe"


    def get_outstanding_orders(self):
        """
        Fetch unfilled (outstanding) orders.
        Real: TTTC8001R (Daily Conclusion - Unfilled)
        Mock: Not Supported (API returns 90000000 or empty data)
        """
        if self.is_mock:
            # [Mock Environment] 
            # VTTC8036R returns "Not Supported" (Code 90000000).
            # VTTC8001R returns empty data for unfilled orders.
            # To prevent errors, we skip this feature in Mock.
            logging.warning("[KIS] 'get_outstanding_orders' is NOT supported in Mock Investment. Skipping.")
            return []

        # [Real Environment] Use inquire-daily-ccld
        path = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "TTTC8001R"
        
        tz_kst = pytz.timezone('Asia/Seoul')
        today_str = datetime.now(pytz.utc).astimezone(tz_kst).strftime("%Y%m%d")
        
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": today_str,
            "INQR_END_DT": today_str,
            "SLL_BUY_DVSN_CD": "00", 
            "INQR_DVSN": "00", 
            "PDNO": "",
            "ORD_GNO_BRNO": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "CCLD_DVSN": "02", # Unfilled Only
            "ODNO": "",
            "INQR_DVSN_1": "",
            "INQR_DVSN_2": "",
            "INQR_DVSN_3": ""
        }
        res_key = 'output1' # 8001R returns 'output1'

        res = self._send_request("GET", path, tr_id, params=params)
        
        if res and res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                raw_list = data.get(res_key, [])
                normalized = []
                for item in raw_list:
                    # Filter for Mock (8036R returns available for cancel, so effectively outstanding)
                    # No extra filtering needed for 8036R usually.
                    
                    # Normalize keys for main.py compatibility
                    norm = item.copy() 
                    
                    # Map Keys
                    # 1. Order No (Target for Cancel)
                    norm['orgn_odno'] = item.get('odno') 
                    
                    # 2. Org No (Branch)
                    norm['krx_fwdg_ord_orgno'] = item.get('ord_gno_brno', '')
                    
                    # 3. Numeric Fields
                    if 'ord_unpr' not in norm: norm['ord_unpr'] = item.get('ord_unpr', '0')
                    
                    # Qty Handling
                    # 8036R has 'rmnd_qty', 8001R has 'ord_qty' - 'tot_ccld_qty'
                    if 'rmnd_qty' in item:
                         rem = item['rmnd_qty']
                         norm['ord_qty'] = rem # Treat remaining as order qty for logic
                         norm['ccld_qty'] = '0'
                    else:
                        ord_q = int(item.get('ord_qty', 0))
                        ccld_q = int(item.get('tot_ccld_qty', 0))
                        norm['ord_qty'] = str(ord_q)
                        norm['ccld_qty'] = str(ccld_q)

                    normalized.append(norm)
                    
                return normalized
            else:
                logging.error(f"[KIS] {tr_id} Error: {data['msg1']} (Code: {data['msg_cd']})")
        else:
             logging.error(f"[KIS] 8001R Request Failed: {res.status_code if res else 'None'} | {res.text if res else ''}")

        return []

    def revise_cancel_order(self, org_no, order_no, qty, price, is_cancel=False, order_type="00"):
        """
        Revise (Modify) or Cancel an existing order.
        TR_ID: TTTC0803U (Real) / VTTC0803U (Mock)
        is_cancel: True to cancel, False to modify price/qty
        """
        path = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
        
        tr_id = "VTTC0803U" if self.is_mock else "TTTC0803U"
        
        # Order Cancel/Correction Code
        # 01: Correction (Revise)
        # 02: Cancel
        cncl_dvsn = "02" if is_cancel else "01"
        
        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "KRX_FWDG_ORD_ORGNO": org_no, # Org Code (usually returned in order list)
            "ORGN_ODNO": order_no, # Original Order No
            "ORD_DVSN": order_type, # 00: Limit, 01: Mkt... (for correction)
            "RVSE_CNCL_DVSN_CD": cncl_dvsn, 
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price), # 0 if Cancel
            "QTY_ALL_ORD_YN": "Y" if qty == 0 else "N" # Y if cancelling all remainder? Let's be explicit with qty
        }
        # Safely handle 'Cancel All' if qty is 0, logic might vary. 
        # Better to pass explicit remainder qty.
        if int(qty) == 0:
             body["QTY_ALL_ORD_YN"] = "Y"
        
        res = self._send_request("POST", path, tr_id, body=body)
        if res is None:
             return False, "Network Error"
             
        data = res.json()
        if data['rt_cd'] == '0':
            logging.info(f"[KIS] Order {'Cancel' if is_cancel else 'Revise'} Success: {order_no}")
            return True, data['msg1']
        else:
             logging.error(f"[KIS] Order {'Cancel' if is_cancel else 'Revise'} Failed: {data['msg1']}")
             return False, data['msg1']

    def get_period_trades(self, start_date, end_date):
        """
        Fetch Trade History (Concluded Orders) for a period.
        TR_ID: TTTC8001R (Real) / VTTC8001R (Mock)
        Path: /uapi/domestic-stock/v1/trading/inquire-daily-ccld
        """
        path = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC8001R" if self.is_mock else "TTTC8001R"
        
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": start_date, # YYYYMMDD
            "INQR_END_DT": end_date,   # YYYYMMDD
            "SLL_BUY_DVSN_CD": "00",   # 00: All, 01: Sell, 02: Buy
            "INQR_DVSN": "00",         # 00: Order order? 01: Order No?
            "PDNO": "",
            "CCLD_DVSN": "01",         # 01: Concluded (Executed)
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        res = self._send_request("GET", path, tr_id, params=params)
        if res and res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                return data['output1'] 
            else:
                logging.error(f"[KIS] Period Trades Error: {data['msg1']}")
        return []

    def get_today_filled_info(self, code, side="buy"):
        """
        오늘 특정 종목의 체결 정보를 조회합니다.
        
        Returns:
            dict: {
                'filled_qty': 총 체결 수량,
                'avg_price': 평균 체결가,
                'total_amount': 총 체결 금액,
                'unfilled_qty': 미체결 수량
            }
        """
        tz_kst = pytz.timezone('Asia/Seoul')
        today_str = datetime.now(pytz.utc).astimezone(tz_kst).strftime("%Y%m%d")
        
        result = {
            'filled_qty': 0,
            'avg_price': 0.0,
            'total_amount': 0.0,
            'unfilled_qty': 0
        }
        
        # 1. 체결 내역 조회
        path = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC8001R" if self.is_mock else "TTTC8001R"
        
        side_code = "02" if side == "buy" else "01"  # 02: Buy, 01: Sell
        
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": today_str,
            "INQR_END_DT": today_str,
            "SLL_BUY_DVSN_CD": side_code,
            "INQR_DVSN": "00",
            "PDNO": code,  # 특정 종목만 조회
            "CCLD_DVSN": "00",  # 00: All (체결+미체결)
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        res = self._send_request("GET", path, tr_id, params=params)
        if res and res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                orders = data.get('output1', [])
                
                total_filled_qty = 0
                total_filled_amount = 0.0
                total_unfilled_qty = 0
                
                for order in orders:
                    if order.get('pdno') == code:
                        # 체결 수량
                        filled = int(order.get('tot_ccld_qty', 0))
                        # 체결 금액
                        filled_amt = float(order.get('tot_ccld_amt', 0))
                        # 주문 수량 - 체결 수량 = 미체결
                        ord_qty = int(order.get('ord_qty', 0))
                        unfilled = ord_qty - filled
                        
                        total_filled_qty += filled
                        total_filled_amount += filled_amt
                        total_unfilled_qty += unfilled
                
                result['filled_qty'] = total_filled_qty
                result['total_amount'] = total_filled_amount
                result['unfilled_qty'] = total_unfilled_qty
                
                # 평균 체결가 계산
                if total_filled_qty > 0:
                    result['avg_price'] = total_filled_amount / total_filled_qty
                    
        return result

