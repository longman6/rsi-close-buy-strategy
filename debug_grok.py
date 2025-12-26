from src.ai_clients import GrokClient
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROK_API_KEY")
model = "grok-4-1-fast-reasoning"

if not api_key:
    print("No GROK_API_KEY found in .env")
    exit()

client = GrokClient(api_key, model)

# Dummy Data: RSI 25 (Low), Price dropping
stock_name = "TestStock"
code = "000000"
rsi = 25.0
ohlcv_text = """
Date       Open    High    Low     Close   Volume  RSI
2024-01-01 10000   10100   9900    9900    100000  40.0
2024-01-02 9900    9950    9800    9800    120000  38.0
2024-01-03 9800    9850    9600    9600    150000  30.0
2024-01-04 9600    9650    9400    9450    200000  28.0
2024-01-05 9450    9500    9200    9250    250000  25.0
"""

# FAKE BAD NEWS to test RAG override
fake_news = """
1. [Breaking News] Start-up 'TestStock' CEO arrested for embezzlement of 50 billion KRW (2025-12-26)
   The prosecution has issued an arrest warrant for the CEO...
   
2. [Market Watch] TestStock plunges 20% on delisting fears (2025-12-26)
   Due to the accounting scandal, the exchange is reviewing...
"""

print(f"Sending request to {model} with FAKE NEGATIVE NEWS...")
print(f"News Context:\n{fake_news}\n")

advice = client.get_advice(stock_name, code, rsi, ohlcv_text, news_context=fake_news)

print("\n--- Response ---")
print(f"Recommendation: {advice.get('recommendation')}")
print(f"Reasoning: {advice.get('reasoning')}")
