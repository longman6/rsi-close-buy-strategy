import os
import json
import logging
import google.generativeai as genai
from duckduckgo_search import DDGS
from dotenv import load_dotenv

load_dotenv()

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logging.warning("[Gemini] API Key not found in .env!")
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-3-flash-preview') # High reasoning for paid tier

    def fetch_recent_news(self, stock_name, stock_code):
        """
        Search for recent news (Last 24h) using DuckDuckGo.
        Returns a summary string of news titles and snippets.
        """
        query = f"{stock_name} {stock_code} 주가 특징주 악재 호재"
        logging.info(f"[News] Searching for: {query}")
        
        results = []
        try:
            # simple text search
            with DDGS() as ddgs:
                # time='d' means last day (24h)
                # region='kr-kr' for Korean results
                ddgs_gen = ddgs.text(query, region='kr-kr', timelimit='d', max_results=5)
                for r in ddgs_gen:
                    results.append(f"- [{r['title']}] {r['body']}")
        except Exception as e:
            logging.error(f"[News] Search failed: {e}")
            return "No specific news found in the last 24 hours."
            
        if not results:
            return "No specific news found in the last 24 hours via web search."
            
        return "\n".join(results)

    def get_buy_advice(self, stock_name, stock_code, rsi_value):
        """
        Queries Gemini for buy advice.
        """
        if not self.api_key:
            return {"recommendation": "NO", "reasoning": "Gemini API Key missing."}

        # # 1. Gather Context
        # news_summary = self.fetch_recent_news(stock_name, stock_code)
        
        # 2. Construct Prompt
        prompt = f"""
Search for the latest news, analyst reports, and social media (SNS) sentiment for the KOSDAQ stock "{stock_name}" ({stock_code}).


      CRITICAL REQUIREMENT: Only consider information published within the LAST 24 HOURS.
      
      User's Goal: Short-term rebound strategy (1-10 days investment horizon) after a recent decline.
      
      Task:
      1. Analyze if there are any ultra-recent positive catalysts or bottoming signals from the last 24 hours.
      2. Check if there are any breaking news or viral SNS mentions that could impact the price today or tomorrow.
      3. Provide a definitive 'YES' or 'NO' recommendation for buying right now.
      4. Summarize the reasoning based on this very recent data.
      
      Response Format:
      Return ONLY a JSON object with this structure:
      {{
        "recommendation": "YES" or "NO",
        "reasoning": "A concise paragraph (2-3 sentences) in Korean explaining why based on news from the last 24 hours."
      }}
"""
        # Retry Config
        max_retries = 3
        retry_delay = 10 # Seconds

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                result = json.loads(response.text)
                return result
            except Exception as e:
                # Check for Rate Limit (429) in error message
                error_str = str(e)
                if "429" in error_str or "Quota exceeded" in error_str:
                    logging.warning(f"[Gemini] Rate Limit hit. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff
                else:
                    logging.error(f"[Gemini] API Error: {e}")
                    return {
                        "recommendation": "NO", 
                        "reasoning": f"Gemini Analysis Failed: {str(e)}"
                    }
        
        return {"recommendation": "NO", "reasoning": "Gemini Rate Limit Exceeded after retries."}
