#!/bin/bash

# Move to the project directory
cd "$(dirname "$0")"

# Activate Virtual Environment
source .venv/bin/activate

# Execute the analysis script
# Appending output to a specific log file for cron debugging
echo "Starting Analysis at $(date)" >> cron_analyze.log
python3 analyze_kosdaq150.py >> cron_analyze.log 2>&1
echo "Finished Analysis at $(date)" >> cron_analyze.log
