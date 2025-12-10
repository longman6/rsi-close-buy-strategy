import pandas as pd
import numpy as np

import config

class Strategy:
    def __init__(self):
        self.rsi_window = config.RSI_WINDOW
        self.sma_window = config.SMA_WINDOW
        self.rsi_buy_threshold = config.RSI_BUY_THRESHOLD
        self.rsi_sell_threshold = config.RSI_SELL_THRESHOLD
        
    def get_universe(self):
        """
        Get KOSDAQ 150 Tickers.
        Returns a list of ticker codes (without .KQ extension usually for KIS API if KIS uses 6 digits).
        KIS uses 6 digits e.g. '005930'. FDR uses '005930'.
        """
        try:
            import FinanceDataReader as fdr
            # KOSDAQ 150 Index Members
            # Note: FDR might not have a direct 'KOSDAQ 150' list in all versions.
            # Using KOSDAQ market cap top 150 is a good approximation if index list fails,
            # but FDR usually supports 'KOSDAQ'.
            # Ideally we want the actual constituents. 
            # For simplicity and robustness as per previous script:
            df_krx = fdr.StockListing('KOSDAQ')
            
            # Filter Strategy:
            # 1. Market Cap Top 150 (approx for KOSDAQ 150)
            # 2. Filter out Admin Issues (Managed Items)
            
            # Check for Admin Issue column
            # Common columns: Code, Name, Market, Dept, Close, ChangeCode, Changes, ChagesRatio, Open, High, Low, Volume, Amount, Marcap, Stocks, MarketId
            # 'Dept' often contains '관리' (Admin) or '환기' (Caution)?
            # 'Market' might be 'KOSDAQ GLOBAL', 'KOSDAQ' etc.
            
            # Sort by Marcap
            col = 'Marcap' if 'Marcap' in df_krx.columns else 'Amount'
            if col in df_krx.columns:
                df_krx = df_krx.sort_values(by=col, ascending=False)
            
            # Basic Management Exclusion if column exists
            # (Note: This is a heuristic. For strict KOSDAQ 150, one should check the index composition specifically, 
            # but simple Market Cap top is accepted practice in the backtest provided).
            
            # Exclude SPACs, etc? User said "Managed Items".
            # If 'Dept' column exists, check for '관리'.
            if 'Dept' in df_krx.columns:
                 df_krx = df_krx[~df_krx['Dept'].astype(str).str.contains('관리', na=False)]
                 
            # Take top 150
            top_150 = df_krx.head(150)
            return top_150['Code'].tolist()
            
        except Exception as e:
            print(f"[Strategy] Error getting universe or FDR missing: {e}")
            # Fallback to a small static list or return empty
            print("[Strategy] Using Fallback KOSDAQ Top list.")
            # Top KOSDAQ stocks (Example list) - Ideally user should install FDR
            return [
                '247540', '086520', '091990', '022100', '066970', # Ecopro BM, Ecopro, Celltrion Pharm, POSCO DX...
                '028300', '293490', '263750', '216080', '035900',
                '041510', '005290', '039030', '000250', '237690'
            ]

    def calculate_indicators(self, df):
        """
        Calculate RSI and SMA.
        df must have 'Close' column.
        Returns df with 'RSI' and 'SMA' columns.
        """
        if len(df) < self.sma_window:
            return df
        
        # SMA
        df['SMA'] = df['Close'].rolling(window=self.sma_window).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        
        # Use Wilder's Smoothing (Standard RSI)
        avg_gain = gain.ewm(com=self.rsi_window - 1, min_periods=self.rsi_window, adjust=False).mean()
        avg_loss = loss.ewm(com=self.rsi_window - 1, min_periods=self.rsi_window, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df

    def analyze_stock(self, code, df):
        """
        Analyze a single stock dataframe.
        Returns:
            dict with { 'code': ..., 'rsi': ..., 'close': ..., 'sma': ... } if BUY signal.
            None if no signal.
        """
        if df.empty or len(df) < self.sma_window:
            return None
            
        # Get latest closed candle (assuming running before market open, so use last row)
        # If running intra-day, last row might be incomplete. 
        # But 'daily-itemchartprice' usually gives confirmed daily candles up to yesterday 
        # unless queried during market with specific flags.
        # We will look at the LAST available completed day.
        # If today is 2024-05-20 and time is 08:30, last row should be 2024-05-19 (or last trading day).
        
        latest = df.iloc[-1]
        
        # Conditions:
        # 1. Close > SMA(100) (User said "Broad market up? No, code said Close > SMA200", 
        #    Plan: RSI(3), SMA(100).
        #    Backtest code checks: row['Close'] > row['SMA200']
        #    User Request: RSI(3), SMA(100).
        #    So we check: Close > SMA(100).
        
        if pd.isna(latest['SMA']) or pd.isna(latest['RSI']):
            return None
            
        if latest['Close'] > latest['SMA'] and latest['RSI'] < self.rsi_buy_threshold:
            return {
                'code': code,
                'rsi': latest['RSI'],
                'close': latest['Close'],
                'sma': latest['SMA']
            }
        return None

    def check_sell_signal(self, code, df, purchase_price=None):
        """
        Check if we should sell.
        Condition: RSI > 70.
        """
        if df.empty:
            return False
            
        latest = df.iloc[-1]
        if pd.isna(latest['RSI']):
            return False
            
        if latest['RSI'] > self.rsi_sell_threshold:
            return True
            
        return False
