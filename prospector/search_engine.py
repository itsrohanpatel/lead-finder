import os
import time
import logging
import warnings
from typing import List, Dict, Any, Optional
import requests

# Suppress rename warning if legacy duckduckgo_search wrapper is imported
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*duckduckgo_search.*")

try:
    from ddgs import DDGS
    import ddgs.ddgs as ddgs_core
except ImportError:
    try:
        from duckduckgo_search import DDGS
        import duckduckgo_search as ddgs_core
    except ImportError:
        DDGS = None
        ddgs_core = None

logger = logging.getLogger(__name__)


class SearchEngine:
    """Dispatches search queries to DuckDuckGo/Yahoo (free, zero-config) or optional Serper/Google APIs."""

    def __init__(self, serper_api_key: Optional[str] = None):
        self.serper_api_key = serper_api_key or os.getenv("SERPER_API_KEY")
        # Silence ddgs backend warnings (e.g. grokipedia/wikipedia disabled)
        logging.getLogger("ddgs").setLevel(logging.ERROR)
        self._ddgs_client = None
        self.bing_provider = None
        self.html_provider = None
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._init_ddgs_client()

    def _init_ddgs_client(self) -> None:
        """Initialize or reset persistent DDGS client with higher timeout for cloud networks."""
        try:
            if DDGS:
                self._ddgs_client = DDGS(timeout=10)
        except Exception as e:
            logger.debug(f"Could not initialize persistent DDGS client: {e}")
            self._ddgs_client = None

    def search_duckduckgo(self, query: str, max_results: int = 15, retries: int = 3) -> List[Dict[str, Any]]:
        """Search using fast direct Bing as primary, with Yahoo and DDG HTML fallbacks and backoff."""
        if query in self._cache:
            return self._cache[query]

        results: List[Dict[str, Any]] = []

        # Polite inter-query pacing
        time.sleep(0.4)

        for attempt in range(retries + 1):
            try:
                raw_results = []

                # 1. Primary backend: Fast Direct Bing Web Provider (<1s, Azure native, zero third-party blocks)
                try:
                    if not self.bing_provider:
                        from prospector.bing_web_provider import BingWebSearchProvider
                        self.bing_provider = BingWebSearchProvider()
                    raw_results = self.bing_provider.query(query, max_results=max_results)
                except Exception as b_err:
                    logger.debug(f"Direct Bing search error: {b_err}")

                # 2. Secondary backend: Yahoo via DDGS if Bing returned 0
                if not raw_results:
                    if self._ddgs_client is None:
                        self._init_ddgs_client()
                    client = self._ddgs_client or (DDGS(timeout=10) if DDGS else None)
                    if client:
                        try:
                            raw_results = list(client.text(query, backend="yahoo", max_results=max_results))
                        except Exception as y_err:
                            logger.debug(f"Yahoo search error: {y_err}")

                # 3. Tertiary backend: Direct DDG HTML search provider
                if not raw_results:
                    try:
                        if not self.html_provider:
                            from prospector.ddg_html_provider import DDGHtmlSearchProvider
                            self.html_provider = DDGHtmlSearchProvider()
                        raw_results = self.html_provider.query(query, max_results=max_results)
                    except Exception as fb_err:
                        logger.debug(f"Direct DDG HTML fallback error: {fb_err}")

                for item in raw_results:
                    link = item.get("link") or item.get("href") or ""
                    snippet = item.get("snippet") or item.get("body") or ""
                    title = item.get("title") or ""
                    if link and not any(r["link"] == link for r in results):
                        results.append({
                            "title": title,
                            "link": link,
                            "snippet": snippet,
                        })

                # If we successfully collected results, break out of retry loop
                if results:
                    break

                # If no results found, back off and retry
                if attempt < retries:
                    logger.debug(f"Attempt {attempt+1} yielded 0 results, retrying with backoff...")
                    self._init_ddgs_client()
                    time.sleep(1.5 * (attempt + 1))
            except Exception as exc:
                logger.warning(f"Search attempt {attempt+1} error: {exc}")
                self._init_ddgs_client()
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))

        if results:
            self._cache[query] = results
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
