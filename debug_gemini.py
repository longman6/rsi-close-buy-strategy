from src.ai_clients import GeminiClient
import os
from dotenv import load_dotenv
import logging

# Configure logging to show info
logging.basicConfig(level=logging.INFO)

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
# Using the model found in list
model = "gemini-3-flash-preview" 

if not api_key:
    print("No GEMINI_API_KEY found in .env")
    exit()

client = GeminiClient(api_key, model)

# List available models
try:
    print("Listing available models...")
    for m in client.client.models.list(config={"page_size": 10}):
        print(f" - {m.name}")
except Exception as e:
    print(f"Error listing models: {e}")

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

# FAKE BAD NEWS to test RAG override - Strong Negative
fake_news = "" # Testing "No News" scenario


print(f"Sending request to {model} with NO NEWS (Expecting YES??)...")
print(f"News Context:\n{fake_news}\n")

advice = client.get_advice(stock_name, code, rsi, ohlcv_text, news_context=fake_news)

print("\n--- Response ---")
print(f"Recommendation: {advice.get('recommendation')}")
print(f"Reasoning: {advice.get('reasoning')}")
print(f"Prompt Used: {advice.get('prompt')[:100]}...") # Check prompt start
