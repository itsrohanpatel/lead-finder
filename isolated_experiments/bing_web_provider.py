"""Workaround 2B: Isolated Bing Web Search Provider."""

import re
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup


class BingWebSearchProvider:
    """Queries Bing's public search engine interface (www.bing.com/search).
    
    Optimized for GitHub Actions runners hosted on Microsoft Azure: requests originating
    from Azure IP ranges to Bing benefit from native Microsoft network trust and suffer
    far less aggressive rate-limiting than external search engines.
    """

    ENDPOINT = "https://www.bing.com/search"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def parse_html(self, html_content: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Parse raw HTML from Bing web search results."""
        results: List[Dict[str, str]] = []
        soup = BeautifulSoup(html_content, "html.parser")

        algo_items = soup.find_all("li", class_="b_algo")
        for li in algo_items:
            if len(results) >= max_results:
                break

            h2 = li.find("h2")
            if not h2:
                continue

            a_tag = h2.find("a")
            if not a_tag or not a_tag.get("href"):
                continue

            title_text = a_tag.get_text(strip=True)
            raw_url = a_tag.get("href", "")

            # Extract snippet from caption
            caption_elem = li.find("div", class_="b_caption") or li.find("p")
            snippet_text = caption_elem.get_text(strip=True) if caption_elem else ""

            clean_url = self._clean_bing_url(raw_url)

            if clean_url and title_text:
                results.append({
                    "title": title_text,
                    "link": clean_url,
                    "snippet": snippet_text,
                })

        return results

    def query(self, query_str: str, max_results: int = 10, timeout: float = 10.0) -> List[Dict[str, str]]:
        """Execute search query against Bing."""
        params = urllib.parse.urlencode({
            "q": query_str,
            "count": str(min(max_results * 2, 50)),
            "first": "1",
            "FORM": "QBLH",
        })
        url = f"{self.ENDPOINT}?{params}"

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.bing.com/",
        }

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html_bytes = resp.read()
                html_text = html_bytes.decode("utf-8", errors="ignore")
                return self.parse_html(html_text, max_results=max_results)
        except Exception:
            return []

    @staticmethod
    def _clean_bing_url(raw_url: str) -> str:
        """Strip Bing tracking wrappers if present."""
        # Check for Bing click tracking URL format
        if "bing.com/ck/a?" in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            if "u" in query_params and query_params["u"]:
                encoded_u = query_params["u"][0]
                # Bing often prefixes target with 'a1' base64 encoding
                if encoded_u.startswith("a1"):
                    try:
                        import base64
                        decoded = base64.b64decode(encoded_u[2:] + "==").decode("utf-8", errors="ignore")
                        if decoded.startswith("http"):
                            return decoded
                    except Exception:
                        pass
        return raw_url
