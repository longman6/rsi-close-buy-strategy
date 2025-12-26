import logging
from duckduckgo_search import DDGS
from typing import List, Dict

class NewsSearch:
    def __init__(self):
        self.ddgs = DDGS()

    def get_news(self, keyword: str, limit: int = 5) -> str:
        """
        Fetches news for a keyword and returns a formatted string of results.
        Returns empty string if no news found or error occurs.
        """
        try:
            # kr-kr region for Korean news, 'd' for day (last 24h) is strictly enforced in prompt but good here too?
            # actually DDGS 't' parameter controls time. 'd' = day.
            results = self.ddgs.news(keywords=keyword, region="kr-kr", timelimit="d", max_results=limit)
            
            if not results:
                return "No recent news found."

            news_text = ""
            for i, r in enumerate(results):
                title = r.get('title', 'No Title')
                body = r.get('body', '')
                source = r.get('source', 'Unknown')
                date = r.get('date', '')
                
                news_text += f"{i+1}. [{source}] {title} ({date})\n   {body}\n\n"
            
            return news_text.strip()

        except Exception as e:
            logging.error(f"[NewsSearch] Error fetching news for {keyword}: {e}")
            return "Error fetching news."

if __name__ == "__main__":
    # Test
    ns = NewsSearch()
    print(ns.get_news("삼성전자"))
