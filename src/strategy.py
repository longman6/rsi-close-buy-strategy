import pandas as pd
import numpy as np
import logging
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
        # SMA 
        df['SMA'] = df['Close'].rolling(window=self.sma_window).mean()
        
        # RSI (Wilder's Smoothing version - Standard)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        
        # Wilder's Smoothing: alpha = 1/N
        avg_gain = gain.ewm(alpha=1/self.rsi_window, min_periods=self.rsi_window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/self.rsi_window, min_periods=self.rsi_window, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df
    
    def calculate_extended_indicators(self, df):
        """
        AI 프롬프트용 확장 지표 계산.
        Returns dict with additional indicators for the latest row.
        """
        if df.empty or len(df) < 60:
            return None
            
        latest = df.iloc[-1]
        
        # RSI(3) 계산
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        
        avg_gain_3 = gain.ewm(com=2, min_periods=3, adjust=False).mean()
        avg_loss_3 = loss.ewm(com=2, min_periods=3, adjust=False).mean()
        rs_3 = avg_gain_3 / avg_loss_3
        rsi_3_series = 100 - (100 / (1 + rs_3))
        rsi_3 = rsi_3_series.iloc[-1] if not pd.isna(rsi_3_series.iloc[-1]) else 0
        
        # RSI(14) 계산
        avg_gain_14 = gain.ewm(com=13, min_periods=14, adjust=False).mean()
        avg_loss_14 = loss.ewm(com=13, min_periods=14, adjust=False).mean()
        rs_14 = avg_gain_14 / avg_loss_14
        rsi_14_series = 100 - (100 / (1 + rs_14))
        rsi_14 = rsi_14_series.iloc[-1] if not pd.isna(rsi_14_series.iloc[-1]) else 0
        
        # 거래량 지표
        current_volume = latest.get('Volume', 0)
        avg_vol_5d = df['Volume'].tail(5).mean() if 'Volume' in df.columns else 0
        avg_vol_20d = df['Volume'].tail(20).mean() if 'Volume' in df.columns else 0
        volume_ratio = (current_volume / avg_vol_20d * 100) if avg_vol_20d > 0 else 0
        
        # 이동평균선 계산
        ma_20 = df['Close'].rolling(window=20).mean().iloc[-1]
        ma_60 = df['Close'].rolling(window=60).mean().iloc[-1]
        
        current_price = latest['Close']
        
        # 이평선 대비 이격도(%)
        dist_20ma = ((current_price / ma_20) - 1) * 100 if not pd.isna(ma_20) and ma_20 > 0 else 0
        dist_60ma = ((current_price / ma_60) - 1) * 100 if not pd.isna(ma_60) and ma_60 > 0 else 0
        
        return {
            'current_price': float(current_price),
            'rsi_3': float(rsi_3),
            'rsi_14': float(rsi_14),
            'avg_vol_5d': float(avg_vol_5d),
            'avg_vol_20d': float(avg_vol_20d),
            'volume_ratio': float(volume_ratio),
            'dist_20ma': float(dist_20ma),
            'dist_60ma': float(dist_60ma)
        }

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
        # 1. Close > SMA
        #    User Request: RSI(3) or RSI(5), SMA(Moving Average).
        #    So we check: Close > SMA(config.SMA_WINDOW).
        #    So we check: Close > SMA(config.SMA_WINDOW).
        
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
