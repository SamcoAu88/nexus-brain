"""
Web Search Tool Integration
Uses Perplexity API for current information retrieval
"""

import logging
from typing import Optional, Dict, List
import requests
from datetime import datetime

from src.core.config import settings

logger = logging.getLogger(__name__)


class PerplexitySearchTool:
    """Web search using Perplexity AI Sonar model"""

    def __init__(self):
        """Initialize Perplexity search tool"""
        self.api_key = settings.PERPLEXITY_API_KEY
        self.model = "sonar"  # Fast, accurate web search
        self.base_url = "https://api.perplexity.ai"

    def search(
        self,
        query: str,
        search_focus: str = "general",  # general, news, academic, web
        max_results: int = 3,
    ) -> Dict:
        """
        Search the web using Perplexity Sonar model.

        Args:
            query: Search query
            search_focus: Type of search (general, news, academic)
            max_results: Maximum results to return

        Returns:
            Dict with search results and context
        """
        if not self.api_key:
            logger.warning("Perplexity API key not configured")
            return {"status": "error", "results": [], "context": ""}

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Map search focus to Perplexity search focus
            focus_map = {
                "general": "general",
                "news": "news",
                "academic": "academic",
                "web": "web",
            }
            perplexity_focus = focus_map.get(search_focus, "general")

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": query,
                    }
                ],
                "max_tokens": 1024,
                "temperature": 0.2,  # Low temp for factual results
                "return_related_questions": False,
                "search_recency_filter": "month",  # Last month for fresher results
            }

            logger.info(f"🔍 Perplexity search: {query[:100]}...")

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=15,
            )

            if response.status_code != 200:
                logger.error(f"Perplexity API error: {response.status_code} - {response.text}")
                return {
                    "status": "error",
                    "results": [],
                    "context": "",
                    "error": f"API error: {response.status_code}",
                }

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            logger.info(f"✅ Perplexity search completed: {len(content)} chars")

            return {
                "status": "success",
                "query": query,
                "context": content,
                "model": self.model,
                "timestamp": datetime.now().isoformat(),
            }

        except requests.exceptions.Timeout:
            logger.error("Perplexity API timeout")
            return {
                "status": "error",
                "results": [],
                "context": "",
                "error": "Search timeout",
            }
        except Exception as e:
            logger.error(f"Perplexity search failed: {e}")
            return {
                "status": "error",
                "results": [],
                "context": "",
                "error": str(e),
            }


def needs_web_search(user_query: str) -> bool:
    """
    Determine if a query needs web search.
    Returns True for queries about current events, recent news, real-time data.
    """
    keywords = [
        # Current events/news
        "today", "yesterday", "news", "latest", "recent",
        "current", "happening", "now", "breaking",
        # Sports/events
        "score", "result", "match", "game", "tournament",
        "championship", "winner", "ranking", "standings",
        # Weather/location based
        "weather", "temperature", "forecast",
        # Real-time data
        "stock", "price", "rate", "exchange",
        "crypto", "bitcoin", "ethereum",
        # Recent releases
        "release", "launched", "just came out",
        "new movie", "new book", "new album",
    ]

    query_lower = user_query.lower()

    # Check for current date references
    if any(keyword in query_lower for keyword in keywords):
        return True

    # Check for specific date queries (not historical)
    import re
    if re.search(r"\b20(2[3-9]|3\d)\b", query_lower):  # Years 2023+
        return True

    return False


# Global instance
search_tool = PerplexitySearchTool()


def web_search(query: str) -> str:
    """
    Perform web search and return formatted context.
    This is the function called by the agent.
    """
    result = search_tool.search(query)

    if result["status"] == "success":
        return result["context"]
    else:
        return f"Search failed: {result.get('error', 'Unknown error')}"
