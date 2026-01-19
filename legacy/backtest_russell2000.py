#!/usr/bin/env python3
"""
Russell 2000 상위 200개 종목 RSI 전략 백테스트 스크립트
- KOSDAQ 150에서 사용한 동일한 RSI 전략을 미국 소형주에 적용
- yfinance를 사용하여 Russell 2000 구성종목 데이터 다운로드
"""
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    print("yfinance가 설치되어 있지 않습니다. 설치 중...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'yfinance'])
    import yfinance as yf

# ---------------------------------------------------------
# 설정
# ---------------------------------------------------------
START_DATE = '2015-01-01'
INITIAL_CAPITAL = 100000  # $100,000 (달러)
TX_FEE_RATE = 0.0001      # 0.01% (미국은 수수료가 낮음)
TAX_RATE = 0.0000         # 단기 매매는 세금 별도 처리
SLIPPAGE_RATE = 0.001     # 0.1%

# KOSDAQ 150 최적 파라미터 (공격형)
STRATEGIES = {
    "KOSDAQ_BEST": {
        "rsi_window": 3,
        "buy_threshold": 20,
        "sell_threshold": 80,
        "sma_window": 50,
        "max_positions": 3,
        "max_holding_days": 10
    },
    "KOSDAQ_STABLE": {
        "rsi_window": 3,
        "buy_threshold": 20,
        "sell_threshold": 75,
        "sma_window": 150,
        "max_positions": 7,
        "max_holding_days": 20
    }
}

# ---------------------------------------------------------
# Russell 2000 상위 200개 종목 가져오기
# ---------------------------------------------------------
def get_russell2000_top200():
    """
    Russell 2000 ETF (IWM) 구성종목 중 상위 200개 추정
    실제로는 시가총액 순으로 정렬해야 하지만, 
    여기서는 대표적인 Russell 2000 소형주들을 사용
    """
    # Russell 2000 대표 종목들 (시가총액 상위)
    # 실제 전체 리스트는 약 2000개이므로 상위 200개 추정 사용
    tickers = [
        # 헬스케어
        "AXSM", "LNTH", "ITCI", "CRSP", "XENE", "ALNY", "SRPT", "BMRN", "EXAS", "HALO",
        "IONS", "RARE", "NBIX", "ARVN", "FOLD", "KRYS", "RPRX", "PCVX", "VERV", "DAWN",
        # 테크
        "CRDO", "RMBS", "CALX", "POWI", "DIOD", "ICHR", "ONTO", "CRUS", "LSCC", "SLAB",
        "CGNX", "NOVT", "OLED", "MTSI", "PSTG", "DDOG", "NET", "CFLT", "MDB", "ESTC",
        # 산업재
        "EXPO", "RBC", "GNRC", "TREX", "SITE", "AAON", "CSL", "AZEK", "FBIN", "UFPI",
        "BLDR", "POOL", "WSO", "GTES", "AGCO", "AWI", "ROLL", "CW", "SPSC", "TNET",
        # 금융
        "HOMB", "FIBK", "GBCI", "SFBS", "TCBI", "ABCB", "SBCF", "PNFP", "CVBF", "HWC",
        "CADE", "WAFD", "UMBF", "WSFS", "DCOM", "NBTB", "FCNCA", "COLB", "HTLF", "BHLB",
        # 소비재
        "BOOT", "PLNT", "BROS", "SHAK", "WING", "TXRH", "CAKE", "BJRI", "DIN", "PLAY",
        "RH", "WSM", "FIVE", "OLLI", "PRPL", "LOVE", "LE", "BIRD", "EVGO", "WRBY",
        # 에너지
        "MTDR", "CIVI", "CHRD", "SM", "PDCE", "MGY", "REPX", "ESTE", "VTLE", "TALO",
        "NOG", "GPRE", "CLNE", "BE", "PLUG", "FCEL", "BLDP", "RUN", "ARRY", "SEDG",
        # 원자재
        "ATI", "CMC", "CLF", "STLD", "RS", "AL", "KALU", "CENX", "HAYN", "ZEUS",
        "SON", "SEE", "BCC", "OLN", "OLIN", "EMN", "FUL", "RPM", "AXTA", "ASIX",
        # 유틸리티
        "ALE", "AVA", "BKH", "IDA", "NWE", "OGS", "PNM", "SJI", "SWX", "UTL",
        # 부동산
        "NSA", "CUBE", "EXR", "LSI", "REXR", "STAG", "TRNO", "PLD", "FR", "COLD",
        "EPR", "SRC", "PINE", "INN", "SHO", "APLE", "RHP", "PEB", "DRH", "HT",
        # 통신
        "USM", "LUMN", "BAND", "CCOI", "SHEN", "GOGO", "TMUS", "IRDM", "GSAT", "ASTS",
        # 추가 종목
        "AXON", "CVLT", "LOGI", "LULU", "DECK", "SFIX", "AN", "LAD", "ABG", "SAH",
        "GPI", "PAG", "KMX", "CPRT", "COPART", "IAA", "ACV", "CARS", "VRM", "CVNA"
    ]
    
    return tickers[:200]  # 상위 200개만

def calculate_rsi(data, window):
    """RSI 계산"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def download_data(tickers):
    """데이터 다운로드"""
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
    fetch_start = (start_dt - timedelta(days=300)).strftime("%Y-%m-%d")
    
    print(f"📥 {len(tickers)}개 종목 데이터 다운로드 중...")
    raw_data = {}
    valid_tickers = []
    
    # 배치로 다운로드 (더 빠름)
    try:
        data = yf.download(tickers, start=fetch_start, progress=False, threads=True)
        
        for ticker in tickers:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    df = data.xs(ticker, axis=1, level=1)
                else:
                    df = data
                
                if df is not None and not df.empty and len(df) > 200:
                    # NaN 제거
                    df = df.dropna()
                    if len(df) > 200:
                        raw_data[ticker] = df
                        valid_tickers.append(ticker)
            except:
                continue
                
    except Exception as e:
        print(f"배치 다운로드 실패, 개별 다운로드로 전환: {e}")
        for i, ticker in enumerate(tickers):
            try:
                df = yf.download(ticker, start=fetch_start, progress=False)
                if df is not None and not df.empty and len(df) > 200:
                    raw_data[ticker] = df
                    valid_tickers.append(ticker)
                if (i + 1) % 50 == 0:
                    print(f"   진행: {i+1}/{len(tickers)}")
            except:
                continue
    
    print(f"✅ {len(valid_tickers)}개 종목 다운로드 완료")
    return raw_data, valid_tickers

def prepare_data(raw_data, rsi_window, sma_window):
    """지표 계산"""
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
    stock_data = {}
    valid_tickers = []
    
    for ticker, df in raw_data.items():
        try:
            df = df.copy()
            if len(df) < max(sma_window, rsi_window) + 10:
                continue
            
            df['SMA'] = df['Close'].rolling(window=sma_window).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)
            df = df[df.index >= start_dt]
            
            if not df.empty and len(df) > 50:
                stock_data[ticker] = df
                valid_tickers.append(ticker)
        except:
            continue
    
    return stock_data, valid_tickers

def run_simulation(stock_data, valid_tickers, cfg):
    """백테스트 실행"""
    max_positions = cfg['max_positions']
    buy_threshold = cfg['buy_threshold']
    sell_threshold = cfg['sell_threshold']
    max_holding_days = cfg['max_holding_days']
    
    allocation = 1.0 / max_positions
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    
    for date in all_dates:
        # 평가 & 매도
        current_value = 0
        to_sell = []
        
        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                price = df.loc[date, 'Close']
                pos['last_price'] = price
                rsi = df.loc[date, 'RSI']
                
                if rsi >= sell_threshold:
                    to_sell.append({'ticker': ticker, 'reason': 'SIGNAL'})
                elif pos['held_bars'] >= max_holding_days:
                    to_sell.append({'ticker': ticker, 'reason': 'FORCE'})
            else:
                price = pos['last_price']
            current_value += pos['shares'] * price
        
        total_equity = cash + current_value
        history.append({'Date': date, 'Equity': total_equity})
        
        # 매도 실행
        for item in to_sell:
            ticker = item['ticker']
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            buy_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_return = ((sell_amt - cost) - buy_cost) / buy_cost * 100
            trades.append({'Return': net_return})
        
        # 매수
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row['SMA']) or pd.isna(row['RSI']): continue
                
                if row['Close'] > row['SMA'] and row['RSI'] <= buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for c in candidates[:open_slots]:
                    current_value = sum(p['shares'] * p['last_price'] for p in positions.values())
                    total_equity = cash + current_value
                    
                    target = total_equity * allocation
                    invest = min(target, cash)
                    max_buy = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy < 100: continue
                    shares = int(max_buy / c['price'])
                    if shares > 0:
                        buy_val = shares * c['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[c['ticker']] = {
                            'shares': shares,
                            'buy_price': c['price'],
                            'last_price': c['price'],
                            'held_bars': 0
                        }
        
        for pos in positions.values():
            pos['held_bars'] += 1
    
    # 결과 계산
    if not history:
        return 0, 0, 0, 0
    
    hist_df = pd.DataFrame(history).set_index('Date')
    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100
    
    trades_df = pd.DataFrame(trades)
    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
    
    return final_ret, mdd, win_rate, len(trades_df)

def main():
    print("="*60)
    print("🚀 Russell 2000 상위 200 RSI 전략 백테스트")
    print("="*60)
    print(f"테스트 기간: {START_DATE} ~ 현재")
    print(f"초기 자본: ${INITIAL_CAPITAL:,}")
    print("="*60)
    
    # 종목 가져오기
    tickers = get_russell2000_top200()
    print(f"\n📊 테스트 종목: {len(tickers)}개")
    
    # 데이터 다운로드
    raw_data, valid_tickers = download_data(tickers)
    
    if not raw_data:
        print("❌ 데이터 다운로드 실패")
        return
    
    results = []
    
    for strategy_name, cfg in STRATEGIES.items():
        print(f"\n>>> [{strategy_name}] 실행 중...")
        print(f"    RSI {cfg['rsi_window']}, BUY<{cfg['buy_threshold']}, SELL>{cfg['sell_threshold']}, SMA {cfg['sma_window']}")
        
        stock_data, valid = prepare_data(raw_data, cfg['rsi_window'], cfg['sma_window'])
        print(f"    유효 종목: {len(valid)}개")
        
        ret, mdd, win_rate, count = run_simulation(stock_data, valid, cfg)
        
        results.append({
            'Strategy': strategy_name,
            'Return': ret,
            'MDD': mdd,
            'WinRate': win_rate,
            'Trades': count
        })
        
        print(f"    👉 결과: 수익률 {ret:.2f}%, MDD {mdd:.2f}%, 승률 {win_rate:.1f}%, 거래 {count}회")
    
    # 결과 출력
    print("\n" + "="*60)
    print("📊 Russell 2000 백테스트 결과")
    print("="*60)
    
    print("\n| 전략 | 수익률 | MDD | 승률 | 거래수 |")
    print("|:---|---:|---:|---:|---:|")
    for r in results:
        print(f"| {r['Strategy']} | {r['Return']:.2f}% | {r['MDD']:.2f}% | {r['WinRate']:.1f}% | {r['Trades']} |")
    
    # 리포트 저장
    report_path = "reports/russell2000_backtest_report.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Russell 2000 상위 200 RSI 전략 백테스트 리포트\n\n")
        f.write(f"**생성일:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**테스트 기간:** {START_DATE} ~ 현재\n\n")
        f.write(f"**초기 자본:** ${INITIAL_CAPITAL:,}\n\n")
        f.write(f"**테스트 종목:** {len(valid_tickers)}개\n\n")
        f.write("## 결과 요약\n\n")
        f.write("| 전략 | 수익률 | MDD | 승률 | 거래수 |\n")
        f.write("|:---|---:|---:|---:|---:|\n")
        for r in results:
            f.write(f"| {r['Strategy']} | {r['Return']:.2f}% | {r['MDD']:.2f}% | {r['WinRate']:.1f}% | {r['Trades']} |\n")
    
    print(f"\n✅ 리포트 저장: {report_path}")

if __name__ == "__main__":
    main()
