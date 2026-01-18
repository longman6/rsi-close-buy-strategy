#!/usr/bin/env python3
"""
KOSDAQ 150 RSI 전략 Clean 백테스트
- 데이터: 2008년부터 다운로드
- 테스트: 2010년부터 시작

파라미터:
- RSI Window: 3
- SMA Window: 70 days
- Buy Limit: RSI < 26.0
- Sell Limit: RSI > 72.0
- Max Positions: 5
- Max Holding: 20 days
- Loss Cooldown: 90 days
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import FinanceDataReader as fdr

# ============================================================
# 설정
# ============================================================
DATA_START_DATE = '2008-01-01'  # 데이터 다운로드 시작일
TEST_START_DATE = '2010-01-01'  # 백테스트 시작일

RSI_WINDOW = 3
SMA_WINDOW = 70
BUY_THRESHOLD = 26
SELL_THRESHOLD = 72
MAX_POSITIONS = 5
MAX_HOLDING_DAYS = 20
LOSS_LOCKOUT_DAYS = 90

INITIAL_CAPITAL = 100_000_000  # 1억원
TX_FEE_RATE = 0.00015   # 0.015% (매수/매도)
TAX_RATE = 0.0020       # 0.2% (매도 시)
SLIPPAGE_RATE = 0.001   # 0.1% (매수/매도)

# ============================================================
# 함수 정의
# ============================================================
def get_kosdaq150_tickers():
    """KOSDAQ 150 종목 코드 로드"""
    filename = 'data/kosdaq150_list.txt'
    tickers = []
    try:
        import ast
        if not os.path.exists(filename):
            print(f"[오류] {filename} 파일이 없습니다.")
            return []
        
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    tickers.append(data['code'])
                except:
                    pass
        return tickers
    except Exception as e:
        print(f"[오류] 종목 리스트 로드 실패: {e}")
        return []

def calculate_rsi(close, window):
    """RSI 계산 (SMA 방식)"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def download_stock_data(tickers, start_date, end_date=None):
    """FinanceDataReader로 주식 데이터 다운로드"""
    stock_data = {}
    valid_tickers = []
    
    total = len(tickers)
    print(f"\n📥 {total}개 종목 데이터 다운로드 시작 ({start_date} ~ 현재)")
    
    for i, ticker in enumerate(tickers, 1):
        try:
            df = fdr.DataReader(ticker, start_date, end_date)
            if df is None or df.empty:
                continue
            
            # 최소 데이터 요구량 확인 (SMA + RSI 계산용)
            if len(df) < SMA_WINDOW + 10:
                continue
            
            # RSI, SMA 계산
            df['RSI'] = calculate_rsi(df['Close'], RSI_WINDOW)
            df['SMA'] = df['Close'].rolling(window=SMA_WINDOW).mean()
            
            stock_data[ticker] = df
            valid_tickers.append(ticker)
            
            if i % 30 == 0:
                print(f"  진행: {i}/{total} ({i/total*100:.1f}%)")
                
        except Exception as e:
            pass  # 실패 종목 무시
    
    print(f"\n✅ 다운로드 완료: {len(valid_tickers)}개 종목")
    return stock_data, valid_tickers

def run_backtest(stock_data, valid_tickers, start_date):
    """백테스트 실행"""
    print(f"\n⏳ 백테스트 실행 중 ({start_date} ~ 현재)...")
    
    allocation_per_stock = 1.0 / MAX_POSITIONS
    
    # 모든 거래일 수집
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    # 테스트 시작일 이후만 필터
    test_start = pd.to_datetime(start_date)
    all_dates = [d for d in all_dates if d >= test_start]
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    lockout_until = {}
    
    for date in all_dates:
        # 1. 보유 종목 평가 및 매도
        current_positions_value = 0
        tickers_to_sell = []
        
        for ticker, pos in positions.items():
            pos['held_bars'] += 1
            
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']
                
                # 매도 조건
                if rsi >= SELL_THRESHOLD:
                    tickers_to_sell.append({'ticker': ticker, 'reason': 'SIGNAL'})
                elif pos['held_bars'] >= MAX_HOLDING_DAYS:
                    tickers_to_sell.append({'ticker': ticker, 'reason': 'FORCE'})
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price
        
        total_equity = cash + current_positions_value
        history.append({'Date': date, 'Equity': total_equity})
        
        # 매도 실행
        for item in tickers_to_sell:
            ticker = item['ticker']
            reason = item['reason']
            
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            # 수익률 계산
            buy_total_cost = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_return = ((sell_amt - cost) - buy_total_cost) / buy_total_cost * 100
            
            trades.append({
                'Ticker': ticker,
                'BuyDate': pos['buy_date'],
                'SellDate': date,
                'BuyPrice': pos['buy_price'],
                'SellPrice': sell_price,
                'Return': net_return,
                'Reason': reason,
                'Days': pos['held_bars']
            })
            
            # 손실 락아웃
            price_return = sell_price - pos['buy_price']
            if price_return < 0 and LOSS_LOCKOUT_DAYS > 0:
                lockout_end = date + timedelta(days=LOSS_LOCKOUT_DAYS)
                lockout_until[ticker] = lockout_end
        
        # 매도 후 자산 재계산
        current_positions_value = sum(p['shares'] * p['last_price'] for p in positions.values())
        total_equity = cash + current_positions_value
        
        # 2. 매수
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            buy_candidates = []
            
            for ticker in valid_tickers:
                if ticker in positions:
                    continue
                
                # 락아웃 체크
                if ticker in lockout_until:
                    if date <= lockout_until[ticker]:
                        continue
                    else:
                        del lockout_until[ticker]
                
                df = stock_data[ticker]
                if date not in df.index:
                    continue
                
                row = df.loc[date]
                if pd.isna(row['SMA']) or pd.isna(row['RSI']):
                    continue
                
                # 매수 조건: SMA 위 & RSI <= BUY_THRESHOLD
                if row['Close'] > row['SMA'] and row['RSI'] <= BUY_THRESHOLD:
                    buy_candidates.append({
                        'ticker': ticker,
                        'rsi': row['RSI'],
                        'price': row['Close']
                    })
            
            if buy_candidates:
                buy_candidates.sort(key=lambda x: x['rsi'])
                
                for candidate in buy_candidates[:open_slots]:
                    # 자산 재계산
                    current_positions_value = sum(p['shares'] * p['last_price'] for p in positions.values())
                    total_equity = cash + current_positions_value
                    
                    target_amt = total_equity * allocation_per_stock
                    invest_amt = min(target_amt, cash)
                    max_buy_val = invest_amt / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy_val < 10000:
                        continue
                    
                    shares = int(max_buy_val / candidate['price'])
                    if shares > 0:
                        buy_val = shares * candidate['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[candidate['ticker']] = {
                            'shares': shares,
                            'buy_price': candidate['price'],
                            'last_price': candidate['price'],
                            'buy_date': date,
                            'held_bars': 0
                        }
    
    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)
    
    if hist_df.empty:
        return 0, 0, 0, 0, pd.DataFrame(), pd.DataFrame()
    
    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100
    
    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
    
    return final_ret, mdd, win_rate, len(trades_df), hist_df, trades_df

def main():
    print("=" * 70)
    print("🚀 KOSDAQ 150 RSI 전략 백테스트 (Clean Test)")
    print("=" * 70)
    
    print(f"""
📋 파라미터:
  - RSI Window: {RSI_WINDOW}
  - SMA Window: {SMA_WINDOW} days
  - Buy Limit: RSI < {BUY_THRESHOLD}
  - Sell Limit: RSI > {SELL_THRESHOLD}
  - Max Positions: {MAX_POSITIONS}
  - Max Holding: {MAX_HOLDING_DAYS} days
  - Loss Cooldown: {LOSS_LOCKOUT_DAYS} days
  - 데이터: {DATA_START_DATE} ~ 현재
  - 테스트: {TEST_START_DATE} ~ 현재
""")
    print("-" * 70)
    
    # 종목 로드
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("❌ 종목 로드 실패")
        return
    print(f"📊 종목 수: {len(tickers)}개")
    
    # 데이터 다운로드
    stock_data, valid_tickers = download_stock_data(tickers, DATA_START_DATE)
    
    if not valid_tickers:
        print("❌ 유효한 데이터가 없습니다")
        return
    
    # 백테스트 실행
    ret, mdd, win_rate, trade_count, hist_df, trades_df = run_backtest(
        stock_data, valid_tickers, TEST_START_DATE
    )
    
    # 결과 출력
    print("\n" + "=" * 70)
    print("📊 백테스트 결과")
    print("=" * 70)
    
    final_equity = hist_df['Equity'].iloc[-1] if not hist_df.empty else INITIAL_CAPITAL
    
    print(f"""
┌────────────────────────────────────────────────────────────────┐
│                      백테스트 결과 요약                        │
├────────────────────┬───────────────────────────────────────────┤
│  초기 자본금       │  {INITIAL_CAPITAL:>30,}원  │
│  최종 자산         │  {final_equity:>30,.0f}원  │
│  총 수익률         │  {ret:>30.2f}%  │
│  MDD               │  {mdd:>30.2f}%  │
│  승률              │  {win_rate:>30.2f}%  │
│  총 거래 수        │  {trade_count:>30,}회  │
└────────────────────┴───────────────────────────────────────────┘
""")
    
    # 연도별 성과
    if not hist_df.empty:
        hist_df['Year'] = hist_df.index.year
        years = sorted(hist_df['Year'].unique())
        
        print("\n📅 연도별 성과:")
        print("-" * 50)
        
        prev_equity = INITIAL_CAPITAL
        for year in years:
            year_data = hist_df[hist_df['Year'] == year]
            if year_data.empty:
                continue
            
            end_equity = year_data['Equity'].iloc[-1]
            year_ret = (end_equity / prev_equity - 1) * 100
            
            # 연도별 MDD
            norm_eq = year_data['Equity'] / prev_equity
            year_mdd = ((norm_eq - norm_eq.cummax()) / norm_eq.cummax()).min() * 100
            
            print(f"  {year}년: 수익률 {year_ret:>+8.2f}% | MDD {year_mdd:>7.2f}%")
            prev_equity = end_equity
    
    # 보고서 저장
    os.makedirs('reports', exist_ok=True)
    report_path = 'reports/clean_backtest_report.md'
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"""# KOSDAQ 150 RSI 전략 백테스트 결과
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 파라미터
| 항목 | 값 |
|:---|:---|
| RSI Window | {RSI_WINDOW} |
| SMA Window | {SMA_WINDOW} days |
| Buy Limit | RSI < {BUY_THRESHOLD} |
| Sell Limit | RSI > {SELL_THRESHOLD} |
| Max Positions | {MAX_POSITIONS} |
| Max Holding | {MAX_HOLDING_DAYS} days |
| Loss Cooldown | {LOSS_LOCKOUT_DAYS} days |
| 데이터 기간 | {DATA_START_DATE} ~ 현재 |
| 테스트 기간 | {TEST_START_DATE} ~ 현재 |

## 성과 요약
| 지표 | 값 |
|:---|---:|
| 초기 자본금 | {INITIAL_CAPITAL:,}원 |
| 최종 자산 | {final_equity:,.0f}원 |
| **총 수익률** | **{ret:.2f}%** |
| MDD | {mdd:.2f}% |
| 승률 | {win_rate:.2f}% |
| 거래 수 | {trade_count:,}회 |
""")
    
    print(f"\n✅ 보고서 저장: {report_path}")
    print(f"⏰ 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
