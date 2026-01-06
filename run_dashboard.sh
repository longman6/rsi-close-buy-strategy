#!/bin/bash

# Move to the project directory
cd "$(dirname "$0")"

# Activate Virtual Environment
source .venv/bin/activate

# Use a specific port if needed, default is 8501
# You can pass arguments to this script to be passed to streamlit
# e.g., ./run_dashboard.sh --server.port 8502
echo "🚀 Starting RSI Power Zone Dashboard in BACKGROUND..."
nohup streamlit run dashboard.py "$@" > logs/dashboard.log 2>&1 &
echo "✅ Dashboard is running in the background. Logs: logs/dashboard.log"
echo "👉 PID: $!"
