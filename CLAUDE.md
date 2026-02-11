# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RSI_POWER_ZONE is an automated Korean stock trading bot that implements an RSI-based mean-reversion strategy on KOSDAQ 150 stocks using the Korea Investment & Securities (KIS) API. The system uses a **multi-LLM consensus approach** (Gemini, Claude, GPT, Grok) combined with real-time news search (RAG) to make buy decisions, executes trades automatically, and provides real-time Telegram notifications including hourly portfolio status reports.

## Core Architecture

### Main Components

1. **main.py**: Orchestrates the daily trading loop with scheduled tasks (morning analysis, pre-market orders, order monitoring, sell execution, hourly portfolio reports)
2. **analyze_kosdaq150.py**: Standalone cron job (runs at 08:00 KST) that calculates RSI for all KOSDAQ 150 stocks, filters candidates (RSI < 35), fetches news via Google News, and queries multiple AI models in parallel for consensus recommendations
3. **src/kis_client.py**: KIS API wrapper handling OAuth, price data, balance queries, order execution, and stock safety checks
4. **src/strategy.py**: Implements RSI(3) + SMA(100) strategy logic for buy/sell signals
5. **src/trade_manager.py**: Manages trade history, holding periods, forced sells, and loss cooldown tracking
6. **src/ai_manager.py**: Coordinates multiple AI clients (Gemini, Claude, GPT, Grok) to get consensus recommendations via parallel API calls using ThreadPoolExecutor
7. **src/ai_clients.py**: Individual client implementations (GeminiClient, ClaudeClient, OpenAIClient, GrokClient) with unified interface
8. **src/news_search.py**: Google News search integration for retrieving recent news about stocks (RAG)
9. **src/db_manager.py**: SQLite persistence for daily RSI data, AI advice from each model, trade history, trading journal, and user authentication
10. **src/telegram_bot.py**: Telegram notifications for trading events
11. **dashboard.py**: Streamlit dashboard with password authentication to view AI consensus results, trade history, and performance metrics

### Daily Trading Flow

The bot operates on a strict schedule (times configured in config.py):

1. **08:00**: Cron job runs `analyze_kosdaq150.py` - calculates RSI for KOSDAQ 150, filters low-RSI candidates, fetches news for each, queries all enabled LLMs in parallel, saves results to database
2. **08:30**: Morning analysis - main bot loads AI consensus results from database, filters stocks with majority "YES" votes, checks exclusion list and cooldown periods
3. **08:57**: Pre-market orders - places limit orders at expected price + 1.5% (adjusted for valid tick sizes)
4. **09:05-15:20**: Continuous order monitoring - modifies unfilled orders to current price (cancels if price rises >5%)
5. **XX:10**: Hourly report (every hour at :10 minutes) - sends portfolio status, holdings, and P/L to Telegram
6. **15:20**: Sell signal check - identifies positions with RSI > 70 or max holding period exceeded
7. **15:26**: Sell execution - executes market orders for flagged positions

### Key Trading Rules

- **Buy Conditions**: RSI(3) < 35 AND Close > SMA(100) AND not in exclusion list AND not in loss cooldown AND AI consensus recommends buy
- **Sell Conditions**: RSI(3) > 70 OR holding period > 38 days
- **Position Limits**: Maximum 5 concurrent positions
- **Position Sizing**: Fixed KRW amount per stock (default: 1,000,000 KRW), auto-adjusted if insufficient cash
- **Loss Cooldown**: 40-day cooldown after selling at a loss
- **Stock Filtering**: Automatically excludes suspended/admin-issue/warning stocks via KIS API status codes
- **AI Consensus**: Requires majority "YES" votes from enabled LLMs (configured in `llm_config.json`)

## Development Commands

### Running the Bot

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the main trading bot (continuous loop)
python main.py

# Or use the shell script
./run.sh
```

### Running AI Analysis Job

```bash
# Run daily AI consensus analysis (normally runs via cron at 08:00)
python analyze_kosdaq150.py

# Or use the shell script (logs to logs/cron_analyze.log)
./run_analysis.sh
```

### Running the Dashboard

```bash
# Launch Streamlit dashboard (default port 8501)
streamlit run dashboard.py

# Or use the shell script
./run_dashboard.sh
```

### Testing

```bash
# Unit tests
python tests/unit/test_kis_ohlcv.py      # KIS API connection and OHLCV data
python tests/unit/test_bot.py            # Telegram notifications
python tests/unit/test_holiday.py        # Holiday calendar
python tests/unit/test_universe.py       # KOSDAQ 150 universe fetching

# Integration tests
python tests/integration/verify_exclusion.py       # Exclusion list filtering
python tests/integration/verify_stock_filter.py    # Stock danger filtering
python tests/integration/verify_holiday.py         # Holiday detection
python tests/integration/verify_db_update.py       # Database operations
python tests/integration/verify_strategy_ops.py    # Strategy signals
python tests/integration/verify_trade_logging.py   # Trade log parsing

# Debug scripts
python tests/debug/debug_kis.py       # KIS API debugging
python tests/debug/debug_balance.py   # Balance inquiry
python tests/debug/debug_gemini.py    # Gemini client
python tests/debug/debug_grok.py      # Grok client
```

### Backtesting

```bash
# Run backtest simulation
python rsi_strategy_backtest.py
```

### Utility Scripts

```bash
# Parse trade logs into database
python scripts/parse_trade_log.py

# Fetch KOSPI 200 data
python scripts/fetch_kospi200.py

# Export KOSDAQ 150 list
python scripts/export_kosdaq150.py
```

## Configuration

### Environment Variables (.env)

**KIS API:**
- `KIS_APP_KEY`: API key from KIS portal
- `KIS_APP_SECRET`: API secret
- `KIS_CANO`: Account number (8 digits)
- `KIS_ACNT_PRDT_CD`: Account product code (usually "01")
- `KIS_URL_BASE`: API endpoint (production: `https://openapi.koreainvestment.com:9443`, mock: `https://openapivts.koreainvestment.com:29443`)

**Telegram:**
- `TELEGRAM_BOT_TOKEN`: Bot token from @BotFather
- `TELEGRAM_CHAT_ID`: Your chat ID
- `ENABLE_NOTIFICATIONS`: "true" or "false"

**AI API Keys:**
- `GEMINI_API_KEY`: Google AI API key (or `GOOGLE_API_KEY`)
- `CLAUDE_API_KEY`: Anthropic API key
- `OPENAI_API_KEY`: OpenAI API key
- `GROK_API_KEY`: xAI API key (or `XAI_API_KEY`)

**Strategy:**
- `RSI_WINDOW`: RSI period (default: 3)
- `SMA_WINDOW`: SMA period (default: 100)
- `MAX_POSITIONS`: Max concurrent positions (default: 5)
- `RSI_BUY_THRESHOLD`: RSI buy threshold (default: 35)
- `RSI_SELL_THRESHOLD`: RSI sell threshold (default: 70)
- `BUY_AMOUNT_KRW`: Fixed buy amount per stock (default: 1000000)
- `MAX_HOLDING_DAYS`: Max holding period before forced sell (default: 38)
- `LOSS_COOLDOWN_DAYS`: Cooldown after loss (default: 40)

**Schedule (HH:MM format):**
- `TIME_MORNING_ANALYSIS`: Morning analysis time (default: "08:30")
- `TIME_PRE_ORDER`: Pre-market order time (default: "08:57")
- `TIME_ORDER_CHECK`: Order monitoring start (default: "09:05")
- `TIME_SELL_CHECK`: Sell signal check (default: "15:20")
- `TIME_SELL_EXEC`: Sell execution (default: "15:26")

### LLM Configuration (llm_config.json)

Controls which AI models are enabled and which specific model versions to use:

```json
{
    "gemini": {
        "enabled": true,
        "model": "gemini-3-pro-preview",
        "env_key": "GEMINI_API_KEY"
    },
    "claude": {
        "enabled": true,
        "model": "claude-opus-4-5-20251101",
        "env_key": "CLAUDE_API_KEY"
    },
    "openai": {
        "enabled": true,
        "model": "gpt-5.2",
        "env_key": "OPENAI_API_KEY"
    },
    "grok": {
        "enabled": true,
        "model": "grok-4-1-fast-reasoning",
        "env_key": "GROK_API_KEY"
    }
}
```

## Database Schema (stock_analysis.db)

The SQLite database has 5 main tables:

1. **daily_rsi**: Daily RSI and price data
   - `date`, `code`, `name`, `rsi`, `close_price`

2. **ai_advice**: Individual AI model recommendations
   - `date`, `code`, `model`, `recommendation` ('YES'/'NO'), `reasoning`, `specific_model`, `prompt`

3. **trade_history**: Executed trades
   - `date`, `code`, `name`, `action` ('BUY'/'SELL'), `price`, `quantity`, `amount`, `pnl_amt`, `pnl_pct`

4. **trading_journal**: Daily portfolio snapshots
   - `date`, `total_balance`, `daily_profit_loss`, `daily_return_pct`, `holdings_snapshot`, `notes`

5. **users**: Dashboard authentication
   - `username`, `password_hash`

## KIS API Integration Details

### Mock vs Production Mode

The system auto-detects mock mode by checking if `KIS_URL_BASE` contains "openapivts":

- **Mock Mode**: Uses virtual trading endpoints (VTTC* TR IDs), extends delays (0.5-1.5s), forces all days as trading days
- **Production Mode**: Uses real trading endpoints (TTTC* TR IDs), normal delays (0.1-0.2s)

### Important API Quirks

1. **Token Management**: Access tokens expire after 24h. The client auto-refreshes on EGW00123 errors and caches tokens to `token.json`
2. **Rate Limits**: KIS API has strict TPS limits. Always include delays between API calls (especially in loops)
3. **Price Ticks**: `get_valid_price()` ensures orders use valid tick sizes based on price ranges (e.g., ₩1 for prices under ₩1000, ₩5 for ₩1000-₩5000, etc.)
4. **Order Types**: "00" = Limit, "01" = Market, "03" = Best Call
5. **Order Modification**: `cncl_dvsn` codes are counter-intuitive - "01" = Revise, "02" = Cancel
6. **Dangerous Stock Check**: Uses `iscd_stat_cls_code`, `mrkt_warn_cls_code`, `mang_issu_cls_code` fields from price queries to filter risky stocks

### Critical TR IDs

- **FHKST03010100**: Daily OHLCV (supports pagination via `FID_PERIOD_DIV_CODE`)
- **TTTC8434R/VTTC8434R**: Balance inquiry
- **TTTC0802U/VTTC0802U**: Buy order
- **TTTC0801U/VTTC0801U**: Sell order
- **TTTC8055R/VTTC8055R**: Outstanding orders
- **TTTC0803U/VTTC0803U**: Order revision/cancellation
- **CTCA0903R**: Holiday calendar check

## State Management

### Global State (main.py)

The `state` dict tracks daily execution flags and resets every day:

- `analysis_done`: Morning analysis completed
- `pre_order_done`: Pre-market orders placed
- `buy_verified`: Buy orders verified
- `sell_check_done`: Sell signals checked
- `sell_exec_done`: Sell orders executed
- `buy_targets`: List of stocks to buy with RSI, price, qty
- `exclude_list`: Set of stock codes from `data/exclude_list.txt`
- `is_holiday`: Boolean indicating trading day
- `last_sent_hour`: Track hourly report (sent at :10 of each hour)

### Persistent State

1. **data/trade_history.json**: TradeManager persistence
   - `holdings`: {code: {buy_date}}
   - `last_trade`: {code: {sell_date, pnl_pct}}

2. **data/stock_analysis.db**: SQLite database (see Database Schema above)

3. **token.json**: Cached KIS OAuth token (auto-refreshes)

4. **logs/trade_log.txt**: Main execution log with KST timestamps

5. **logs/daily_analysis.log**: AI analysis job log

## Multi-LLM Consensus System

The AI Manager (`src/ai_manager.py`) implements a sophisticated consensus mechanism:

1. **News Search (RAG)**: For each stock, fetches recent Google News articles in Korean
2. **Parallel Queries**: Uses ThreadPoolExecutor to query all enabled LLMs simultaneously
3. **Unified Interface**: Each client (Gemini, Claude, GPT, Grok) implements `get_advice()` method
4. **Consensus Logic**: Majority voting - if >50% of LLMs recommend "YES", the stock is considered a buy candidate
5. **Database Persistence**: Each model's recommendation and reasoning is saved individually to `ai_advice` table
6. **Error Handling**: If an LLM fails, it returns "ERROR" recommendation and continues with other models

## Time Zone Handling

All date/time operations use Korea Standard Time (KST/Asia/Seoul):

- `get_now_kst()` helper function in `src/utils.py`
- Logging formatter uses KST converter
- Holiday checks and date comparisons use KST
- Database timestamps use CURRENT_TIMESTAMP (system time, but logs are KST)

## Exclusion List

The `data/exclude_list.txt` file contains stock codes to skip:

- One code per line
- Lines starting with `#` are ignored (comments)
- Loaded on daily state reset
- `load_exclusion_list(kis)` optionally fetches and logs stock names via KIS API

## Logging Strategy

- All logs include KST timestamps
- Main bot logs to `logs/trade_log.txt` and stdout
- Analysis job logs to `logs/daily_analysis.log` and stdout
- Log levels: INFO for normal operations, WARNING for recoverable issues, ERROR for failures
- Emoji prefixes for visual scanning: 🚀 (start), ✅ (success), ❌ (failure), ⚠️ (warning), 🔍 (analysis), 📊 (status), 🤖 (AI)

## Common Pitfalls

1. **TPS Errors**: KIS API has strict rate limits. Always include `time.sleep()` between API calls, especially in loops over multiple stocks
2. **Token Expiry**: Don't assume tokens are valid. Use `_send_request()` which auto-refreshes on EGW00123 errors
3. **Mock Server Instability**: Mock server returns 500 errors frequently. Implement retries and fallbacks
4. **Incomplete Data**: Daily OHLCV may not include today's incomplete candle. Use yesterday's data for morning analysis
5. **Date Format Consistency**: KIS API uses YYYYMMDD strings, but logs/DB use YYYY-MM-DD. Always normalize
6. **AI API Rate Limits**: Each LLM has different rate limits. Gemini implements exponential backoff (3 retries)
7. **News Search Quality**: Google News may return irrelevant results. LLMs should filter and summarize

## Adding New Features

When modifying trading logic:

1. Always read current holdings/orders from KIS API before making decisions
2. Update both in-memory `state` dict and persistent files (`trade_history.json`, database)
3. Add appropriate Telegram notifications for visibility
4. Test in mock mode first (`KIS_URL_BASE=https://openapivts.koreainvestment.com:29443`)
5. Consider rate limits when adding new API calls (KIS, AI providers)
6. Update the daily schedule windows if adding time-based tasks
7. Update database schema if adding new data fields (see `_initialize_db()` migration pattern)

When adding new AI providers:

1. Implement a new client class in `src/ai_clients.py` with `get_advice()` method
2. Add configuration to `llm_config.json`
3. Register the client in `src/ai_manager.py`'s `_initialize_clients()`
4. Test with a single stock before enabling for full universe

## Dependencies

Install via: `pip install -r requirements.txt`

Core packages:

- `pandas`, `numpy`: Data analysis and RSI calculation
- `requests`: HTTP client for KIS API
- `python-dotenv`: Environment variable management
- `finance-datareader`: Korean stock data (fallback)
- `pykrx`: KOSDAQ 150 index composition
- `streamlit`: Dashboard UI
- `pytz`: Time zone handling (KST)
- `anthropic`: Claude API client
- `openai`: OpenAI/GPT API client
- `google-generativeai`: Gemini API client
- `duckduckgo-search`: News search (alternative to Google News)
- `bcrypt`: Password hashing for dashboard
