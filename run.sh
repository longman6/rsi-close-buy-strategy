#!/bin/bash

# Move to the project directory
# (Adjust this path if you move the folder)
cd "$(dirname "$0")"

# Activate Virtual Environment
source .venv/bin/activate

# Run the Bot
# Logs are inherently handled by main.py (trade_log.txt)
# But we also capture stderr just in case
#python3 main.py >> trade_log_cron.txt 2>&1

python3 main.py


