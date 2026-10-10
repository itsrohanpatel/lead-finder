"""Company input resolver and normalizer."""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Optional, Tuple, List, Dict, Any
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
    def enrich_from_website(cls, domain: str) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
        """Fetch homepage and extract official trade name, LinkedIn company page, and direct team profiles."""
        url = f"https://{domain}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        trade_name = None
        linkedin_company = None
        team_leads: List[Dict[str, Any]] = []
        try:
            resp = requests.get(url, headers=headers, timeout=3.5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. Clean Title Name
                if soup.title and soup.title.string:
                    title_text = soup.title.string.strip()
                    parts = re.split(r"[-|:•–—]", title_text)
                    candidate = parts[0].strip()
                    if any(term in candidate.lower() for term in ["consultancy", "solutions", "services", "human resource", "home"]) and len(parts) > 1:
                        candidate = parts[-1].strip()
                    candidate = cls.clean_company_name(candidate)
                    if candidate and len(candidate) <= 35:
                        trade_name = candidate

                # 2. LinkedIn company page
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "linkedin.com/company/" in href:
                        clean_li = href.split("?")[0].rstrip("/")
                        if clean_li.startswith("http://"):
                            clean_li = "https://" + clean_li[7:]
                        linkedin_company = clean_li
                        break

                # 3. Direct LinkedIn personal profiles
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "linkedin.com/in/" in href:
                        clean_url = href.split("?")[0].rstrip("/")
                        name = a.get_text(strip=True)
                        if not name and a.parent:
                            name = a.parent.get_text(strip=True)
                        if not name and a.parent and a.parent.parent:
                            gp_text = a.parent.parent.get_text(separator=" ", strip=True)
                            m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", gp_text)
                            if m:
                                name = m.group(1).strip()
                        if name and len(name.split()) in [2, 3]:
                            if not any(bad in name.lower() for bad in ["linkedin", "follow", "share", "view", "connect"]):
                                team_leads.append({
                                    "name": name,
                                    "linkedin_url": clean_url,
                                    "job_title": "Founder / Leadership",
                                })

                # 4. Schema.org JSON-LD & Author metadata
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        import json
                        data = json.loads(script.string or "")
                        def extract_ld_persons(obj):
                            if isinstance(obj, dict):
                                if obj.get("@type") == "Person" and obj.get("name"):
                                    p_name = obj.get("name", "").strip()
                                    if len(p_name.split()) in [2, 3] and not any(bad in p_name.lower() for bad in ["admin", "theme"]):
                                        if not any(tl["name"].lower() == p_name.lower() for tl in team_leads):
                                            team_leads.append({
                                                "name": p_name,
                                                "linkedin_url": None,
                                                "job_title": "Founder & CEO",
                                            })
                                for v in obj.values():
                                    extract_ld_persons(v)
                            elif isinstance(obj, list):
                                for item in obj:
                                    extract_ld_persons(item)
                        extract_ld_persons(data)
                    except Exception:
                        pass

                for meta in soup.find_all("meta"):
                    prop = (meta.get("property") or meta.get("name") or "").lower()
                    content = (meta.get("content") or "").strip()
                    if any(k in prop for k in ["author", "twitter:data1", "article:author"]):
                        if content and len(content.split()) in [2, 3] and not any(bad in content.lower() for bad in ["admin", "theme", "http"]):
                            if not any(tl["name"].lower() == content.lower() for tl in team_leads):
                                team_leads.append({
                                    "name": content,
                                    "linkedin_url": None,
                                    "job_title": "Founder & CEO",
                                })
        except Exception:
            pass

        return trade_name, linkedin_company, team_leads

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
            # Baseline name derived from domain SLD
            parts = extracted_domain.split(".")
            sld = parts[-2] if len(parts) > 2 and parts[-2] in {"co", "com", "org", "net", "gov"} else parts[0]
            clean_name = sld.replace("-", " ").capitalize()

            # Attempt live website metadata enrichment
            trade_name, li_company, direct_leads = cls.enrich_from_website(extracted_domain)
            final_name = trade_name or clean_name
            return CompanyInfo(
                raw_input=raw,
                clean_name=final_name,
                domain=extracted_domain,
                linkedin_company_url=li_company,
                direct_website_leads=direct_leads,
            )

        # Case 3: Raw company name
        clean_name = cls.clean_company_name(raw)
        return CompanyInfo(
            raw_input=raw,
            clean_name=clean_name,
            domain=None,
            linkedin_company_url=None,
        )
