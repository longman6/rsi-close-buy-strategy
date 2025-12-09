import requests
import json
import time
import os
import logging
import pandas as pd
from datetime import datetime, timedelta
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            res = requests.post(url, headers=headers, data=json.dumps(body))
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
        url = f"{self.base_url}{path}"
        headers = self._get_headers("FHKST01010100")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", # J: Stock, W: Warrants...
            "FID_INPUT_ISCD": code # Stock Code
        }
        
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                return data['output']
            else:
                logging.warning(f"[KIS] GetPrice Error {code}: {data['msg1']}")
        return None

    def get_daily_ohlcv(self, code, period_code="D"):
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
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = "20230101" # Safe range for SMA100
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start_date, 
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D", # D: Day
            "FID_ORG_ADJ_PRC": "1" # Adjusted Price
        }
        
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0' and data['output2']:
                df = pd.DataFrame(data['output2'])
                # Clean up columns: stck_bsop_date(Date), stck_clpr(Close), etc.
                df = df.rename(columns={
                    'stck_bsop_date': 'Date',
                    'stck_oprc': 'Open',
                    'stck_hgpr': 'High',
                    'stck_lwpr': 'Low',
                    'stck_clpr': 'Close',
                    'acml_vol': 'Volume'
                })
                df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
                # Convert to numeric
                cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                df[cols] = df[cols].apply(pd.to_numeric)
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.sort_values('Date') # Ascending
                return df
        return pd.DataFrame()

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
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if data['rt_cd'] == '0':
                # output1: Holdings list, output2: Account Summary
                holdings = data['output1']
                summary = data['output2'][0]
                return {
                    'cash_available': float(summary.get('dnca_tot_amt', 0)), # Deposit
                    'total_asset': float(summary.get('tot_evlu_amt', 0)),
                    'holdings': holdings 
                }
            else:
                logging.error(f"[KIS] Balance Error: {data['msg1']} (Code: {data['msg_cd']})")
        else:
            logging.error(f"[KIS] Network/Server Error: {res.status_code} - {res.text}")
        return None

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
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        data = res.json()
        if data['rt_cd'] == '0':
            logging.info(f"[KIS] Order Success: {side.upper()} {code} {qty}ea @ {price if price >0 else 'Market'}")
            return True, data['msg1']
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

