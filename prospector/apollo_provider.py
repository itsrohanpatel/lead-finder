"""Direct implementation and reverse-engineered alternative to Apify's company-employees-scraper.

Connects directly to Apollo.io's API to fetch company employee rosters using
the identical domain, department, and seniority parameters without paying Apify markups.
"""

import os
import re
import logging
from typing import List, Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


class ApolloProvider:
    """Direct client for Apollo.io B2B search API (powers Apify's company-employees-scraper)."""

    BASE_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"

    DEPARTMENT_MAP = {
        "c_suite": "c_suite",
        "product": "product",
        "engineering_technical": "engineering_technical",
        "design": "design",
        "education": "education",
        "finance": "finance",
        "human_resources": "human_resources",
        "information_technology": "information_technology",
        "legal": "legal",
        "marketing": "marketing",
        "medical_health": "medical_health",
        "operations": "operations",
        "sales": "sales",
        "consulting": "consulting",
    }

    SENIORITY_MAP = {
        "founder": "founder",
        "owner": "owner",
        "c_suite": "c_suite",
        "director": "director",
        "partner": "partner",
        "vp": "vp",
        "head": "head",
        "manager": "manager",
        "senior": "senior",
        "entry": "entry",
        "intern": "intern",
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("APOLLO_API_KEY", "")

    @classmethod
    def clean_domain(cls, website_or_domain: str) -> str:
        """Extract clean root second-level domain from URL or domain string."""
        dom = website_or_domain.lower().strip()
        dom = re.sub(r"^https?://", "", dom)
        dom = re.sub(r"^www\.", "", dom)
        dom = dom.split("/")[0].split("?")[0].strip()
        return dom

    def search_employees(
        self,
        website: str,
        departments: Optional[List[str]] = None,
        seniority: Optional[List[str]] = None,
        max_records: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch employee records directly from Apollo API."""
        if not self.api_key:
            logger.warning("No Apollo API key provided. Skipping Apollo direct lookup.")
            return []

        domain = self.clean_domain(website)
        if not domain:
            return []

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key,
        }

        results: List[Dict[str, Any]] = []
        page = 1
        per_page = min(max_records, 100)

        # Validate departments and seniority against known enums
        valid_deps = [self.DEPARTMENT_MAP[d] for d in (departments or []) if d in self.DEPARTMENT_MAP]
        valid_sens = [self.SENIORITY_MAP[s] for s in (seniority or []) if s in self.SENIORITY_MAP]

        while len(results) < max_records:
            payload: Dict[str, Any] = {
                "q_organization_domains_list": [domain],
                "page": page,
                "per_page": per_page,
            }
            if valid_deps:
                payload["person_departments"] = valid_deps
            if valid_sens:
                payload["person_seniorities"] = valid_sens

            try:
                resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=12.0)
                if resp.status_code != 200:
                    logger.debug(f"Apollo API error: {resp.status_code} - {resp.text[:200]}")
                    break

                data = resp.json()
                people = data.get("people", [])
                if not people:
                    break

                for p in people:
                    name = p.get("name")
                    if not name:
                        first = p.get("first_name", "")
                        last = p.get("last_name", "")
                        name = f"{first} {last}".strip()

                    title = p.get("title") or p.get("headline") or ""
                    linkedin_url = p.get("linkedin_url", "")
                    city = p.get("city", "")
                    country = p.get("country", "")
                    location = f"{city}, {country}".strip(", ") if (city or country) else None

                    results.append({
                        "name": name,
                        "first_name": p.get("first_name", ""),
                        "last_name": p.get("last_name", ""),
                        "title": title,
                        "job_title": title,
                        "linkedin_url": linkedin_url,
                        "location": location,
                        "company_name": p.get("organization", {}).get("name") if isinstance(p.get("organization"), dict) else None,
                        "domain": domain,
                        "raw_person": p,
                    })

                    if len(results) >= max_records:
                        break

                page += 1
                # If less than per_page returned, we reached the end
                if len(people) < per_page:
                    break
            except Exception as e:
                logger.warning(f"Error querying Apollo API: {e}")
                break

        return results
