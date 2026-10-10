"""Company input resolver and normalizer."""

import re
from urllib.parse import urlparse
from typing import Optional, Tuple
from prospector.models import CompanyInfo


LEGAL_SUFFIXES = [
    r"\binc\.?\b",
    r"\bllc\.?\b",
    r"\bltd\.?\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\btechnologies\b",
    r"\btechnology\b",
    r"\bgroup\b",
    r"\bservices\b",
    r"\bpvt\.?\b",
    r"\bgmbh\b",
    r"\bco\.?\b",
]


class CompanyResolver:
    """Normalizes and resolves domain, company name, and LinkedIn URL."""

    @classmethod
    def clean_company_name(cls, name: str) -> str:
        """Strip legal entity suffixes, punctuation, and extraneous words."""
        cleaned = name.strip()
        for suffix in LEGAL_SUFFIXES:
            cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE).strip()
        # Clean trailing commas/dashes/periods
        cleaned = re.sub(r"[\s,\-\.]+$", "", cleaned).strip()
        return cleaned or name.strip()

    @classmethod
    def extract_domain_from_url(cls, url_or_domain: str) -> Optional[str]:
        """Extract clean FQDN domain from a URL or domain string."""
        raw = url_or_domain.strip().lower()
        if not raw:
            return None

        # Add protocol if missing to assist urlparse
        if not raw.startswith(("http://", "https://")):
            raw_url = "https://" + raw
        else:
            raw_url = raw

        try:
            parsed = urlparse(raw_url)
            netloc = parsed.netloc or parsed.path
            # Strip port if present
            netloc = netloc.split(":")[0]
            # Strip www
            if netloc.startswith("www."):
                netloc = netloc[4:]
            # Ensure it looks like a valid domain with a TLD
            if "." in netloc and len(netloc.split(".")[-1]) >= 2:
                return netloc
        except Exception:
            pass

        return None

    @classmethod
    def parse_linkedin_company(cls, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse company identifier from linkedin.com/company/<slug> URL."""
        match = re.search(r"linkedin\.com/company/([a-zA-Z0-9_\-]+)", url, re.IGNORECASE)
        if match:
            slug = match.group(1).replace("-", " ").title()
            full_url = f"https://www.linkedin.com/company/{match.group(1)}/"
            return slug, full_url
        return None, None

    @classmethod
    def resolve(cls, raw_input: str) -> CompanyInfo:
        """Resolve arbitrary user input into structured CompanyInfo."""
        raw = raw_input.strip()
        if not raw:
            raise ValueError("Input company/domain string cannot be empty.")

        # Case 1: LinkedIn Company URL
        if "linkedin.com/company/" in raw.lower():
            slug_name, linkedin_url = cls.parse_linkedin_company(raw)
            clean_name = slug_name or "Company"
            return CompanyInfo(
                raw_input=raw,
                clean_name=clean_name,
                domain=None,
                linkedin_company_url=linkedin_url,
            )

        # Case 2: Looks like a domain or website URL
        extracted_domain = cls.extract_domain_from_url(raw)
        if extracted_domain and not (" " in raw and "." not in raw.split()[0]):
            # Name derived from domain SLD (e.g. stripe.com -> Stripe)
            parts = extracted_domain.split(".")
            # Handle co.uk, com.au, etc.
            sld = parts[-2] if len(parts) > 2 and parts[-2] in {"co", "com", "org", "net", "gov"} else parts[0]
            clean_name = sld.replace("-", " ").capitalize()
            return CompanyInfo(
                raw_input=raw,
                clean_name=clean_name,
                domain=extracted_domain,
                linkedin_company_url=None,
            )

        # Case 3: Raw company name
        clean_name = cls.clean_company_name(raw)
        return CompanyInfo(
            raw_input=raw,
            clean_name=clean_name,
            domain=None,
            linkedin_company_url=None,
        )
