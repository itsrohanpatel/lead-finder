"""Parses search results into validated LeadRecord objects."""

import re
from typing import List, Optional, Tuple, Dict, Any
from prospector.models import LeadRecord, RoleCategory


C_SUITE_KEYWORDS = [
    r"\bceo\b",
    r"\bchief executive\b",
    r"\bcto\b",
    r"\bchief technology\b",
    r"\bchief technical\b",
    r"\bcoo\b",
    r"\bchief operating\b",
    r"\bcfo\b",
    r"\bchief financial\b",
    r"\bcmo\b",
    r"\bchief marketing\b",
    r"\bcro\b",
    r"\bchief revenue\b",
    r"\bcpo\b",
    r"\bchief product\b",
    r"\bfounder\b",
    r"\bco-founder\b",
    r"\bpresident\b",
    r"\bmanaging director\b",
    r"\bvp\b",
    r"\bvice president\b",
    r"\bpartner\b",
]

HR_TALENT_KEYWORDS = [
    r"\btalent acquisition\b",
    r"\bhead of talent\b",
    r"\btalent lead\b",
    r"\btalent partner\b",
    r"\btalent scout\b",
    r"\brecruiter\b",
    r"\brecruiting\b",
    r"\brecruitment\b",
    r"\bhead of people\b",
    r"\bpeople ops\b",
    r"\bpeople operations\b",
    r"\bhuman resources\b",
    r"\bhr director\b",
    r"\bvp hr\b",
    r"\bhead of hr\b",
    r"\bstaffing\b",
    r"\bsourcer\b",
    r"\bta lead\b",
    r"\bta manager\b",
]


class LeadExtractor:
    """Extracts, categorizes, and validates leads from search result items."""

    @classmethod
    def is_individual_linkedin_profile(cls, url: str) -> bool:
        """Verify URL is an individual profile (not company, job, or search page)."""
        clean_url = url.lower()
        if "linkedin.com/in/" not in clean_url:
            return False
        # Exclude directories and job listings
        if any(bad in clean_url for bad in ["/dir/", "/jobs/", "/pulse/", "/learning/"]):
            return False
        return True

    @classmethod
    def clean_linkedin_url(cls, url: str) -> str:
        """Strip tracking query parameters from LinkedIn URL."""
        return url.split("?")[0].rstrip("/")

    @classmethod
    def parse_name_and_title(cls, raw_title: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract person's name and job title from typical LinkedIn SERP titles.
        
        Examples:
        - "Satya Nadella - Chairman and CEO - Microsoft | LinkedIn"
        - "Jane Doe | Head of Talent - Stripe"
        - "Alex Smith - Chief Technology Officer at Acme"
        """
        # Strip trailing branding ("| LinkedIn", "- LinkedIn", etc.)
        cleaned = re.sub(r"[\-\|\–\—]\s*LinkedIn.*$", "", raw_title, flags=re.IGNORECASE).strip()

        # Common delimiters between Name, Title, and Company: ' - ', ' | ', ' – ', ' — '
        parts = re.split(r"\s+[\-\|\–\—]\s+", cleaned)
        if len(parts) >= 2:
            name_candidate = parts[0].strip()
            title_candidate = parts[1].strip()
            # If title contains ' at Company', clean it
            title_candidate = re.sub(r"\s+at\s+.*$", "", title_candidate, flags=re.IGNORECASE).strip()
            return name_candidate, title_candidate

        # Alternate format: "John Doe, CEO at Company"
        match = re.search(r"^([a-zA-Z\s\.\'\-]+),\s*(.*?)(?:\s+at\s+.*)?$", cleaned)
        if match:
            return match.group(1).strip(), match.group(2).strip()

        return None, None

    @classmethod
    def split_name(cls, full_name: str) -> Tuple[str, str]:
        """Split full name into first name and last name."""
        tokens = [t.strip() for t in full_name.split() if t.strip()]
        if not tokens:
            return "", ""
        if len(tokens) == 1:
            return tokens[0], ""
        return tokens[0], tokens[-1]

    @classmethod
    def categorize_role(cls, title: str) -> RoleCategory:
        """Categorize job title into C-Suite, HR/Talent, or Other."""
        title_lower = title.lower()
        for kw in HR_TALENT_KEYWORDS:
            if re.search(kw, title_lower):
                return RoleCategory.HR_TALENT
        for kw in C_SUITE_KEYWORDS:
            if re.search(kw, title_lower):
                return RoleCategory.C_SUITE
        return RoleCategory.OTHER

    @classmethod
    def extract_leads(
        cls,
        search_results: List[Dict[str, Any]],
        company_name: str,
        domain: Optional[str] = None,
        target_roles: Optional[List[RoleCategory]] = None,
    ) -> List[LeadRecord]:
        """Extract deduplicated and qualified leads from raw search engine results."""
        leads: List[LeadRecord] = []
        seen_urls = set()
        seen_names = set()

        if target_roles is None:
            target_roles = [RoleCategory.C_SUITE, RoleCategory.HR_TALENT]

        for item in search_results:
            link = item.get("link", "")
            title = item.get("title", "")

            if not cls.is_individual_linkedin_profile(link):
                continue

            clean_url = cls.clean_linkedin_url(link)
            if clean_url in seen_urls:
                continue

            name, job_title = cls.parse_name_and_title(title)
            if not name or not job_title:
                continue

            # Skip if name looks like generic text or directory
            if any(bad in name.lower() for bad in ["linkedin", "profiles", "directory", "jobs"]):
                continue

            first_name, last_name = cls.split_name(name)
            if not first_name:
                continue

            name_key = f"{first_name.lower()} {last_name.lower()}"
            if name_key in seen_names:
                continue

            role_cat = cls.categorize_role(job_title)
            if role_cat not in target_roles and RoleCategory.OTHER not in target_roles:
                continue

            seen_urls.add(clean_url)
            seen_names.add(name_key)

            leads.append(
                LeadRecord(
                    full_name=name,
                    first_name=first_name,
                    last_name=last_name,
                    job_title=job_title,
                    role_category=role_cat,
                    linkedin_url=clean_url,
                    company_name=company_name,
                    domain=domain,
                )
            )

        return leads
