#!/bin/bash

# Define Paths
PROJECT_ROOT="/home/longman6/codelab/RSI_POWER_ZONE"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
REPORT_DIR="$PROJECT_ROOT/reports"
FINAL_REPORT="$REPORT_DIR/final_comprehensive_report_$(date +%Y%m%d_%H%M%S).md"

echo "🚀 Resuming RSI Optimization (Start from RSI 5)..."
echo "---------------------------------------------"

# 2. Optimize RSI 5
echo "👉 Running RSI 5 Optimization..."
"$VENV_PYTHON" "$PROJECT_ROOT/scripts/optimize_rsi5.py"
if [ $? -eq 0 ]; then
    echo "✅ RSI 5 Optimization Completed."
else
    echo "❌ RSI 5 Optimization Failed."
    exit 1
fi

# 3. Optimize RSI 7
echo "👉 Running RSI 7 Optimization..."
"$VENV_PYTHON" "$PROJECT_ROOT/scripts/optimize_rsi7.py"
if [ $? -eq 0 ]; then
    echo "✅ RSI 7 Optimization Completed."
else
    echo "❌ RSI 7 Optimization Failed."
    exit 1
fi

echo "---------------------------------------------"
echo "📊 Generating Comprehensive Report..."

echo "# RSI Strategy Optimization Comprehensive Report" > "$FINAL_REPORT"
echo "Generated: $(date)" >> "$FINAL_REPORT"
echo "" >> "$FINAL_REPORT"

echo "## 1. RSI 3 Results Summary" >> "$FINAL_REPORT"
if [ -f "$REPORT_DIR/rsi3_parallel_report.md" ]; then
    cat "$REPORT_DIR/rsi3_parallel_report.md" >> "$FINAL_REPORT"
else
    echo "No report found for RSI 3." >> "$FINAL_REPORT"
fi
echo "" >> "$FINAL_REPORT"

echo "## 2. RSI 5 Results Summary" >> "$FINAL_REPORT"
if [ -f "$REPORT_DIR/rsi5_parallel_report.md" ]; then
    cat "$REPORT_DIR/rsi5_parallel_report.md" >> "$FINAL_REPORT"
else
    echo "No report found for RSI 5." >> "$FINAL_REPORT"
fi
echo "" >> "$FINAL_REPORT"

echo "## 3. RSI 7 Results Summary" >> "$FINAL_REPORT"
if [ -f "$REPORT_DIR/rsi7_parallel_report.md" ]; then
    cat "$REPORT_DIR/rsi7_parallel_report.md" >> "$FINAL_REPORT"
else
    echo "No report found for RSI 7." >> "$FINAL_REPORT"
fi

echo "✅ All Done! Final Report saved to: $FINAL_REPORT"
