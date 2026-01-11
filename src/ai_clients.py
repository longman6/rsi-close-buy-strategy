import os
import json
import logging
from typing import Dict
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None


import config

def _get_common_prompt(stock_name: str, code: str, rsi: float, ohlcv_text: str, news_context: str = "") -> str:
    return f"""
    Analyze the KOSDAQ stock "{stock_name}" ({code}) for a potential Short-term Rebound Trade (1-10 days).

    [Technical Data]
    - Current RSI({config.RSI_WINDOW}): {rsi:.2f}
    - Note: RSI and SMA are calculated based on user config (RSI period: {config.RSI_WINDOW}, SMA period: {config.SMA_WINDOW}).
    - Recent Price History (Last 30 Days):
    {ohlcv_text}

    [News Context (Real-time RAG)]
    The following news headlines and snippets were retrieved from the last 24 hours:
    ---
    {news_context if news_context else "No recent news found."}
    ---

    [Task]
    1. **Technical Analysis**: Briefly analyze the price trend and volume from the provided OHLCV data. Is there signs of stopping the fall?
    2. **News/Sentiment**: Analyze the provided 'News Context' above.
       - If "No recent news found", assume NO specific bad news (Neutral/Positive for rebound).
       - If there is bad news (e.g. Delisting risk, Embezzlement, huge earnings miss), it is a STRONG SELL signal (NO).
       - If there is good news or just general neutral news, it supports a rebound.
    3. **Decision**: Provide a definitive 'YES' or 'NO' recommendation for buying right now.
       - YES: If technicals show potential rebound AND no fatal bad news in the provided context.
       - NO: If trend is broken without support OR there is bad news explaining the drop.
    4. **Reasoning**: Summarize the reasoning based on both Technicals and News.
    
    Response Format:
    Return ONLY a JSON object with this structure:
    {{
        "recommendation": "YES" or "NO",
        "reasoning": "A concise paragraph (2-3 sentences) in Korean explaining why based on Tech+News."
    }}
    """


class ClaudeClient:
    def __init__(self, api_key: str, model: str):
        self.client = Anthropic(api_key=api_key) if Anthropic else None
        self.model = model
        self.enabled = bool(self.client) and bool(api_key)

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "") -> Dict:
        if not self.enabled:
            return {"recommendation": "SKIP (Config)", "reasoning": "Claude Disabled/No Key"}
        
        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context)
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = message.content[0].text
            
            # Very basic extraction for YES/NO
            rec = "NO"
            reason = response_text
            import re
            
            # Find JSON block
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    rec = data.get("recommendation", "NO")
                    reason = data.get("reasoning", response_text)
                except:
                    pass
            
            return {"recommendation": rec, "reasoning": reason, "prompt": prompt}

        except Exception as e:
            logging.error(f"Claude Error: {e}")
            return {"recommendation": "ERROR", "reasoning": str(e), "prompt": prompt}

class OpenAIClient:
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key=api_key) if OpenAI else None
        self.model = model
        self.enabled = bool(self.client) and bool(api_key)

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "") -> Dict:
        if not self.enabled:
             return {"recommendation": "SKIP (Config)", "reasoning": "OpenAI Disabled/No Key"}

        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            data["prompt"] = prompt
            return data
        except Exception as e:
            logging.error(f"OpenAI Error: {e}")
            return {"recommendation": "ERROR", "reasoning": str(e), "prompt": prompt}

class GrokClient:
    def __init__(self, api_key: str, model: str):
        base_url = "https://api.x.ai/v1"
        self.client = OpenAI(api_key=api_key, base_url=base_url) if OpenAI else None
        self.model = model 
        self.enabled = bool(self.client) and bool(api_key)

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "") -> Dict:
        if not self.enabled:
             return {"recommendation": "SKIP (Config)", "reasoning": "Grok Disabled/No Key"}

        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Return JSON only."},
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content
            
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                data["prompt"] = prompt
                return data
            else:
                 return {"recommendation": "N/A", "reasoning": content, "prompt": prompt}
        except Exception as e:
            logging.error(f"Grok Error: {e}")
            return {"recommendation": "ERROR", "reasoning": str(e), "prompt": prompt}

class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model_name = model
        self.enabled = bool(self.api_key) and bool(genai)
        self.client = None
        
        if self.enabled:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logging.error(f"[Gemini] Init Error: {e}")
                self.enabled = False

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "") -> Dict:
        if not self.enabled:
             return {"recommendation": "SKIP (Config)", "reasoning": "Gemini Disabled/No Key"}

        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context)
        
        # Retry Config
        max_retries = 3
        retry_delay = 10 

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                result = json.loads(response.text)
                result["prompt"] = prompt
                return result
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "Quota exceeded" in error_str:
                    logging.warning(f"[Gemini] Rate Limit hit. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logging.error(f"[Gemini] API Error: {e}")
                    return {
                        "recommendation": "NO", 
                        "reasoning": f"Gemini Analysis Failed: {str(e)}",
                        "prompt": prompt
                    }
        
        return {"recommendation": "NO", "reasoning": "Gemini Rate Limit Exceeded after retries.", "prompt": prompt}
