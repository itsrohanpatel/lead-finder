"""Direct implementation and reverse-engineered alternative to Apify's company-employees-scraper.

Connects directly to Apollo.io's API to fetch company employee rosters using
domain, department, and seniority parameters without paying Apify markups.
Includes intelligent search-engine unmasking of Apollo's obfuscated last names for $0.
"""

import os
import re
import logging
from typing import List, Optional, Dict, Any, Tuple, Union
import time
import requests

logger = logging.getLogger(__name__)


class ApolloProvider:
    """Direct client for Apollo.io B2B search API (powers Apify's company-employees-scraper)."""

    BASE_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"

    DEPARTMENT_MAP = {
        # Core Apollo Enums
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
        # Common Aliases & Shorthands
        "hr": "human_resources",
        "talent": "human_resources",
        "recruiting": "human_resources",
        "people": "human_resources",
        "tech": "engineering_technical",
        "engineering": "engineering_technical",
        "dev": "engineering_technical",
        "it": "information_technology",
        "bizdev": "sales",
        "bd": "sales",
        "csuite": "c_suite",
        "exec": "c_suite",
        "executive": "c_suite",
        "cxo": "c_suite",
        "mgmt": "operations",
        "management": "operations",
    }

    SENIORITY_MAP = {
        # Core Apollo Enums
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
        # Common Aliases
        "cofounder": "founder",
        "co_founder": "founder",
        "chief": "c_suite",
        "exec": "c_suite",
        "executive": "c_suite",
        "lead": "head",
        "leader": "head",
        "mgr": "manager",
        "sr": "senior",
    }

    def __init__(self, api_key: Optional[Union[str, List[str]]] = None):
        self.api_keys: List[str] = self._resolve_api_keys(api_key)
        self._current_index: int = 0

    @classmethod
    def _resolve_api_keys(cls, api_key_arg: Optional[Union[str, List[str]]] = None) -> List[str]:
        """Collect and deduplicate Apollo API keys from arguments and environment variables.

        Supports:
        - List of keys: ["key1", "key2"]
        - Comma/newline separated strings: "key1,key2,key3"
        - APOLLO_API_KEYS env var (comma/newline separated)
        - APOLLO_API_KEY env var
        - APOLLO_API_KEY_1, APOLLO_API_KEY_2, APOLLO_API_KEY_3, etc.
        """
        raw_keys: List[str] = []

        # 1. Check explicit argument
        if api_key_arg:
            if isinstance(api_key_arg, list):
                raw_keys.extend(api_key_arg)
            elif isinstance(api_key_arg, str):
                for k in re.split(r"[,;\n\r]+", api_key_arg):
                    if k.strip():
                        raw_keys.append(k.strip())

        # 2. Check APOLLO_API_KEYS environment variable
        env_keys = os.getenv("APOLLO_API_KEYS", "")
        if env_keys:
            for k in re.split(r"[,;\n\r]+", env_keys):
                if k.strip():
                    raw_keys.append(k.strip())

        # 3. Check APOLLO_API_KEY environment variable
        single_env = os.getenv("APOLLO_API_KEY", "")
        if single_env:
            for k in re.split(r"[,;\n\r]+", single_env):
                if k.strip():
                    raw_keys.append(k.strip())

        # 4. Check numbered environment variables: APOLLO_API_KEY_1, APOLLO_API_KEY_2, etc.
        for env_name, env_val in os.environ.items():
            if re.match(r"^APOLLO_API_KEY_\d+$", env_name, re.IGNORECASE) and env_val.strip():
                raw_keys.append(env_val.strip())

        # Deduplicate while preserving order
        deduped: List[str] = []
        seen = set()
        for k in raw_keys:
            k_clean = k.strip()
            if k_clean and k_clean not in seen:
                seen.add(k_clean)
                deduped.append(k_clean)

        return deduped

    @property
    def api_key(self) -> str:
        """Returns the currently active API key, or empty string if no keys configured."""
        if not self.api_keys:
            return ""
        return self.api_keys[self._current_index % len(self.api_keys)]

    def rotate_key(self, reason: str = "rate_limit") -> Optional[str]:
        """Rotate to the next API key in the pool (round-robin / failover)."""
        if not self.api_keys or len(self.api_keys) <= 1:
            return self.api_key if self.api_keys else None
        old_idx = self._current_index % len(self.api_keys)
        self._current_index = (self._current_index + 1) % len(self.api_keys)
        new_idx = self._current_index % len(self.api_keys)
        logger.info(
            f"Rotating Apollo API key ({reason}): switched from key #{old_idx + 1} "
            f"to key #{new_idx + 1} of {len(self.api_keys)}."
        )
        return self.api_key

    @classmethod
    def clean_domain(cls, website_or_domain: str) -> str:
        """Extract clean root second-level domain from URL or domain string."""
        dom = website_or_domain.lower().strip()
        dom = re.sub(r"^https?://", "", dom)
        dom = re.sub(r"^www\.", "", dom)
        dom = dom.split("/")[0].split("?")[0].strip()
        return dom

    @classmethod
    def resolve_departments(cls, departments: Optional[List[str]]) -> List[str]:
        """Normalize list of department strings/aliases to valid Apollo enums."""
        if not departments:
            return []
        resolved = []
        for d in departments:
            clean = d.strip().lower().replace("-", "_").replace(" ", "_")
            if clean in cls.DEPARTMENT_MAP:
                enum_val = cls.DEPARTMENT_MAP[clean]
                if enum_val not in resolved:
                    resolved.append(enum_val)
        return resolved

    @classmethod
    def resolve_seniorities(cls, seniorities: Optional[List[str]]) -> List[str]:
        """Normalize list of seniority strings/aliases to valid Apollo enums."""
        if not seniorities:
            return []
        resolved = []
        for s in seniorities:
            clean = s.strip().lower().replace("-", "_").replace(" ", "_")
            if clean in cls.SENIORITY_MAP:
                enum_val = cls.SENIORITY_MAP[clean]
                if enum_val not in resolved:
                    resolved.append(enum_val)
        return resolved

    @staticmethod
    def match_obfuscated_last_name(candidate_last: str, obfuscated_pattern: str) -> bool:
        """Check if a candidate last name matches an Apollo obfuscated pattern like 'Ve***a'.

        Apollo masks last names by keeping the first 1-2 characters and trailing 1 character,
        inserting asterisks in between (e.g. 'Ve***a', 'Gu***a', 'S***h').
        """
        if not candidate_last or not obfuscated_pattern:
            return False
        cand = candidate_last.strip().lower()
        obf = obfuscated_pattern.strip().lower()

        if "*" not in obf:
            return cand == obf

        parts = obf.split("*")
        prefix = parts[0]
        suffix = parts[-1]

        if prefix and not cand.startswith(prefix):
            return False
        if suffix and not cand.endswith(suffix):
            return False

        if len(cand) < (len(prefix) + len(suffix)):
            return False

        return True

    @staticmethod
    def extract_name_from_linkedin_title(
        title: str, first_name: str, obfuscated_pattern: str
    ) -> Optional[Tuple[str, str]]:
        """Extract matched full name and last name from a LinkedIn result title."""
        if not title or not first_name:
            return None

        # Look for "{First} {Last}" pattern in the title
        pattern = rf"\b{re.escape(first_name)}\s+([A-Za-z]+)\b"
        for m in re.finditer(pattern, title, re.IGNORECASE):
            candidate_last = m.group(1)
            if ApolloProvider.match_obfuscated_last_name(candidate_last, obfuscated_pattern):
                return f"{first_name} {candidate_last}", candidate_last

        return None

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

        valid_deps = self.resolve_departments(departments)
        valid_sens = self.resolve_seniorities(seniority)

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

            attempts = 0
            max_attempts = max(1, len(self.api_keys))
            resp = None

            while attempts < max_attempts:
                current_key = self.api_key
                headers = {
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": current_key,
                }
                try:
                    resp = requests.post(self.BASE_URL, headers=headers, json=payload, timeout=12.0)
                    if resp.status_code == 200:
                        break
                    elif resp.status_code in (429, 403) and len(self.api_keys) > 1:
                        reason = "HTTP 429 Rate Limit" if resp.status_code == 429 else "HTTP 403 Forbidden"
                        logger.warning(f"Apollo key #{self._current_index + 1} returned {reason}. Failing over to next key...")
                        self.rotate_key(reason=reason)
                        attempts += 1
                        time.sleep(0.3)
                        continue
                    else:
                        logger.debug(f"Apollo API error: {resp.status_code} - {resp.text[:200]}")
                        break
                except Exception as e:
                    logger.warning(f"Error querying Apollo API with key #{self._current_index + 1}: {e}")
                    if len(self.api_keys) > 1:
                        self.rotate_key(reason="Network exception")
                        attempts += 1
                        continue
                    break

            if not resp or resp.status_code != 200:
                break

            try:
                data = resp.json()
                people = data.get("people", [])
                if not people:
                    break

                for p in people:
                    first = p.get("first_name", "")
                    last = p.get("last_name", "")
                    last_obf = p.get("last_name_obfuscated", "")
                    name = p.get("name")

                    if not name:
                        if first and last:
                            name = f"{first} {last}".strip()
                        elif first and last_obf:
                            name = f"{first} {last_obf}".strip()
                        elif first:
                            name = first

                    title = p.get("title") or p.get("headline") or ""
                    linkedin_url = p.get("linkedin_url", "")
                    city = p.get("city", "")
                    country = p.get("country", "")
                    location = f"{city}, {country}".strip(", ") if (city or country) else None

                    results.append({
                        "name": name,
                        "first_name": first,
                        "last_name": last or last_obf,
                        "last_name_obfuscated": last_obf,
                        "is_obfuscated": bool(last_obf and "*" in last_obf),
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
                if len(people) < per_page:
                    break
            except Exception as e:
                logger.warning(f"Error querying Apollo API: {e}")
                break

        return results

    def unmask_candidate(
        self,
        candidate: Dict[str, Any],
        search_engine: Any,
        company_name: str,
    ) -> Dict[str, Any]:
        """Unmask an Apollo candidate's full name and LinkedIn URL via passive search dorks."""
        first = candidate.get("first_name", "")
        last_obf = candidate.get("last_name_obfuscated", "")
        current_last = candidate.get("last_name", "")

        # If already unobfuscated, return directly
        if current_last and "*" not in current_last:
            candidate["is_obfuscated"] = False
            return candidate

        if not first or not last_obf:
            return candidate

        # Search dork: site:linkedin.com/in {first} {company_name}
        clean_company = re.sub(r"[^\w\s]", "", company_name).strip() if company_name else ""
        dork = f"site:linkedin.com/in {first} {clean_company}".strip()

        try:
            results = search_engine.search_duckduckgo(dork, max_results=5)
            for item in results:
                title = item.get("title", "")
                link = item.get("link", "") or item.get("href", "")

                # 1. Match against LinkedIn title
                matched = self.extract_name_from_linkedin_title(title, first, last_obf)
                if matched:
                    full_name, resolved_last = matched
                    candidate["name"] = full_name
                    candidate["first_name"] = first
                    candidate["last_name"] = resolved_last
                    candidate["is_obfuscated"] = False
                    if link and "linkedin.com/in/" in link:
                        candidate["linkedin_url"] = link
                    logger.info(f"Unmasked Apollo candidate: {first} {last_obf} -> {full_name}")
                    return candidate

                # 2. Match against LinkedIn URL slug (e.g. linkedin.com/in/sshubamverma)
                if link and "linkedin.com/in/" in link:
                    slug_match = re.search(r"linkedin\.com/in/([a-zA-Z0-9_\-]+)", link)
                    if slug_match:
                        slug = slug_match.group(1).lower()
                        clean_first = first.lower()
                        if clean_first in slug:
                            remainder = slug.replace(clean_first, "").strip("-_")
                            remainder = re.sub(r"[0-9]+$", "", remainder)
                            if remainder and self.match_obfuscated_last_name(remainder, last_obf):
                                resolved_last = remainder.title()
                                full_name = f"{first} {resolved_last}"
                                candidate["name"] = full_name
                                candidate["first_name"] = first
                                candidate["last_name"] = resolved_last
                                candidate["is_obfuscated"] = False
                                candidate["linkedin_url"] = link
                                logger.info(f"Unmasked Apollo candidate from URL: {first} {last_obf} -> {full_name}")
                                return candidate
        except Exception as e:
            logger.debug(f"Unmasking search dork failed for {first} {last_obf}: {e}")

        return candidate

    def unmask_candidates(
        self,
        candidates: List[Dict[str, Any]],
        search_engine: Any,
        company_name: str,
        max_to_unmask: int = 8,
    ) -> List[Dict[str, Any]]:
        """Batch unmask a list of candidate records."""
        unmasked_list = []
        count = 0
        for cand in candidates:
            if cand.get("is_obfuscated") and count < max_to_unmask:
                cand = self.unmask_candidate(cand, search_engine, company_name)
                count += 1
            unmasked_list.append(cand)
        return unmasked_list
