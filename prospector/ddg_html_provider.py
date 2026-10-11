"""DuckDuckGo Direct HTML Search Provider for Prospector-AI.

Provides zero-dependency, non-JS fallback search directly against
https://html.duckduckgo.com/html/ when third-party client wrappers
experience rate limits, connection drops, or upstream library bugs.
"""

import re
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup


class DDGHtmlSearchProvider:
    """Queries DuckDuckGo's lightweight, non-JS HTML endpoint (html.duckduckgo.com).
    
    Bypasses aggressive cloud/datacenter IP blocking by using standard form POST
    instead of monitored AJAX/JSON APIs.
    """

    ENDPOINT = "https://html.duckduckgo.com/html/"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def parse_html(self, html_content: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Parse raw HTML from DuckDuckGo HTML endpoint into standard results."""
        results: List[Dict[str, str]] = []
        soup = BeautifulSoup(html_content, "html.parser")

        result_divs = soup.find_all("div", class_=re.compile(r"result\s+results_links"))
        for div in result_divs:
            if len(results) >= max_results:
                break

            title_elem = div.find("a", class_="result__url") or div.find("h2", class_="result__title")
            snippet_elem = div.find("a", class_="result__snippet")

            if not title_elem:
                continue

            raw_href = title_elem.get("href", "")
            title_text = title_elem.get_text(strip=True)
            snippet_text = snippet_elem.get_text(strip=True) if snippet_elem else ""

            # Unquote DuckDuckGo redirect wrapper if present (/l/?uddg=https%3A%2F%2F...)
            clean_url = self._clean_ddg_url(raw_href)

            if clean_url and title_text:
                results.append({
                    "title": title_text,
                    "link": clean_url,
                    "snippet": snippet_text,
                })

        return results

    def query(self, query_str: str, max_results: int = 10, timeout: float = 10.0) -> List[Dict[str, str]]:
        """Execute search query against html.duckduckgo.com."""
        post_data = urllib.parse.urlencode({"q": query_str, "b": ""}).encode("utf-8")
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://html.duckduckgo.com/",
        }

        req = urllib.request.Request(self.ENDPOINT, data=post_data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html_bytes = resp.read()
                html_text = html_bytes.decode("utf-8", errors="ignore")
                return self.parse_html(html_text, max_results=max_results)
        except Exception:
            return []

    @staticmethod
    def _clean_ddg_url(raw_url: str) -> str:
        """Extract destination target from DuckDuckGo redirect wrapper."""
        if "uddg=" in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            if "uddg" in query_params and query_params["uddg"]:
                return query_params["uddg"][0]
        return raw_url
