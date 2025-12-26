import pandas as pd
import numpy as np
from src.strategy import Strategy
from src.kis_client import KISClient

# Mock KIS Client
class MockKISClient(KISClient):
    def __init__(self):
        print("[Mock] Initialized Mock KIS Client")
        self.account_no = "12345678"
    
    def get_balance(self):
        return {
            'cash_available': 10000000.0, # 10M KRW
            'holdings': [
                {'pdno': '000001', 'prdt_name': 'HoldingStock', 'hldg_qty': '10', 'prpr': '50000', 'pchs_avg_pric': '48000'}
            ]
        }
    
    def get_daily_ohlcv(self, code, period_code="D"):
        # Create dummy data
        dates = pd.date_range(end=pd.Timestamp.now(), periods=150)
        data = {
            'Date': dates,
            'Close': np.linspace(10000, 11000, 150),
            'Open': np.linspace(10000, 11000, 150),
            'High': np.linspace(10050, 11050, 150),
            'Low': np.linspace(9950, 10950, 150),
            'Volume': np.random.randint(1000, 100000, 150)
        }
        df = pd.DataFrame(data)
        
        # Inject Signals
        if code == 'BUY_CANDIDATE':
            # Force RSI Low
            df.iloc[-5:, 1] = [11000, 10500, 10000, 9500, 9000] # Sharp Drop
            # Ensure Close > SMA(100)
            # SMA100 of linspace 10000-11000 is around 10500? 
            # Let's manually set SMA to be lower than Close?
            # Or just let Strategy calc it.
            # If we drop too much, price < SMA.
            # We need Price > SMA but RSI < 35.
            # This happens in pullbacks of uptrends.
            # Let's simulate uptrend then small dip.
            base = np.linspace(10000, 20000, 150)
            df['Close'] = base
            # SMA100 will be around 15000 at end.
            # Drop price to 16000 (still > SMA) but fast enough for RSI dip?
            df.iloc[-1, 1] = 16000 # Close
            df.iloc[-2, 1] = 18000
            df.iloc[-3, 1] = 19000
            
        elif code == 'SELL_CANDIDATE':
            # Force RSI High
            # Rapid rise
            df.iloc[-1, 1] = 25000
            df.iloc[-2, 1] = 23000
            df.iloc[-3, 1] = 21000
            
        elif code == '000001': # Holding stock
            # Let's make it RSI > 70 to test sell
            df.iloc[-1, 1] = 60000 # Jump from 50000
            df.iloc[-2, 1] = 58000
            df.iloc[-3, 1] = 56000
            
        return df

    def send_order(self, code, qty, side="buy", price=0):
        print(f"[Mock] Order Sent: {side.upper()} {code} {qty}ea")
        return True, "Mock Success"

def test_strategy():
    strategy = Strategy()
    mock_kis = MockKISClient()
    
    print("\n--- Test 1: Sell Logic ---")
    # We hold 000001. Mock data returns high RSI.
    df = mock_kis.get_daily_ohlcv('000001')
    df = strategy.calculate_indicators(df)
    rsi = df.iloc[-1]['RSI']
    sell = strategy.check_sell_signal('000001', df)
    print(f"Stock 000001 RSI: {rsi:.2f}, Should Sell? {sell}")
    assert sell == True
    
    print("\n--- Test 2: Buy Logic ---")
    # 'BUY_CANDIDATE' has sharp drop but High SMA
    df = mock_kis.get_daily_ohlcv('BUY_CANDIDATE')
    df = strategy.calculate_indicators(df)
    signal = strategy.analyze_stock('BUY_CANDIDATE', df)
    print(f"Buy Candidate Signal: {signal}")
    if signal:
        print(f"RSI: {signal['rsi']:.2f}, Close: {signal['close']}, SMA: {signal['sma']:.2f}")
        assert signal['rsi'] < 35
        assert signal['close'] > signal['sma']
        
    print("\n--- Test Complete ---")

if __name__ == "__main__":
    test_strategy()
