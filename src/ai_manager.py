import json
import os
import logging
from typing import List, Dict

# Import Clients
# Import Clients
from src.ai_clients import GeminiClient, ClaudeClient, OpenAIClient, GrokClient
from src.news_search import NewsSearch
from dotenv import load_dotenv

load_dotenv()

CONFIG_FILE = "llm_config.json"

class AIManager:
    def __init__(self):
        self.clients = []
        self.config = self._load_config()
        self._initialize_clients()
        self.news_search = NewsSearch()

    def _load_config(self) -> Dict:
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Config Load Error: {e}")
            return {}

    def _initialize_clients(self):
        # 1. Gemini
        gemini_cfg = self.config.get("gemini", {})
        if gemini_cfg.get("enabled"):
            key = os.getenv(gemini_cfg.get("env_key", "GOOGLE_API_KEY"))
            if key:
                try:
                    self.clients.append({
                        "name": "Gemini",
                        "client": GeminiClient(api_key=key, model=gemini_cfg.get("model")),
                        "model": gemini_cfg.get("model")
                    })
                except Exception as e:
                    logging.error(f"Gemini Init Failed: {e}")

        # 2. Claude
        claude_cfg = self.config.get("claude", {})
        if claude_cfg.get("enabled"):
            key = os.getenv(claude_cfg.get("env_key", "CLAUDE_API_KEY"))
            if key:
                self.clients.append({
                    "name": "Claude",
                    "client": ClaudeClient(api_key=key, model=claude_cfg.get("model")),
                    "model": claude_cfg.get("model")
                })

        # 3. OpenAI
        openai_cfg = self.config.get("openai", {})
        if openai_cfg.get("enabled"):
            key = os.getenv(openai_cfg.get("env_key", "OPENAI_API_KEY"))
            if key:
                self.clients.append({
                    "name": "ChatGPT",
                    "client": OpenAIClient(api_key=key, model=openai_cfg.get("model")),
                    "model": openai_cfg.get("model")
                })
        
        # 4. Grok
        grok_cfg = self.config.get("grok", {})
        if grok_cfg.get("enabled"):
            key = os.getenv(grok_cfg.get("env_key", "GROK_API_KEY"))
            if key:
                self.clients.append({
                    "name": "Grok",
                    "client": GrokClient(api_key=key, model=grok_cfg.get("model")),
                    "model": grok_cfg.get("model")
                })

        logging.info(f"AI Manager Initialized with {len(self.clients)} clients: {[c['name'] for c in self.clients]}")

    def get_aggregated_advice(self, name: str, code: str, rsi: float, ohlcv_text: str = "") -> List[Dict]:
        """
        Polls all enabled AI clients for advice.
        Returns a list of results: 
        [
            {'model': 'Gemini', 'recommendation': 'YES', 'reasoning': '...'},
            ...
        ]
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 1. Fetch News (RAG)
        logging.info(f"🔎 Fetching news for {name} ({code})...")
        news_text = self.news_search.get_news(name)

        def call_client(client_config):
            c_name = client_config['name']
            c_obj = client_config['client']
            try:
                logging.info(f"🤖 Asking {c_name} about {name}...")
                advice = c_obj.get_advice(name, code, rsi, ohlcv_text, news_context=news_text)
                
                rec = advice.get("recommendation", "ERROR")
                reason = advice.get("reasoning", "No valid response")
                
                return {
                    "model": c_name,
                    "specific_model": client_config.get('model'),
                    "recommendation": rec,
                    "reasoning": reason,
                    "prompt": advice.get("prompt")
                }
            except Exception as e:
                logging.error(f"Error from {c_name}: {e}")
                return {
                    "model": c_name,
                    "recommendation": "ERROR",
                    "reasoning": str(e)
                }

        results = []
        with ThreadPoolExecutor(max_workers=len(self.clients)) as executor:
            future_to_client = {executor.submit(call_client, c): c for c in self.clients}
            for future in as_completed(future_to_client):
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Log immediately for user content
                    m_name = result.get('model')
                    m_rec = result.get('recommendation')
                    logging.info(f"   > {m_name} finished: {m_rec}")

                except Exception as e:
                    logging.error(f"Thread Error: {e}")
        
        return results
