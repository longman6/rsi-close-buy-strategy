#!/bin/bash

# Configuration
REMOTE_HOST="ec2-13-209-72-41.ap-northeast-2.compute.amazonaws.com"
REMOTE_USER="ubuntu"
REMOTE_DIR="/home/ubuntu/projects/RSI_POWER_ZONE/data"
REMOTE_FILE="stock_analysis.db"
PEM_FILE="$HOME/.ssh/longman.pem"
LOCAL_DIR="data"
LOCAL_FILE="$LOCAL_DIR/stock_analysis.db"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "🚀 Connecting to AWS EC2 ($REMOTE_HOST)..."

# Check if PEM file exists
if [ ! -f "$PEM_FILE" ]; then
    echo -e "${RED}❌ Error: PEM file not found at $PEM_FILE${NC}"
    exit 1
fi

# Ensure local directory exists
mkdir -p "$LOCAL_DIR"

# Execute SCP
CMD="scp -i "$PEM_FILE" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/$REMOTE_FILE" "$LOCAL_FILE""
echo "📝 Executing: $CMD"

$CMD

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Database downloaded successfully to $LOCAL_FILE${NC}"
    ls -lh "$LOCAL_FILE"
else
    echo -e "${RED}❌ Failed to download database.${NC}"
    exit 1
fi
