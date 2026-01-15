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

def _get_common_prompt(stock_name: str, code: str, rsi: float, ohlcv_text: str, news_context: str = "", extended_indicators: Dict = None) -> str:
    # 확장 지표 텍스트 생성
    if extended_indicators:
        ext_ind = extended_indicators
        indicators_text = f"""
    [Extended Indicators]
    - Current Price: {ext_ind.get('current_price', 0):,.0f} KRW
    - RSI(3): {ext_ind.get('rsi_3', 0):.1f}
    - RSI(14): {ext_ind.get('rsi_14', 0):.1f}
    - 5-Day Avg Volume: {ext_ind.get('avg_vol_5d', 0):,.0f}
    - 20-Day Avg Volume: {ext_ind.get('avg_vol_20d', 0):,.0f}
    - Volume Ratio (Today/20D): {ext_ind.get('volume_ratio', 0):.1f}%
    - Distance from 20MA: {ext_ind.get('dist_20ma', 0):+.1f}%
    - Distance from 60MA: {ext_ind.get('dist_60ma', 0):+.1f}%
"""
    else:
        indicators_text = ""
    
    return f"""
    You are a quantitative trading analyst specializing in RSI({config.RSI_WINDOW}) mean reversion strategy with news sentiment filter.

    ## STRATEGY RULES
    - **Primary Signal**: RSI({config.RSI_WINDOW}) ≤ {config.RSI_BUY_THRESHOLD} (oversold condition triggers buy consideration)
    - **Trend Filter**: Price must be above SMA({config.SMA_WINDOW}) to confirm uptrend
    - **Holding Period**: Maximum {config.MAX_HOLDING_DAYS} trading days
    - **Exit Conditions**: RSI({config.RSI_WINDOW}) > {config.RSI_SELL_THRESHOLD} OR +10% profit

    ## TASK
    Determine whether to BUY the KOSDAQ stock "{stock_name}" ({code}) based on the strategy above.

    [Technical Data]
    - Current RSI({config.RSI_WINDOW}): {rsi:.2f}
    - Note: RSI and SMA are calculated based on user config (RSI period: {config.RSI_WINDOW}, SMA period: {config.SMA_WINDOW}).
    - Recent Price History (Last 30 Days):
    {ohlcv_text}
    {indicators_text}
    [News Context (Real-time RAG)]
    The following news headlines and snippets were retrieved from the last 24 hours:
    ---
    {news_context if news_context else "No recent news found."}
    ---

    [Analysis Instructions]
    1. **Technical Analysis**: Briefly analyze the price trend and volume from the provided OHLCV data. Is there signs of stopping the fall? Does RSI indicate oversold?
       - Consider short-term RSI(3) for immediate momentum and RSI(14) for medium-term trend.
       - Evaluate volume ratio to assess buying interest.
       - Check distance from moving averages to gauge mean reversion potential.
    2. **News/Sentiment Filter**: Analyze the provided 'News Context' above.
       - If "No recent news found", assume NO specific bad news (Neutral/Positive for rebound).
       - If there is bad news (e.g. Delisting risk, Embezzlement, huge earnings miss), it is a STRONG SELL signal (NO).
       - If there is good news or just general neutral news, it supports a rebound.
    3. **Decision**: Based on the strategy rules above, provide a definitive 'YES' or 'NO' recommendation.
       - YES: If RSI is oversold, price is above SMA, AND no fatal bad news in the provided context.
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

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "", extended_indicators: Dict = None) -> Dict:
        if not self.enabled:
            return {"recommendation": "SKIP (Config)", "reasoning": "Claude Disabled/No Key"}
        
        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context, extended_indicators)
        
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

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "", extended_indicators: Dict = None) -> Dict:
        if not self.enabled:
             return {"recommendation": "SKIP (Config)", "reasoning": "OpenAI Disabled/No Key"}

        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context, extended_indicators)
        
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

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "", extended_indicators: Dict = None) -> Dict:
        if not self.enabled:
             return {"recommendation": "SKIP (Config)", "reasoning": "Grok Disabled/No Key"}

        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context, extended_indicators)
        
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

    def get_advice(self, stock_name: str, code: str, rsi: float, ohlcv_text: str = "", news_context: str = "", extended_indicators: Dict = None) -> Dict:
        if not self.enabled:
             return {"recommendation": "SKIP (Config)", "reasoning": "Gemini Disabled/No Key"}

        prompt = _get_common_prompt(stock_name, code, rsi, ohlcv_text, news_context, extended_indicators)
        
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
