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
        Get KOSDAQ 150 Tickers using PyKRX (Index 2203).
        Returns a list of ticker codes (strings).
        """
        try:
            from pykrx import stock
            # KOSDAQ 150 Index Code: 2203
            tickers = stock.get_index_portfolio_deposit_file("2203")
            return tickers
            
        except Exception as e:
            print(f"[Strategy] PyKRX Universe Error: {e}")
            print("[Strategy] Using Fallback KOSDAQ Top list.")
            # Fallback List (Major KOSDAQ 150 components)
            return [
                '247540', '086520', '028300', '066970', '403870', 
                '035900', '025980', '293490', '068270', '357780',
                '402280', '112040'
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
            
        if latest['Close'] > latest['SMA'] and latest['RSI'] <= self.rsi_buy_threshold:
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
            
        if latest['RSI'] >= self.rsi_sell_threshold:
            return True
            
        return False
