# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RSI_POWER_ZONE is an automated Korean stock trading bot that implements an RSI-based mean-reversion strategy on KOSDAQ 150 stocks using the Korea Investment & Securities (KIS) API. The system includes AI-powered buy recommendations via Google Gemini, trade execution, position management, and real-time Slack notifications.

## Core Architecture

### Main Components

1. **main.py**: Orchestrates the daily trading loop with scheduled tasks (morning analysis, pre-market orders, order monitoring, sell execution)
2. **src/kis_client.py**: KIS API wrapper handling OAuth, price data, balance queries, order execution, and stock safety checks
3. **src/strategy.py**: Implements RSI(3) + SMA(100) strategy logic for buy/sell signals
4. **src/trade_manager.py**: Manages trade history, holding periods, forced sells, and loss cooldown tracking
5. **src/gemini_client.py**: Queries Google Gemini AI for buy recommendations based on recent news
6. **src/db_manager.py**: SQLite persistence for Gemini advice history
7. **src/slack_bot.py**: Slack notifications for trading events
8. **dashboard.py**: Streamlit dashboard to view Gemini advice results
9. **run_daily_advice.py**: Standalone job that runs Gemini analysis on low-RSI candidates

### Daily Trading Flow

The bot operates on a strict schedule (configured in config.py):

1. **07:00-07:30**: Gemini AI analyzes low-RSI stocks and provides buy recommendations
2. **08:30**: Morning analysis - calculates RSI for KOSDAQ 150, filters candidates
3. **08:57**: Pre-market orders - places limit orders at expected price + 5 ticks
4. **09:05-15:20**: Continuous order monitoring - modifies unfilled orders to current price (cancels if price rises >5%)
5. **15:20**: Sell signal check - identifies positions with RSI > 70 or max holding period exceeded
6. **15:26**: Sell execution - executes market orders for flagged positions

### Key Trading Rules

- **Buy Conditions**: RSI(3) < 35 AND Close > SMA(100) AND not in exclusion list AND not in loss cooldown
- **Sell Conditions**: RSI(3) > 70 OR holding period > 38 days
- **Position Limits**: Maximum 5 concurrent positions
- **Position Sizing**: Fixed KRW amount per stock (default: 1,000,000 KRW)
- **Loss Cooldown**: 40-day cooldown after selling at a loss
- **Stock Filtering**: Automatically excludes suspended/admin-issue/warning stocks

## Development Commands

### Running the Bot

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the main trading bot (continuous loop)
python3 main.py

# Or use the shell script
./run.sh
```

### Running Gemini Analysis Job

```bash
# Run daily Gemini advice analysis
python3 run_daily_advice.py
```

### Running the Dashboard

```bash
# Launch Streamlit dashboard
streamlit run dashboard.py
```

### Testing Components

```bash
# Test KIS API connection and data fetching
python3 test_kis_ohlcv.py

# Test Slack notifications
python3 test_bot.py

# Verify holiday calendar
python3 test_holiday.py
python3 verify_holiday.py

# Verify exclusion list filtering
python3 verify_exclusion.py

# Verify stock danger filtering
python3 verify_stock_filter.py

# Parse trade logs into history
python3 parse_trade_log.py
```

### Backtesting

```bash
# Run backtest simulation
python3 rsi_strategy_backtest.py
```

## Configuration

All configuration is managed through environment variables in `.env`:

- **KIS API**: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO`, `KIS_URL_BASE`
- **Slack**: `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`
- **Gemini**: `GEMINI_API_KEY`
- **Strategy**: `RSI_WINDOW`, `SMA_WINDOW`, `RSI_BUY_THRESHOLD`, `RSI_SELL_THRESHOLD`, `MAX_POSITIONS`, `BUY_AMOUNT_KRW`, `MAX_HOLDING_DAYS`, `LOSS_COOLDOWN_DAYS`
- **Schedule**: `TIME_MORNING_ANALYSIS`, `TIME_PRE_ORDER`, `TIME_ORDER_CHECK`, `TIME_SELL_CHECK`, `TIME_SELL_EXEC`

See `.env.example` for required variables.

## KIS API Integration Details

### Mock vs Production Mode

The system auto-detects mock mode by checking if `KIS_URL_BASE` contains "openapivts":

- **Mock Mode**: Uses virtual trading endpoints (VTTC* TR IDs), extends delays, forces trading days
- **Production Mode**: Uses real trading endpoints (TTTC* TR IDs), normal rate limits

### Important API Quirks

1. **Token Management**: Access tokens expire after 24h. The client auto-refreshes on EGW00123 errors and caches tokens to `token.json`
2. **Rate Limits**: Mock server needs longer delays (0.5-1.5s) to avoid 500 errors. Production uses 0.1-0.2s delays
3. **Price Ticks**: `get_valid_price()` ensures orders use valid tick sizes based on price ranges
4. **Order Types**: "00" = Limit, "01" = Market, "03" = Best Call
5. **Dangerous Stock Check**: Uses `iscd_stat_cls_code`, `mrkt_warn_cls_code`, `mang_issu_cls_code` fields from price queries

### Critical TR IDs

- **FHKST03010100**: Daily OHLCV (supports pagination for long history)
- **TTTC8434R/VTTC8434R**: Balance inquiry
- **TTTC0802U/VTTC0802U**: Buy order
- **TTTC0801U/VTTC0801U**: Sell order
- **TTTC8055R/VTTC8055R**: Outstanding orders
- **TTTC0803U/VTTC0803U**: Order revision/cancellation
- **CTCA0903R**: Holiday calendar check

## State Management

### Global State (in main.py)

The `state` dict tracks daily execution flags:

- `analysis_done`, `pre_order_done`, `buy_verified`, `sell_check_done`, `sell_exec_done`
- `buy_targets`: List of stocks selected for buying with code, RSI, yesterday close, target qty
- `exclude_list`: Set of stock codes loaded from `exclude_list.txt`
- `is_holiday`: Boolean indicating if today is a trading day

State resets daily based on `last_reset_date`.

### Persistent State

1. **trade_history.json**: TradeManager persistence
   - `holdings`: {code: {buy_date}}
   - `last_trade`: {code: {sell_date, pnl_pct}}

2. **stock_analysis.db**: SQLite database storing Gemini advice results

3. **token.json**: Cached KIS OAuth token
4. **trade_log.txt**: Comprehensive execution log with KST timestamps

## Time Zone Handling

All date/time operations use Korea Standard Time (KST/Asia/Seoul):

- `get_now_kst()` helper function in main.py
- Logging formatter uses KST converter
- Holiday checks and date comparisons use KST

## Exclusion List

The `exclude_list.txt` file contains stock codes to skip for both buying and selling:

- One code per line
- Lines starting with `#` are ignored
- Loaded on daily state reset
- Use `load_exclusion_list(kis)` to fetch and log stock names

## Gemini AI Integration

The Gemini client uses `gemini-3-flash-preview` model to:

1. Search for news via DuckDuckGo (last 24h, Korean region)
2. Analyze sentiment and catalysts
3. Return YES/NO buy recommendation with reasoning

**Rate Limiting**: Implements exponential backoff on 429 errors with 3 retries.

## Logging Strategy

- All logs include KST timestamps
- Logs written to both `trade_log.txt` and stdout
- Log levels: INFO for normal operations, WARNING for recoverable issues, ERROR for failures
- Use emoji prefixes for visual scanning: 🚀 (start), ✅ (success), ❌ (failure), ⚠️ (warning), 🔍 (analysis), 📊 (status)

## Common Pitfalls

1. **TPS Errors**: KIS API has strict rate limits. Always include delays between API calls (especially in loops)
2. **Token Expiry**: Don't assume tokens are valid. Use `_send_request()` which auto-refreshes
3. **Mock Server Instability**: Mock server returns 500 errors frequently. Implement retries and fallbacks
4. **Incomplete Data**: Daily OHLCV may not include today's candle. Use yesterday's data for morning analysis
5. **Order Modification Logic**: The cncl_dvsn code is counter-intuitive: "01" = Revise, "02" = Cancel
6. **Date Format Consistency**: KIS uses YYYYMMDD strings, but logs/DB use YYYY-MM-DD. Always normalize

## Adding New Features

When modifying trading logic:

1. Always read current holdings/orders before making decisions
2. Update both in-memory `state` and persistent `trade_history.json`
3. Add appropriate Slack notifications for visibility
4. Test in mock mode first (`KIS_URL_BASE=https://openapivts.koreainvestment.com:29443`)
5. Consider rate limits when adding new API calls
6. Update the daily schedule windows if adding time-based tasks

## Dependencies

Install via: `pip install -r requirements.txt`

Core packages:

- `pandas`, `numpy`: Data analysis
- `requests`: HTTP client
- `python-dotenv`: Environment variable management
- `finance-datareader`: Korean stock data
- `google-generativeai`: Gemini AI SDK
- `duckduckgo-search`: News search
- `streamlit`: Dashboard UI
- `pytz`: Time zone handling
