"""Search engine query provider for passive LinkedIn OSINT dorking."""

import os
import time
import logging
from typing import List, Dict, Any, Optional
import requests
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


class SearchEngine:
    """Dispatches search queries to DuckDuckGo (free, zero-config) or optional Serper/Google APIs."""

    def __init__(self, serper_api_key: Optional[str] = None):
        self.serper_api_key = serper_api_key or os.getenv("SERPER_API_KEY")
        try:
            from ddgs import ddgs
            for eng in list(ddgs.ENGINES.get("text", {}).keys()):
                if eng != "yahoo":
                    ddgs.ENGINES["text"].pop(eng, None)
        except Exception:
            pass

    def search_duckduckgo(self, query: str, max_results: int = 15, retries: int = 1) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo via DDGS text search with automatic backoff retry."""
        results: List[Dict[str, Any]] = []
        for attempt in range(retries + 1):
            try:
                with DDGS() as ddgs:
                    raw_results = ddgs.text(query, max_results=max_results)
                    for item in raw_results:
                        results.append({
                            "title": item.get("title", ""),
                            "link": item.get("href", ""),
                            "snippet": item.get("body", ""),
                        })
                break
            except Exception as exc:
                if "no results found" in str(exc).lower():
                    # 0 search matches is normal, do not retry
                    break
                logger.warning(f"DuckDuckGo search attempt {attempt+1} error: {exc}")
                if attempt < retries:
                    time.sleep(1.0)
        return results

    def search_serper(self, query: str, max_results: int = 15) -> List[Dict[str, Any]]:
        """Optional accelerator search using Serper.dev API if key provided."""
        if not self.serper_api_key:
            return []
        try:
            url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json",
            }
            payload = {"q": query, "num": max_results}
            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                items = []
                for org in data.get("organic", []):
                    items.append({
                        "title": org.get("title", ""),
                        "link": org.get("link", ""),
                        "snippet": org.get("snippet", ""),
                    })
                return items
        except Exception as exc:
            logger.warning(f"Serper API search error: {exc}")
        return []

    def query(self, query_str: str, max_results: int = 15) -> List[Dict[str, Any]]:
        """Query primary engine (DuckDuckGo) with fallback to Serper if configured."""
        logger.info(f"Executing search dork: {query_str}")
        # Try Serper first if key provided for faster enterprise response
        if self.serper_api_key:
            res = self.search_serper(query_str, max_results=max_results)
            if res:
                return res

        # Primary default: DuckDuckGo
        return self.search_duckduckgo(query_str, max_results=max_results)

    def find_company_domain(self, company_name: str) -> Optional[str]:
        """Resolve official company domain from name via fast DNS probe and search engine fallback."""
        import re
        import dns.resolver

        clean_slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        candidates = []
        if clean_slug:
            candidates.append(f"{clean_slug}.com")
            candidates.append(f"{clean_slug}.in")
            candidates.append(f"{clean_slug}.ai")
            if clean_slug.startswith("the") and len(clean_slug) > 3:
                candidates.append(f"{clean_slug[3:]}.com")
                candidates.append(f"{clean_slug[3:]}.in")

        # Fast DNS check on candidate domains
        for cand in candidates:
            try:
                dns.resolver.resolve(cand, "A", lifetime=1.2)
                return cand
            except Exception:
                pass

        query_str = f'"{company_name}" official website domain'
        results = self.query(query_str, max_results=5)
        blacklisted = [
            "linkedin.com", "wikipedia.org", "bloomberg.com", "facebook.com",
            "twitter.com", "x.com", "crunchbase.com", "bing.com", "google.com",
            "yahoo.com", "duckduckgo.com", "youtube.com", "instagram.com",
            "glassdoor.com", "indeed.com", "ambitionbox.com", "zaubacorp.com",
            "tofler.in", "tracxn.com"
        ]
        for r in results:
            link = r.get("link", "")
            if any(agg in link.lower() for agg in blacklisted):
                continue
            from prospector.company_resolver import CompanyResolver
            domain = CompanyResolver.extract_domain_from_url(link)
            if domain and "." in domain:
                try:
                    dns.resolver.resolve(domain, "A", lifetime=1.2)
                    return domain
                except Exception:
                    continue
        return None
